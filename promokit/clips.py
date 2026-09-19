"""MiniMax H3 clips: draft (768P) with cache, optional 2K regeneration for approved clips, frame references between clips."""
from __future__ import annotations
import json, pathlib, shutil, subprocess
from .cache import key_of, file_hash

RES_ORDER = ["2K", "768P", "480P"]

def clip_defaults(project, clip):
    d = dict(project["clips_defaults"]); d.update({k: v for k, v in clip.items() if k in ("model", "ratio", "draft_resolution", "final_resolution")}); return d

def prompt_text(project, clip) -> str:
    if "prompt" in clip: return clip["prompt"].strip()
    return project.path(clip["prompt_file"]).read_text().strip()

def best_file(project, clip_id: str):
    """Best available rendition on disk (2K > 768P > 480P)."""
    for res in RES_ORDER:
        p = project.dir / "clips" / f"{clip_id}_{res}.mp4"
        if p.exists(): return p, res
    return None, None

def extract_frame(video, t: float, out):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1", str(out)], check=True); return out

def resolve_refs(project, clip):
    """Returns list of (role, path) or raises if a frame dependency is not generated yet.
    refs: {role, frame: {clip, t}} (frame of another clip) | {role, overlay: <id>} (rendered overlay PNG) | {role, path}."""
    refs = []
    for r in clip.get("refs", []):
        role = r.get("role", "reference_image")
        if "frame" in r:
            src_id = r["frame"]["clip"]; t = float(r["frame"].get("t", 1.0))
            src_clip = next((c for c in project.get("clips", []) if c["id"] == src_id), {})
            draft = project.dir / "clips" / f"{src_id}_{clip_defaults(project, src_clip)['draft_resolution']}.mp4"
            vid, res = (draft, "draft") if draft.exists() else best_file(project, src_id)
            if not vid: raise LookupError(f"clip {clip['id']} needs a frame of clip {src_id}, which is not generated yet")
            out = project.dir / "clips" / f"{src_id}_frame_{t:.2f}.png"
            if not out.exists(): extract_frame(vid, t, out)
            refs.append((role, out))
        elif "overlay" in r:   # a promokit-rendered still (title card, diagram) as first_frame / reference_image: designed by the kit, animated by H3
            png = project.overlays_dir / f"{r['overlay']}.png"
            if not png.exists():
                from .overlays import Painter
                Painter(project).render(only=[r["overlay"]], log=lambda *a: None)
            if not png.exists(): raise LookupError(f"clip {clip['id']}: overlay '{r['overlay']}' is not an overlays item (or is a device_frame)")
            refs.append((role, png))
        else:
            refs.append((role, project.path(r["path"])))
    return refs

def draft_request(project, clip, refs):
    d = clip_defaults(project, clip)
    return {"kind": "video", "model": d["model"], "resolution": d["draft_resolution"], "duration": int(clip["duration"]), "ratio": d["ratio"],
            "prompt": prompt_text(project, clip), "refs": [(role, file_hash(p)) for role, p in refs]}

def plan(project, cache, pricing, tier="draft"):
    rows = []
    for clip in project.get("clips", []):
        d = clip_defaults(project, clip); n_ref = len(clip.get("refs", []))
        try: refs = resolve_refs(project, clip); req = draft_request(project, clip, refs); hit = cache.get("video", key_of(req)); dep = None
        except LookupError as e: hit = None; dep = str(e)
        row = {"id": clip["id"], "seconds": int(clip["duration"]), "draft_cached": bool(hit), "dep": dep,
               "est_draft_usd": 0.0 if hit else pricing.video(d["model"], d["draft_resolution"], clip["duration"], n_ref)}
        if tier == "final":
            f = project.dir / "clips" / f"{clip['id']}_{d['final_resolution']}.mp4"
            row["approved"] = bool(clip.get("approve")); row["final_cached"] = f.exists()
            row["est_final_usd"] = 0.0 if (f.exists() or not clip.get("approve")) else pricing.regen(clip["duration"])
        rows.append(row)
    return rows

