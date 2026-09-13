"""Voiceover segments with cache + budget guard."""
from __future__ import annotations
import shutil, subprocess
from .cache import key_of

NO_VOICE = "voice.voice_id is empty: set it in project.yaml or PROMOKIT_VOICE_ID in .env (`promokit voices`)"

def _req(project, seg, strict=True):
    v = project["voice"]
    if strict and not v.get("voice_id"): raise ValueError(NO_VOICE)
    return {"kind": "tts", "text": seg["text"], "voice_id": v["voice_id"], "model": v["model"], "speed": seg.get("speed", v["speed"]),
            "emotion": seg.get("emotion"), "language": v["language"]}

def plan(project, cache, pricing):
    rows = []
    for seg in project.get("script", []):
        req = _req(project, seg, strict=False); hit = cache.get("tts", key_of(req)) if req["voice_id"] else None
        rows.append({"id": seg["id"], "chars": len(seg["text"]), "cached": bool(hit), "est_usd": 0.0 if hit else pricing.tts(req["model"], len(seg["text"])), "no_voice": not req["voice_id"]})
    return rows

def duration(path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))

def generate(project, mm, cache, guard, ledger, pricing, only=None, force=False, log=print):
    out_dir = project.dir / "vo"; results = {}
    for seg in project.get("script", []):
        if only and seg["id"] not in only: continue
        req = _req(project, seg); key = key_of(req); out = out_dir / f"{seg['id']}.mp3"
        hit = None if force else cache.get("tts", key)
        if hit:
            if not out.exists() or out.stat().st_size != __import__("pathlib").Path(hit["path"]).stat().st_size: shutil.copy2(hit["path"], out)
            results[seg["id"]] = {"path": str(out), "cached": True, "duration": duration(out)}; log(f"  vo {seg['id']}: cached ({results[seg['id']]['duration']:.2f}s)"); continue
        est = pricing.tts(req["model"], len(seg["text"])); guard.check(est, f"TTS {seg['id']} ({len(seg['text'])} chars)")
        rid = ledger.open("tts", {"segment": seg["id"], "chars": len(seg["text"]), "model": req["model"], "voice_id": req["voice_id"]}, est)
        try:
            info = mm.tts(seg["text"], out, voice_id=req["voice_id"], model=req["model"], speed=req["speed"], emotion=req["emotion"], language=req["language"])
            actual = pricing.tts(req["model"], int(info.get("usage_characters", len(seg["text"]))))
            ledger.close(rid, "done", actual, {"audio_length_ms": info.get("audio_length"), "usage_characters": info.get("usage_characters")})
            cache.put("tts", key, out, {"request": req, "segment": seg["id"], "extra_info": info})
            results[seg["id"]] = {"path": str(out), "cached": False, "duration": duration(out), "usd": actual}
            log(f"  vo {seg['id']}: generated ({results[seg['id']]['duration']:.2f}s, ~${actual:.3f})")
        except Exception:
            ledger.close(rid, "failed"); raise
    return results
