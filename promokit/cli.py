"""promokit CLI. Every paid stage is dry by default: it prints the cost plan and stops unless --yes is given,
and it never exceeds budget.max_usd / per_call_max_usd from project.yaml."""
from __future__ import annotations
import argparse, asyncio, json, pathlib, shutil, sys
from .config import Project
from .pricing import Pricing
from .ledger import Ledger, BudgetGuard, BudgetExceeded, ConfirmationRequired
from .cache import Cache, key_of
from . import voice, clips as clipmod, overlays as ovmod, assemble as asm

KIT = pathlib.Path(__file__).resolve().parents[1]

_VARIANT = None
def _project(arg) -> Project:
    p = pathlib.Path(arg)
    if not p.exists():
        p = KIT / "projects" / arg
        if not p.exists() and (KIT / "examples" / arg).exists(): p = KIT / "examples" / arg
    return Project(p, _VARIANT)

def _ctx(project: Project, yes: bool):
    pricing = Pricing(project.get("pricing")); cache = Cache(project.cache_dir); ledger = Ledger(project.ledger_file, project.name)
    b = project["budget"]; guard = BudgetGuard(ledger, b["max_usd"], b["per_call_max_usd"], yes)
    return pricing, cache, ledger, guard

def _mm():
    from .minimax import MiniMax
    return MiniMax()

def cmd_init(a):
    dst = KIT / "projects" / a.name
    if dst.exists(): sys.exit(f"{dst} already exists")
    shutil.copytree(KIT / "templates" / "project", dst)
    y = dst / "project.yaml"; s = y.read_text().replace("__NAME__", a.name).replace("__URL__", a.url or "https://example.com"); y.write_text(s)
    print(f"created {dst}\n  1) edit {y}\n  2) promokit plan {a.name}\n  3) promokit run {a.name} --yes")

def cmd_check(a):
    ok = True
    for tool in ("ffmpeg", "ffprobe"):
        print(f"  {tool}: {'ok' if shutil.which(tool) else 'MISSING'}"); ok &= bool(shutil.which(tool))
    try:
        import playwright; print("  playwright: ok")
    except ImportError: print("  playwright: MISSING (pip install playwright && playwright install chromium)"); ok = False
    if a.project:
        p = _project(a.project); print(f"  project: {p.name} ({p.file})"); print(f"  .env: {p.env_file or 'not found'}")
    try:
        mm = _mm(); v = mm.voices("voice_cloning"); names = [x["voice_id"] for x in (v.get("voice_cloning") or [])]
        print(f"  MiniMax API: ok, cloned voices: {names or 'none'}")
    except Exception as e: print(f"  MiniMax API: {str(e)[:120]}"); ok = False
    print("OK" if ok else "some checks failed")

def cmd_voices(a):
    v = _mm().voices("voice_cloning")
    for x in (v.get("voice_cloning") or []): print(f"  {x['voice_id']}  created {x.get('created_time')}  {x.get('voice_name') or ''}")
    if not v.get("voice_cloning"): print("  no cloned voice on this account (cloning costs $1.5/voice, do it once via the MiniMax console)")

def _plan(project, pricing, cache, guard):
    rows_vo = voice.plan(project, cache, pricing); rows_cl = clipmod.plan(project, cache, pricing, tier="final")
    tot_vo = sum(r["est_usd"] for r in rows_vo); tot_draft = sum(r["est_draft_usd"] for r in rows_cl); tot_final = sum(r.get("est_final_usd", 0) for r in rows_cl)
    print(f"\nPROJECT {project.label}   budget: {guard.status()}")
    print(f"\nVoiceover ({project['voice'].get('voice_id') or 'NO VOICE_ID: set voice.voice_id or PROMOKIT_VOICE_ID'}, {project['voice']['model']}):")
    for r in rows_vo: print(f"  {r['id']:<16} {r['chars']:4d} chars  {'cached' if r['cached'] else f'~${r['est_usd']:.3f}'}")
    print("\nH3 clips (draft 768P -> optional 2K regeneration for approve: true):")
    for r in rows_cl:
        d = "cached" if r["draft_cached"] else f"~${r['est_draft_usd']:.2f}"
        f = "cached" if r.get("final_cached") else (f"~${r['est_final_usd']:.2f}" if r.get("approved") else "not approved")
        dep = f"  (waits for: {r['dep'][:60]})" if r["dep"] else ""
        print(f"  {r['id']:<16} {r['seconds']:2d}s  draft {d:<8} 2K {f}{dep}")
    print(f"\nESTIMATED SPEND if you run everything now: vo ${tot_vo:.2f} + drafts ${tot_draft:.2f} + 2K ${tot_final:.2f} = ${tot_vo+tot_draft+tot_final:.2f}")
    print(f"Already spent on this project (ledger): ${guard.ledger.spent(project.name):.2f}; cap ${guard.max_usd:.2f}")
    return tot_vo + tot_draft + tot_final