def generate(project, mm, cache, guard, ledger, pricing, only=None, force=False, log=print):
    """Draft-tier generation with dependency ordering (frame refs)."""
    clips = [c for c in project.get("clips", []) if not only or c["id"] in only]
    pending = list(clips); results = {}; n_paid = 0; cap = int(project["budget"]["max_clips_per_run"])
    while pending:
        progressed = False
        for clip in list(pending):
            d = clip_defaults(project, clip); res = d["draft_resolution"]; out = project.dir / "clips" / f"{clip['id']}_{res}.mp4"
            try: refs = resolve_refs(project, clip)
            except LookupError: continue
            req = draft_request(project, clip, refs); key = key_of(req)
            hit = None if force else cache.get("video", key)
            if hit:
                if not out.exists(): shutil.copy2(hit["path"], out)
                meta_out = out.with_suffix(".json"); meta_out.write_text(json.dumps(hit["meta"], indent=1))
                results[clip["id"]] = {"path": str(out), "cached": True, "task_id": hit["meta"].get("task_id")}; log(f"  clip {clip['id']}: cached ({res})")
                pending.remove(clip); progressed = True; continue
            if n_paid >= cap: raise RuntimeError(f"max_clips_per_run={cap} reached; re-run to continue")
            est = pricing.video(d["model"], res, clip["duration"], len(refs)); guard.check(est, f"H3 clip {clip['id']} {res} {clip['duration']}s")
            rid = ledger.open("video", {"clip": clip["id"], "model": d["model"], "resolution": res, "seconds": clip["duration"], "refs": len(refs)}, est)
            try:
                log(f"  clip {clip['id']}: generating {res} {clip['duration']}s (~${est:.2f})...")
                tid = mm.video_create(req["prompt"], clip["duration"], res, d["ratio"], d["model"], images=[(r, str(p)) for r, p in refs])
                j = mm.video_wait(tid, out, log=log); usage = j.get("task", {}).get("usage", {})
                actual = pricing.video(d["model"], res, float(usage.get("output_seconds", clip["duration"])), int(usage.get("input_image_count", len(refs))))
                ledger.close(rid, "done", actual, usage); n_paid += 1
                meta = {"request": {k: v for k, v in req.items() if k != "prompt"}, "prompt": req["prompt"], "task_id": tid, "usage": usage, "clip": clip["id"]}
                cache.put("video", key, out, meta); out.with_suffix(".json").write_text(json.dumps(meta, indent=1))
                results[clip["id"]] = {"path": str(out), "cached": False, "task_id": tid, "usd": actual}; log(f"  clip {clip['id']}: done (~${actual:.2f})")
            except Exception:
                ledger.close(rid, "failed"); raise
            pending.remove(clip); progressed = True
        if not progressed:
            raise RuntimeError("unresolvable clip dependencies: " + ", ".join(c["id"] for c in pending))
    return results

def upscale(project, mm, cache, guard, ledger, pricing, only=None, force=False, log=print):
    """2K regeneration for clips marked approve: true (or listed in --only)."""
    results = {}
    for clip in project.get("clips", []):
        if only and clip["id"] not in only: continue
        if not only and not clip.get("approve"): continue
        d = clip_defaults(project, clip); final = d["final_resolution"]; out = project.dir / "clips" / f"{clip['id']}_{final}.mp4"
        if out.exists() and not force: results[clip["id"]] = {"path": str(out), "cached": True}; log(f"  upscale {clip['id']}: already {final}"); continue
        draft = project.dir / "clips" / f"{clip['id']}_{d['draft_resolution']}.mp4"; meta_p = draft.with_suffix(".json")
        if not (draft.exists() and meta_p.exists()): raise LookupError(f"clip {clip['id']}: draft not generated yet (run `clips` first)")
        tid_src = json.loads(meta_p.read_text()).get("task_id")
        req = {"kind": "regen", "source_task_id": tid_src, "resolution": final}; key = key_of(req); hit = None if force else cache.get("regen", key)
        if hit: shutil.copy2(hit["path"], out); results[clip["id"]] = {"path": str(out), "cached": True}; log(f"  upscale {clip['id']}: cached"); continue
        est = pricing.regen(clip["duration"]); guard.check(est, f"2K regeneration {clip['id']} {clip['duration']}s")
        rid = ledger.open("regen", {"clip": clip["id"], "seconds": clip["duration"], "source_task_id": tid_src}, est)
        try:
            log(f"  upscale {clip['id']}: regenerating {final} (~${est:.2f})...")
            tid = mm.video_regenerate(tid_src, final, d["model"]); j = mm.video_wait(tid, out, log=log); usage = j.get("task", {}).get("usage", {})
            actual = pricing.regen(float(usage.get("output_seconds", clip["duration"]))); ledger.close(rid, "done", actual, usage)
            cache.put("regen", key, out, {"request": req, "task_id": tid, "usage": usage, "clip": clip["id"]})
            results[clip["id"]] = {"path": str(out), "cached": False, "usd": actual}; log(f"  upscale {clip['id']}: done (~${actual:.2f})")
        except Exception:
            ledger.close(rid, "failed"); raise
    return results
