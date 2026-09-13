"""Timeline -> mp4.

Two ways to describe the edit in `timeline:`
  segments: explicit list (src, in/out, speed, xfade...) + audio.vo placements (as before), or
  beats:    one beat per voice-over line; the beat length follows the VO duration and its shots are fitted automatically.

Segment options: src (clip:<id> | scene:<name> | overlay:<id> | path), in, out, speed, len (auto speed), hold, still, zoom, pan,
crop_x / crop_y (0..1 reframing when the source aspect differs, e.g. 16:9 clip in a 9:16 video), frame (<device_frame overlay id>),
xfade (seconds of crossfade into the next segment), xfade_kind.
Time references: 12.5 | end | seg3+0.5 | <segment id>-0.2 (before its end) | beat:<id>+x | beatend:<id>-x | vo:<id>+x | voend:<id>+x
Audio: VO (optional tempo), clip ambience, music with sidechain ducking, loudnorm -16 LUFS, AAC 48 kHz.
Captions: `captions: {mode: lines|words, burn: bool, ...}` -> build/subtitles.srt (+ captions.ass in words mode)."""
from __future__ import annotations
import json, re, subprocess, pathlib
from .clips import best_file

def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0: raise RuntimeError(" ".join(map(str, cmd))[:1500] + "\n" + r.stderr[-2500:])
    return r
def _dur(f): return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]))
def _hex_ass(c, alpha=0):
    c = c.lstrip("#"); r, g, b = c[0:2], c[2:4], c[4:6]; return f"&H{alpha:02X}{b}{g}{r}".upper()