def cmd_plan(a):
    p = _project(a.project); pricing, cache, ledger, guard = _ctx(p, False); _plan(p, pricing, cache, guard)

def _paid(fn, a, what):
    p = _project(a.project); pricing, cache, ledger, guard = _ctx(p, a.yes)
    if not a.yes: _plan(p, pricing, cache, guard); print(f"\nDry run: nothing spent. Add --yes to actually run `{what}`."); return
    try: fn(p, _mm(), cache, guard, ledger, pricing, only=a.only, **({"force": a.force} if hasattr(a, "force") else {}))
    except (BudgetExceeded, ConfirmationRequired) as e: sys.exit(f"STOPPED: {e}")

def cmd_vo(a): _paid(voice.generate, a, "vo")
def cmd_clips(a): _paid(clipmod.generate, a, "clips")
def cmd_upscale(a): _paid(clipmod.upscale, a, "upscale")

def cmd_screens(a):
    p = _project(a.project); s = p.get("screens", {}); base = s.get("base_url") or p["site"]["url"]
    from .screens.actions import run_all
    asyncio.run(run_all(s.get("scenes", {}), s.get("captures", []), base.rstrip("/"), p.screens_out, only=a.only, width=p["video"]["width"], height=p["video"]["height"], fps=p["video"]["fps"], viewport=s.get("viewport")))

def cmd_overlays(a):
    p = _project(a.project); ovmod.Painter(p).render(only=a.only)

def cmd_assemble(a):
    p = _project(a.project); A = asm.Assembler(p); name = a.out or p.get("output", {}).get("name", f"{p.label.replace(':', '_')}.mp4")
    burn_default = bool(p.get("captions", {}).get("burn", False))
    out = A.build(name, burn_subs=burn_default)
    if a.sub and not burn_default: A.build(pathlib.Path(name).stem + "_sub.mp4", burn_subs=True)
    if a.proxies: asm.proxies(p, out)
    print(f"\nDONE: {out}")

def cmd_run(a):
    p = _project(a.project); pricing, cache, ledger, guard = _ctx(p, a.yes); est = _plan(p, pricing, cache, guard)
    if est > 0 and not a.yes: print("\nDry run: paid stages skipped. Re-run with --yes to spend the estimate above (within the budget cap)."); return
    if est > 0 and guard.ledger.spent(p.name) + est > guard.max_usd: sys.exit(f"STOPPED before spending: estimate ${est:.2f} would exceed budget.max_usd={guard.max_usd:.2f}")
    mm = _mm() if est > 0 else None
    try:
        print("\n[1/6] voiceover"); voice.generate(p, mm, cache, guard, ledger, pricing)
        print("[2/6] clips (draft)"); clipmod.generate(p, mm, cache, guard, ledger, pricing)
        print("[3/6] screens"); cmd_screens(argparse.Namespace(project=a.project, only=None))
        print("[4/6] overlays"); ovmod.Painter(p).render()
        if not a.skip_upscale: print("[5/6] 2K upscale (approved clips)"); clipmod.upscale(p, mm, cache, guard, ledger, pricing)
        else: print("[5/6] 2K upscale skipped")
        print("[6/6] assemble"); cmd_assemble(argparse.Namespace(project=a.project, out=a.out, sub=a.sub, proxies=a.proxies))
    except (BudgetExceeded, ConfirmationRequired) as e: sys.exit(f"STOPPED: {e}")
    print(f"\nbudget: {guard.status()}")

def cmd_ledger(a):
    lp = _project(a.project).ledger_file if a.project else KIT / "ledger.jsonl"; L = Ledger(lp, a.project or "")
    recs = L.records(_project(a.project).name if a.project else None); tot = 0.0
    for r in recs:
        usd = r.get("actual_usd", r.get("est_usd", 0)); tot += usd
        print(f"  {r['ts']}  {r['project']:<14} {r['kind']:<6} {r['status']:<8} ${usd:6.3f}  {json.dumps(r.get('detail'), ensure_ascii=False)[:80]}")
    print(f"  TOTAL ${tot:.2f}  ({len(recs)} records) in {lp}")