class Assembler:
    def __init__(self, project, log=print):
        self.p = project; self.log = log; v = project["video"]; self.W, self.H, self.FPS = v["width"], v["height"], v["fps"]
        self.B = project.build_dir; self.TMP = self.B / "tmp"; self.TMP.mkdir(parents=True, exist_ok=True)
        self.items = {it["id"]: it for it in project.get("overlays", {}).get("items", [])}
    # ------------------------------------------------------------------ sources
    def resolve(self, src: str) -> pathlib.Path:
        if src.startswith("clip:"):
            f, _ = best_file(self.p, src[5:])
            if not f: raise FileNotFoundError(f"clip {src[5:]} not generated (run `clips`)")
            return f
        if src.startswith("scene:"): return self.p.screens_out / f"{src[6:]}.mp4"
        if src.startswith("overlay:"): return self.p.overlays_dir / f"{src[8:]}.png"
        return self.p.path(src)
    def vo_path(self, v) -> pathlib.Path:
        return self.p.dir / "vo" / f"{v['id']}.mp3" if "id" in v else self.p.path(v["src"])
    # ------------------------------------------------------------------ beats -> segments
    def mus(self, v, tl=None):
        """Seconds from a number or a musical string: '2b' (beats), '1bar', '-0.5bar' (needs timeline.bpm)."""
        if isinstance(v, (int, float)): return float(v)
        tl = tl or self.p["timeline"]; m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(b|beat|beats|bar|bars|s)?\s*", str(v))
        if not m: raise ValueError(f"bad duration: {v}")
        n, u = float(m.group(1)), (m.group(2) or "s")
        if u == "s": return n
        bpm = float(tl.get("bpm") or 0)
        if not bpm: raise ValueError(f"'{v}' needs timeline.bpm")
        beat = 60.0 / bpm
        return n * beat * (int(tl.get("beats_per_bar", 4)) if u.startswith("bar") else 1)
    def compile_beats(self, tl):
        a = dict(tl.get("audio", {})); tempo_default = float(a.get("vo_tempo", 1.0))
        lead_d, tail_d = float(tl.get("beat_lead", 0.25)), float(tl.get("beat_tail", 0.2))
        segs, vo, ovs, amb, beats_meta = [], [], list(tl.get("overlays", [])), list(a.get("ambient", [])), []
        for bi, beat in enumerate(tl["beats"]):
            bid = beat.get("id", f"b{bi}"); shots = beat["shots"]
            tempo = float(beat.get("tempo", tempo_default)); lead = float(beat.get("lead", lead_d)); tail = float(beat.get("tail", tail_d))
            Lvo = _dur(self.vo_path({"id": beat["vo"]})) / tempo if beat.get("vo") else 0.0
            if "bars" in beat: total = self.mus(f"{beat['bars']}bar", tl) + self.mus(beat.get("extra", 0.0), tl)
            elif "len" in beat: total = self.mus(beat["len"], tl)
            elif beat.get("vo"): total = lead + Lvo + tail + self.mus(beat.get("extra", 0.0), tl)
            else: raise ValueError(f"beat {bid}: needs vo, len or bars")
            # natural length of a shot = (out-in)/speed (videos) or len (stills)
            for sh in shots:
                for k in ("len", "xfade"):
                    if k in sh: sh[k] = self.mus(sh[k], tl)
                if not sh.get("still") and "out" not in sh and not str(sh["src"]).startswith("overlay:"):
                    sh["out"] = round(_dur(self.resolve(sh["src"])) - 0.05, 3)   # default: until the end of the source
            def natural(s):
                if "len" in s: return float(s["len"])
                if s.get("still"): return 3.0
                return (float(s["out"]) - float(s.get("in", 0))) / float(s.get("speed", 1.0))
            fixed = [s for s in shots if s.get("fixed")]
            flex = [s for s in shots if s not in fixed]
            used = sum(natural(s) - float(s.get("xfade", 0.0)) for s in fixed)
            remaining = total - used
            if flex:
                weights = [float(s.get("weight", natural(s))) for s in flex]; wsum = sum(weights) or 1.0
                for s, w in zip(flex, weights):
                    s["_len"] = max(0.4, remaining * w / wsum + float(s.get("xfade", 0.0)))
            else:
                last = shots[-1]; diff = total - sum(natural(s) - float(s.get("xfade", 0.0)) for s in shots)
                if diff > 0.02 and last.get("still"): last["len"] = round(natural(last) + diff, 3)
                elif diff > 0.02: last["hold"] = round(diff, 3)
                elif diff < -0.02 and not last.get("still"): last["out"] = round(float(last["out"]) + diff * float(last.get("speed", 1.0)), 3)
            first_idx = len(segs)
            for si, s in enumerate(shots):
                seg = {k: v for k, v in s.items() if k not in ("fixed", "flex", "weight", "_len", "ambient")}
                seg.setdefault("id", f"{bid}_{si}")
                if "_len" in s:
                    if s.get("still"): seg["len"] = round(s["_len"], 3)
                    else:
                        seg["speed"] = round((float(s["out"]) - float(s.get("in", 0))) / s["_len"], 4)
                        if not 0.5 <= seg["speed"] <= 4.0: self.log(f"  warning: beat {bid} shot {si} speed {seg['speed']} (source too short/long for the beat)")
                segs.append(seg)
                if s.get("ambient") and not s.get("still"):
                    amb.append({"src": s["src"], "in": float(s.get("in", 0)), "out": float(s["out"]), "t": f"{seg['id']}+0", "gain": float(s["ambient"])})
            if beat.get("vo"): vo.append({"id": beat["vo"], "t": f"{segs[first_idx]['id']}+{lead}", "tempo": tempo, **({"text": beat["text"]} if beat.get("text") else {})})
            if abs(sum((float(sg["len"]) if sg.get("still") else (float(sg["out"]) - float(sg.get("in", 0))) / float(sg.get("speed", 1.0))) + float(sg.get("hold", 0)) - float(sg.get("xfade", 0)) for sg in segs[first_idx:]) - total) > 0.08:
                self.log(f"  warning: beat {bid} shots do not add up to {total:.2f}s")
            for o in beat.get("overlays", []):
                o2 = {k: v for k, v in o.items() if k not in ("from", "to")}
                fr, to = self.mus(o.get("from", 0.0), tl), self.mus(o.get("to", 0.0), tl)
                o2["t"] = [f"beat:{bid}+{fr}" if fr >= 0 else f"beatend:{bid}-{-fr}", f"beatend:{bid}-{-to}" if to <= 0 else f"beat:{bid}+{to}"]
                ovs.append(o2)
            beats_meta.append({"id": bid, "first": segs[first_idx]["id"], "len": total, "vo_len": Lvo})
        a["vo"] = vo; a["ambient"] = amb
        return segs, ovs, a, beats_meta
    # ------------------------------------------------------------------ segment rendering
    def still_vf(self, seg, w, h, L):
        """Filter chain turning a looped still image into a w x h clip: fit (cover|contain|width), eased pan, eased zoom with focus."""
        FPS = self.FPS; F = max(1, int(round(L * FPS))); fit = seg.get("fit", "cover")
        z1 = float(seg.get("zoom", 1.06 if fit == "cover" else 1.0)); z0 = float(seg.get("zoom_from", 1.0)); zx, zy = seg.get("zoom_x", 0.5), seg.get("zoom_y", 0.5)
        p1, p0 = float(seg.get("pan", 0.0)), float(seg.get("pan_from", 0.0)); cx = seg.get("crop_x", 0.5); pad = seg.get("pad_color", "#000000").replace("#", "0x")
        W2, H2 = w * 2, h * 2; ease = f"(0.5-0.5*cos(PI*min(1\\,t/{L:.4f})))"
        if fit == "contain":
            base = f"scale={W2}:{H2}:force_original_aspect_ratio=decrease:flags=lanczos,pad={W2}:{H2}:'(ow-iw)/2':'(oh-ih)/2':color={pad}"
        elif fit == "width":
            base = f"scale={W2}:-2:flags=lanczos,pad={W2}:'max(ih\\,{H2})':0:0:color={pad},crop={W2}:{H2}:x=0:y='(ih-oh)*({p0}+({p1}-{p0})*{ease})'"
        else:
            base = f"scale={W2}:{H2}:force_original_aspect_ratio=increase:flags=lanczos,crop={W2}:{H2}:x='(iw-ow)*{cx}':y='(ih-oh)*({p0}+({p1}-{p0})*{ease})'"
        zoom = f"zoompan=z='{z0}+({z1}-{z0})*(0.5-0.5*cos(PI*min(1\\,on/{F})))':x='(iw-iw/zoom)*{zx}':y='(ih-ih/zoom)*{zy}':d=1:s={w}x{h}:fps={FPS}"
        return f"{base},{zoom},format=yuv420p"
    def render_segment(self, i, seg):
        out = self.TMP / f"seg{i:02d}.mp4"; src = self.resolve(seg["src"]); W, H, FPS = self.W, self.H, self.FPS
        if not src.exists(): raise FileNotFoundError(f"segment {i} ({seg.get('id')}): {src} missing")
        enc = ["-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p"]
        is_still = bool(seg.get("still")) or src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        frame = self.items.get(seg["frame"]) if seg.get("frame") else None
        if seg.get("frame") and not frame: raise KeyError(f"segment {i}: frame '{seg['frame']}' is not an overlays item")
        tw, th = (int(frame["w"]), int(frame["h"])) if frame else (W, H)
        if is_still:
            L = float(seg["len"]); target = self.TMP / f"seg{i:02d}_in.mp4" if frame else out
            _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(src), "-t", f"{L:.3f}", "-vf", self.still_vf(seg, tw, th, L), "-r", str(FPS)] + enc + [str(target)])
            if not frame: return out, _dur(out)
            src_v, t_in, t_out, speed, crop = target, 0.0, L, 1.0, False
        else:
            src_v, t_in, t_out, speed, crop = src, float(seg.get("in", 0)), float(seg.get("out") or _dur(src) - 0.05), float(seg.get("speed", 1.0)), True
        L = (t_out - t_in) / speed; cx, cy = seg.get("crop_x", 0.5), seg.get("crop_y", 0.5)
        fit_v = f"scale={tw}:{th}:force_original_aspect_ratio=increase:flags=lanczos,crop={tw}:{th}:x='(iw-ow)*{cx}':y='(ih-oh)*{cy}'" if crop else f"scale={tw}:{th}"
        if frame:
            fx, fy = int(frame["x"]), int(frame["y"])
            bg, mask = self.p.overlays_dir / f"{frame['id']}_bg.png", self.p.overlays_dir / f"{frame['id']}_mask.png"
            if not bg.exists(): raise FileNotFoundError(f"{bg} missing: run `overlays` first")
            fc = (f"[1:v]setpts=PTS/{speed},{fit_v},fps={FPS},format=rgba[v];[2:v]scale={tw}:{th},format=gray[m];[v][m]alphamerge[vm];"
                  f"[0:v]scale={W}:{H},format=rgba[bg];[bg][vm]overlay={fx}:{fy}:shortest=1,fps={FPS},format=yuv420p[o]")
            cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(bg), "-ss", str(t_in), "-to", str(t_out), "-i", str(src_v),
                   "-loop", "1", "-framerate", str(FPS), "-i", str(mask), "-filter_complex", fc, "-map", "[o]", "-t", f"{L:.3f}", "-an"] + enc + [str(out)]
        else:
            vf = f"setpts=PTS/{speed},{fit_v},fps={FPS},format=yuv420p"
            cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(t_in), "-to", str(t_out), "-i", str(src_v), "-vf", vf, "-an"] + enc + [str(out)]
        _run(cmd); Lr = _dur(out)
        if seg.get("hold"):
            out2 = self.TMP / f"seg{i:02d}h.mp4"
            _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(out), "-vf", f"tpad=stop_mode=clone:stop_duration={seg['hold']}"] + enc + [str(out2)]); out, Lr = out2, _dur(out2)
        return out, Lr
    # ------------------------------------------------------------------ build
    def build(self, out_name: str, burn_subs: bool = False):
        tl = self.p["timeline"]; W, H, FPS = self.W, self.H, self.FPS; B, TMP = self.B, self.TMP
        if tl.get("beats"): segs, ov_list, a, beats_meta = self.compile_beats(json.loads(json.dumps(tl)))
        else: segs, ov_list, a, beats_meta = tl["segments"], tl.get("overlays", []), tl["audio"], []
        paths, lens = [], []
        for i, s in enumerate(segs):
            p_, L = self.render_segment(i, s); paths.append(p_); lens.append(L)
        runs, cur = [], []
        for i, s in enumerate(segs):
            cur.append(i)
            if float(s.get("xfade", 0)) > 0 or i == len(segs) - 1: runs.append(cur); cur = []
        run_paths, run_lens = [], []
        for k, r in enumerate(runs):
            if len(r) == 1: run_paths.append(paths[r[0]]); run_lens.append(lens[r[0]]); continue
            lst = TMP / f"run{k:02d}.txt"; lst.write_text("".join(f"file '{paths[i]}'\n" for i in r)); outp = TMP / f"run{k:02d}.mp4"
            _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(outp)]); run_paths.append(outp); run_lens.append(_dur(outp))
        starts, total = [], 0.0
        for k, r in enumerate(runs):
            if k > 0: total -= float(segs[runs[k - 1][-1]].get("xfade", 0.0))
            t_ = total
            for i in r: starts.append(t_); t_ += lens[i]
            total += run_lens[k]
        names = {s.get("id", f"seg{i}"): i for i, s in enumerate(segs)}
        beat_t = {b["id"]: (starts[names[b["first"]]], starts[names[b["first"]]] + b["len"]) for b in beats_meta}
        vo_t = {}
        def T(v):
            if isinstance(v, (int, float)): return float(v)
            v = str(v).replace("+-", "-")
            if v == "end": return total
            m = re.match(r"^(?:(beat|beatend|vo|voend):)?([A-Za-z_][\w-]*)(?:([+-])(\d+(?:\.\d+)?(?:b|bar|bars|beats?)?))?$", v)
            if not m: raise ValueError(f"bad time ref: {v}")
            kind, ref, sign, off = m.group(1), m.group(2), m.group(3) or "+", self.mus(m.group(4) or 0)
            o = off if sign == "+" else -off
            if kind in ("beat", "beatend"): return beat_t[ref][0 if kind == "beat" else 1] + o
            if kind in ("vo", "voend"): return vo_t[ref][0 if kind == "vo" else 1] + o
            i = int(ref[3:]) if ref.startswith("seg") and ref[3:].isdigit() else names[ref]
            return starts[i] + o if sign == "+" else starts[i] + lens[i] + o
        for i in range(len(segs)): self.log(f"  {i:02d} {segs[i].get('id', ''):<16} {segs[i]['src'][-26:]:>26} start={starts[i]:6.2f} len={lens[i]:5.2f} x{float(segs[i].get('speed', 1)):.2f} xfade={segs[i].get('xfade', 0)}")
        self.log(f"  TOTAL {total:.2f}s")
        # ---- VO placement first (overlays and captions may reference it)
        vo_items = []; prev_end = 0.0
        for v in a.get("vo", []):
            src = self.vo_path(v); tempo = float(v.get("tempo", a.get("vo_tempo", 1.0))); L = _dur(src) / tempo
            t0 = prev_end + float(v["after"]) if "after" in v else T(v["t"])
            key = v.get("id") or pathlib.Path(v["src"]).stem; vo_t[key] = (t0, t0 + L); prev_end = t0 + L
            vo_items.append({**v, "_src": src, "_t0": t0, "_len": L, "_tempo": tempo})
        for x, y in zip(vo_items, vo_items[1:]):
            if x["_t0"] + x["_len"] > y["_t0"] + 0.01: self.log(f"  warning: VO {x.get('id')} overlaps {y.get('id')} by {x['_t0'] + x['_len'] - y['_t0']:.2f}s")
        json.dump({"starts": starts, "lens": lens, "total": total, "vo": {k: list(v) for k, v in vo_t.items()}, "beats": {k: list(v) for k, v in beat_t.items()}}, open(B / "timing.json", "w"), indent=1)
        # ---- video chain
        inputs, fc = [], []
        for p_ in run_paths: inputs += ["-i", str(p_)]
        n = len(run_paths); cur = "[0:v]"; off = run_lens[0]
        for k in range(1, n):
            last = segs[runs[k - 1][-1]]; d = float(last.get("xfade", 0.0)); kind = last.get("xfade_kind", "fade")
            fc.append(f"{cur}[{k}:v]xfade=transition={kind}:duration={d:.4f}:offset={off-d:.4f}[v{k}]"); cur = f"[v{k}]"; off = off - d + run_lens[k]
        k = n
        for o in ov_list:
            png = self.p.overlays_dir / f"{o['id']}.png" if "id" in o else self.p.path(o["png"])
            if not png.exists(): self.log(f"  overlay {png.name} missing, skipped"); continue
            tin, tout = max(0.0, T(o["t"][0])), min(total, T(o["t"][1])); fd = float(o.get("fade", 0.4)); slide = o.get("slide", 0)
            if tout - tin < 2 * fd: fd = max(0.05, (tout - tin) / 3)
            inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", str(png)]
            fade_in = f"fade=t=in:st={tin}:d={fd}:alpha=1," if tin > 0.01 or o.get("fade_first") else ""
            fc.append(f"[{k}:v]format=rgba,{fade_in}fade=t=out:st={tout-fd}:d={fd}:alpha=1[o{k}]")
            yexpr = f"{slide}*(1-min(1,(t-{tin})/{fd}))" if slide else "0"
            fc.append(f"{cur}[o{k}]overlay=x=0:y='{yexpr}':enable='between(t,{tin},{tout})'[v{k}]"); cur = f"[v{k}]"; k += 1
        cap = self.p.get("captions", {}) or {}
        srt, ass = self.write_captions(vo_items, total, cap)
        if burn_subs and (ass or srt):
            fontsdir = self.fonts_static_dir(cap)
            if ass: fc.append(f"{cur}ass='{ass}':fontsdir='{fontsdir}'[vs]")
            else:
                st = cap.get("style") or tl.get("subtitle_style", "FontName=DM Sans,FontSize=14,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H60000000,BorderStyle=1,Outline=1.0,Shadow=0.5,MarginV=46,MarginL=60,MarginR=60")
                fc.append(f"{cur}subtitles='{srt}':fontsdir='{fontsdir}':force_style='{st}'[vs]")
            cur = "[vs]"
        fc.append(f"{cur}format=yuv420p[vout]")
        # ---- audio
        aidx = k; vo = []
        for v in vo_items:
            inputs += ["-i", str(v["_src"])]; ms = int(v["_t0"] * 1000)
            tempo = f"atempo={v['_tempo']}," if abs(v["_tempo"] - 1.0) > 1e-3 else ""
            fc.append(f"[{aidx}:a]aresample=48000,aformat=channel_layouts=stereo,{tempo}adelay={ms}|{ms},volume={v.get('gain', 1.0)}[vo{aidx}]"); vo.append(f"[vo{aidx}]"); aidx += 1
        if vo: fc.append("".join(vo) + f"amix=inputs={len(vo)}:normalize=0[vo]")
        else: self.log("  no voice-over: music-driven edit")
        amb = []
        for v in a.get("ambient", []):
            src = self.resolve(v["src"]); inputs += ["-ss", str(v.get("in", 0)), "-to", str(v["out"]), "-i", str(src)]; ms = int(max(0.0, T(v["t"])) * 1000); L = float(v["out"]) - float(v.get("in", 0))
            fc.append(f"[{aidx}:a]aresample=48000,aformat=channel_layouts=stereo,afade=t=in:d=0.4,afade=t=out:st={max(0, L-0.6)}:d=0.6,volume={v.get('gain', 0.3)},adelay={ms}|{ms}[am{aidx}]"); amb.append(f"[am{aidx}]"); aidx += 1
        if amb: fc.append("".join(amb) + f"amix=inputs={len(amb)}:normalize=0[amb]")
        m = a.get("music") or self.p.get("music"); mix = []
        if m and not self.p.path(m["src"]).exists():
            self.log(f"  music {m['src']} not found: building without music"); m = None
        if vo: fc.append("[vo]asplit=2[vo1][vo2]"); mix.append("[vo1]")
        if m:
            inputs += ["-i", str(self.p.path(m["src"]))]; fo = float(m.get("fade_out", 2.5))
            fc.append(f"[{aidx}:a]atrim=start={m.get('in', 0)}:end={float(m.get('in', 0))+total+1},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,volume={m.get('gain', 0.5)},afade=t=in:d={m.get('fade_in', 1.5)},afade=t=out:st={max(0, total-fo)}:d={fo}[mus]"); aidx += 1
            if vo: fc.append(f"[mus][vo2]sidechaincompress=threshold={m.get('sc_thresh', 0.02)}:ratio={m.get('sc_ratio', 6)}:attack=40:release=600:makeup=1[musd]"); mix.insert(0, "[musd]")
            else: mix.insert(0, "[mus]")
        elif vo: fc.append("[vo2]anullsink")
        if amb: mix.append("[amb]")
        if not mix:
            inputs += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]; mix.append(f"[{aidx}:a]"); aidx += 1
        fc.append("".join(mix) + (f"amix=inputs={len(mix)}:normalize=0," if len(mix) > 1 else "") + f"loudnorm=I=-16:TP=-1.5:LRA=11,atrim=0:{total},asetpts=PTS-STARTPTS[aout]")
        (B / "filter.txt").write_text(";\n".join(fc)); out = B / out_name
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + inputs + ["-filter_complex_script", str(B / "filter.txt"), "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)]
        self.log("  encoding..."); _run(cmd); self.log(f"  OK {out} ({_dur(out):.2f}s)"); return out
    # ------------------------------------------------------------------ captions
    def fonts_static_dir(self, cap) -> pathlib.Path:
        d = self.B / "fonts"; d.mkdir(exist_ok=True)
        fonts = self.p.get("overlays", {}).get("fonts", {}); src_dir = self.p.path(fonts.get("dir", "assets/fonts"))
        for f in src_dir.glob("*.ttf"): 
            dst = d / f.name
            if not dst.exists(): dst.write_bytes(f.read_bytes())
        font_file = cap.get("font_file")
        if font_file:
            family = cap.get("font", "Promokit Caption"); dst = d / (family.replace(" ", "") + ".ttf")
            if not dst.exists(): static_instance(self.p.path(font_file), dst, family, int(cap.get("weight", 700)))
        return d
    @staticmethod
    def speech_pauses(path, noise=-35, min_d=0.12):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", f"silencedetect=noise={noise}dB:d={min_d}", "-f", "null", "-"], capture_output=True, text=True).stderr
        st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r)]; en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r)]
        return list(zip(st, en + [None] * (len(st) - len(en))))
    PHRASE_SPLIT = re.compile(r"(?<=[,.;:?!…])\s+")
    @staticmethod
    def tokens(phrase, keep=()):
        out = []
        for w in phrase.split():
            if out and re.fullmatch(r"[?!:;»…%]+", w): out[-1] += "\u00a0" + w     # French spacing: keep "plus ?" together
            else: out.append(w)
        for k in sorted(keep, key=len, reverse=True):                            # never split brand names / amounts across cues
            kw = [x.lower() for x in k.split()]; n = len(kw); i = 0
            if n < 2: continue
            while i + n <= len(out):
                if [re.sub(r"[,.;:?!…]+$", "", x.replace("\u00a0", " ").split(" ")[0]).lower() for x in out[i:i + n]] == kw:
                    out[i:i + n] = ["\u00a0".join(out[i:i + n])]
                i += 1
        return out
    def word_times(self, path, text, tempo, display=None):
        """Per-word (word, start, end, phrase_idx), tempo-adjusted. Phrase breaks of the spoken text are anchored to detected pauses;
        words of the displayed text are spread inside each phrase proportionally to their length."""
        D = _dur(path); pauses = self.speech_pauses(path)
        s0 = pauses[0][1] if pauses and pauses[0][0] < 0.05 and pauses[0][1] else 0.0
        s1 = pauses[-1][0] if pauses and (pauses[-1][1] is None or pauses[-1][1] >= D - 0.05) else D
        inner = [((a + b) / 2, a, b) for a, b in pauses if b is not None and a > s0 + 0.05 and b < s1 - 0.05]
        phrases = [p.strip() for p in self.PHRASE_SPLIT.split(text) if p.strip()]
        shown = [p.strip() for p in self.PHRASE_SPLIT.split(display) if p.strip()] if display else phrases
        if len(shown) != len(phrases): shown = phrases if not display else [display]; phrases = phrases if not display else [text]
        lens = [len(p) for p in phrases]; tot = sum(lens) or 1
        bounds, acc = [], 0
        for L in lens[:-1]: acc += L; bounds.append(s0 + (s1 - s0) * acc / tot)
        assigned = [None] * len(bounds); used = set()
        for bi, e in enumerate(bounds):
            prev = max([x for x in assigned[:bi] if x is not None], default=-1)
            best = min(((abs(mid - e), j) for j, (mid, a, b) in enumerate(inner) if j not in used and j > prev), default=None)
            if best and best[0] < 0.9: assigned[bi] = best[1]; used.add(best[1])
        edges = [(s0, s0)]
        for bi, e in enumerate(bounds):
            if assigned[bi] is not None: _, a, b = inner[assigned[bi]]; edges.append((a, b))
            else: edges.append((e, e))
        edges.append((s1, s1))
        words = []
        for pi, ph in enumerate(shown):
            start, end = edges[pi][1], edges[pi + 1][0]
            if end - start < 0.15: end = start + 0.15
            ws = self.tokens(ph, self.p.get("captions", {}).get("keep", [])); wl = [len(w) + 1 for w in ws]; wt = sum(wl) or 1; t = start
            for w, l in zip(ws, wl):
                d = (end - start) * l / wt; words.append((w, t / tempo, (t + d) / tempo, pi)); t += d
        return words
    def write_captions(self, vo_items, total, cap):
        script = {s["id"]: s for s in self.p.get("script", [])}; mode = cap.get("mode", "lines")
        def ts(x): h = int(x // 3600); m_ = int(x % 3600 // 60); s = x % 60; return f"{h:02d}:{m_:02d}:{int(s):02d},{int(round((s-int(s))*1000)):03d}"
        def ta(x): h = int(x // 3600); m_ = int(x % 3600 // 60); s = x % 60; return f"{h}:{m_:02d}:{s:05.2f}"
        cues, word_events = [], []
        for v in vo_items:
            sc = script.get(v.get("id"), {}); spoken = sc.get("text", ""); text = v.get("text") or sc.get("display") or spoken
            if not text: continue
            if mode == "words":
                ws = self.word_times(v["_src"], spoken or text, v["_tempo"], display=text if text != spoken else None); t0 = v["_t0"]
                maxw, maxc, min_d = int(cap.get("max_words", 3)), int(cap.get("max_chars", 18)), float(cap.get("min_duration", 0.45)); chunks = []; chunk = []
                for w in ws:
                    if chunk and (len(chunk) >= maxw or len(" ".join(x[0] for x in chunk)) + 1 + len(w[0]) > maxc or w[3] != chunk[-1][3]): chunks.append(chunk); chunk = []
                    chunk.append(w)
                if chunk: chunks.append(chunk)
                merged = True
                while merged and len(chunks) > 1:      # merge too-short chunks into a neighbour (readability beats strict limits)
                    merged = False
                    for ci, ch in enumerate(chunks):
                        if ch[-1][2] - ch[0][1] >= min_d: continue
                        cand = []
                        if ci > 0: cand.append((len(" ".join(x[0] for x in chunks[ci - 1] + ch)), ci - 1))
                        if ci + 1 < len(chunks): cand.append((len(" ".join(x[0] for x in ch + chunks[ci + 1])), ci))
                        cand = [c for c in cand if c[0] <= maxc + 9]
                        if not cand: continue
                        _, j = min(cand); chunks[j:j + 2] = [chunks[j] + chunks[j + 1]]; merged = True; break
                for ch in chunks: word_events.append([(w, t0 + a, t0 + b) for w, a, b, _ in ch])
            else:
                t0 = v["_t0"]; t1 = t0 + v["_len"]
                parts = [x.strip() for x in re.split(r'(?<=[.?!])\s+|(?<=\.\.\.)\s+|(?<=:)\s+', text) if x.strip()]; chunks, cur = [], ""
                for x in parts:
                    if cur and len(cur) + len(x) + 1 > 62: chunks.append(cur); cur = x
                    else: cur = (cur + " " + x).strip()
                if cur: chunks.append(cur)
                tot = sum(len(c) for c in chunks); t = t0
                for c in chunks: d = (t1 - t0) * len(c) / tot; cues.append((t, min(t + d, t1), c)); t += d
        if mode == "words":
            for i, ev in enumerate(word_events):   # extend each chunk to the next one when the gap is short (no flicker)
                nxt = word_events[i + 1][0][1] if i + 1 < len(word_events) else None
                if nxt is not None and 0 < nxt - ev[-1][2] < 0.35: ev[-1] = (ev[-1][0], ev[-1][1], nxt)
                cues.append((ev[0][1], ev[-1][2], " ".join(w for w, _, _ in ev)))
        if not cues: return None, None
        srt = self.B / "subtitles.srt"; srt.write_text("\n".join(f"{i+1}\n{ts(a)} --> {ts(b)}\n{c}\n" for i, (a, b, c) in enumerate(cues)))
        if mode != "words": return srt, None
        caps = bool(cap.get("caps", True)); font = cap.get("font", "Promokit Caption"); size = int(cap.get("size", 76))
        col, hi, outl = _hex_ass(cap.get("color", "#FFFFFF")), _hex_ass(cap.get("highlight", "#FFD84D")), _hex_ass(cap.get("outline_color", "#000000"))
        y = int(cap.get("y", int(self.H * 0.75))); marginv = self.H - y
        head = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {self.W}", f"PlayResY: {self.H}", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
                "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                f"Style: Cap,{font},{size},{col},{col},{outl},&H80000000,0,0,0,0,100,100,{cap.get('spacing', 1)},0,1,{cap.get('outline', 6)},{cap.get('shadow', 3)},2,{cap.get('margin_x', 110)},{cap.get('margin_x', 110)},{marginv},1", "",
                "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
        lines = []
        for ev in word_events:
            words = [w.upper() if caps else w for w, _, _ in ev]; end = ev[-1][2]
            for j, (w, a, b) in enumerate(ev):
                e = ev[j + 1][1] if j + 1 < len(ev) else end
                txt = " ".join((f"{{\\c{hi}}}{x}{{\\c{col}}}" if k2 == j else x) for k2, x in enumerate(words))
                pop = "{\\fscx108\\fscy108\\t(0,90,\\fscx100\\fscy100)}" if j == 0 and cap.get("pop", True) else ""
                lines.append(f"Dialogue: 0,{ta(a)},{ta(max(e, a + 0.05))},Cap,,0,0,0,,{pop}{txt}")
        ass = self.B / "captions.ass"; ass.write_text("\n".join(head + lines) + "\n"); return srt, ass

def static_instance(src, dst, family, weight=700):
    """Instantiate a variable font at `weight` with a unique family name (so libass picks it without faux bold)."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    f = TTFont(str(src))
    if "fvar" in f: f = instancer.instantiateVariableFont(f, {"wght": weight})
    name = f["name"]; ps = family.replace(" ", "")
    for rec in list(name.names):
        if rec.nameID in (1, 2, 3, 4, 6, 16, 17): name.removeNames(nameID=rec.nameID)
    for nid, val in ((1, family), (2, "Regular"), (3, ps + "-promokit"), (4, family), (6, ps)): name.setName(val, nid, 3, 1, 0x409); name.setName(val, nid, 1, 0, 0)
    if "OS/2" in f: f["OS/2"].usWeightClass = 400
    f.save(str(dst))

def proxies(project, master: pathlib.Path, log=print):
    portrait = project.portrait
    for name, short, crf in (("720p", 720, 23), ("480p", 480, 26)):
        out = master.with_name(master.stem + f"_{name}.mp4"); scale = f"{short}:-2" if portrait else f"-2:{short}"
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(master), "-vf", f"scale={scale}", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(out)]); log(f"  proxy {out.name}")