def cmd_cache_import(a):
    """Register already-generated files (vo/*.mp3, clips/*_768P.mp4 + .json, clips/*_2K.mp4) so they are never paid again."""
    p = _project(a.project); pricing, cache, ledger, guard = _ctx(p, False); n = 0; usd = 0.0
    for seg in p.get("script", []):
        f = p.dir / "vo" / f"{seg['id']}.mp3"
        if f.exists():
            req = voice._req(p, seg); k = key_of(req)
            if not cache.get("tts", k): cache.put("tts", k, f, {"request": req, "segment": seg["id"], "imported": True}); n += 1; usd += pricing.tts(req["model"], len(seg["text"]))
    for clip in p.get("clips", []):
        d = clipmod.clip_defaults(p, clip); f = p.dir / "clips" / f"{clip['id']}_{d['draft_resolution']}.mp4"; meta_p = f.with_suffix(".json")
        if f.exists():
            try: refs = clipmod.resolve_refs(p, clip)
            except LookupError as e: print(f"  skip {clip['id']}: {e}"); continue
            req = clipmod.draft_request(p, clip, refs); k = key_of(req); meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
            if not cache.get("video", k):
                cache.put("video", k, f, {"request": {x: y for x, y in req.items() if x != "prompt"}, "prompt": req["prompt"], "task_id": meta.get("task_id"), "usage": meta.get("usage", {}), "clip": clip["id"], "imported": True}); n += 1
                usd += pricing.video(d["model"], d["draft_resolution"], clip["duration"], len(refs))
            f2 = p.dir / "clips" / f"{clip['id']}_{d['final_resolution']}.mp4"
            if f2.exists() and meta.get("task_id"):
                k2 = key_of({"kind": "regen", "source_task_id": meta["task_id"], "resolution": d["final_resolution"]})
                if not cache.get("regen", k2): cache.put("regen", k2, f2, {"clip": clip["id"], "imported": True}); n += 1; usd += pricing.regen(clip["duration"])
    if n and a.record_spend:
        rid = ledger.open("import", {"note": "assets generated before promokit, cost estimated from pricing table", "files": n}, usd); ledger.close(rid, "done", usd)
    print(f"  imported {n} files into cache ({p.cache_dir}); estimated historical cost ${usd:.2f}{' recorded in ledger' if a.record_spend and n else ''}")

def main(argv=None):
    ap = argparse.ArgumentParser(prog="promokit", description=__doc__); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help="create a project from the template"); s.add_argument("name"); s.add_argument("--url"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("check", help="verify tools, API key, voices"); s.add_argument("project", nargs="?"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("voices", help="list cloned voices (free)"); s.set_defaults(fn=cmd_voices)
    s = sub.add_parser("plan", help="cost plan, nothing is spent"); s.add_argument("project"); s.set_defaults(fn=cmd_plan)
    for name, fn, hlp in (("vo", cmd_vo, "voiceover (paid, cached)"), ("clips", cmd_clips, "H3 draft clips (paid, cached)"), ("upscale", cmd_upscale, "2K regeneration of approved clips (paid, cached)")):
        s = sub.add_parser(name, help=hlp); s.add_argument("project"); s.add_argument("--yes", action="store_true", help="actually spend money"); s.add_argument("--only", nargs="*"); s.add_argument("--force", action="store_true", help="ignore cache"); s.set_defaults(fn=fn)
    s = sub.add_parser("screens", help="record product scenes (free)"); s.add_argument("project"); s.add_argument("--only", nargs="*"); s.set_defaults(fn=cmd_screens)
    s = sub.add_parser("overlays", help="render overlays (free)"); s.add_argument("project"); s.add_argument("--only", nargs="*"); s.set_defaults(fn=cmd_overlays)
    s = sub.add_parser("assemble", help="build the video (free)"); s.add_argument("project"); s.add_argument("--out"); s.add_argument("--sub", action="store_true"); s.add_argument("--proxies", action="store_true"); s.set_defaults(fn=cmd_assemble)
    s = sub.add_parser("run", help="all stages; dry unless --yes"); s.add_argument("project"); s.add_argument("--yes", action="store_true"); s.add_argument("--sub", action="store_true"); s.add_argument("--proxies", action="store_true"); s.add_argument("--skip-upscale", action="store_true"); s.add_argument("--out"); s.set_defaults(fn=cmd_run)
    s = sub.add_parser("ledger", help="spend history"); s.add_argument("project", nargs="?"); s.set_defaults(fn=cmd_ledger)
    s = sub.add_parser("cache-import", help="register existing vo/clips files in the cache"); s.add_argument("project"); s.add_argument("--record-spend", action="store_true", help="also log their estimated cost in the ledger"); s.set_defaults(fn=cmd_cache_import)
    for sp in sub.choices.values():
        if not any(x.dest == "variant" for x in sp._actions): sp.add_argument("--variant", help="format variant: variants/<name>.yaml (e.g. tiktok)")
    a = ap.parse_args(argv); global _VARIANT; _VARIANT = getattr(a, "variant", None); a.fn(a)

if __name__ == "__main__": main()
