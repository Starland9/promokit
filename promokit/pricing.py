"""Pricing table + estimators. USD, pay-as-you-go, from platform.minimax.io/docs/guides/pricing-paygo (read 2026-09-13).
Override any value in project.yaml under `pricing:` (prices change; the ledger records the estimate used)."""
from __future__ import annotations

DEFAULT_PRICES = {
    # MiniMax H3 video (per output second)
    "video.MiniMax-H3.768P": 0.08,
    "video.MiniMax-H3.2K": 0.13,
    "video.MiniMax-H3-Max.480P": 0.05,
    "video.MiniMax-H3-Max.768P": 0.08,
    "video.regeneration.2K": 0.05,       # 768P -> 2K, per second
    "video.reference_image": 0.04,       # per reference image beyond the first 5 free
    "video.reference_image_free": 5,
    # Text to speech (per 1000 characters)
    "tts.speech-2.8-hd": 0.10,
    "tts.speech-2.8-turbo": 0.06,
    "tts.speech-2.6-hd": 0.10,
    "tts.speech-2.6-turbo": 0.06,
    "voice.clone": 1.5,                  # rapid voice cloning, per voice (never done automatically by promokit)
    # Failed / content-filtered tasks are normally not billed, but we count them at 100% to stay conservative.
    "policy.failed_task_billing": 1.0,
}

class Pricing:
    def __init__(self, overrides: dict | None = None):
        self.p = dict(DEFAULT_PRICES); self.p.update(overrides or {})
    def video(self, model: str, resolution: str, seconds: float, n_ref_images: int = 0) -> float:
        key = f"video.{model}.{resolution}"
        if key not in self.p: raise KeyError(f"no price for {key}; add it under pricing: in project.yaml")
        imgs = max(0, n_ref_images - int(self.p["video.reference_image_free"]))
        return round(self.p[key] * seconds + imgs * self.p["video.reference_image"], 4)
    def regen(self, seconds: float) -> float:
        return round(self.p["video.regeneration.2K"] * seconds, 4)
    def tts(self, model: str, n_chars: int) -> float:
        key = f"tts.{model}"
        if key not in self.p: raise KeyError(f"no price for {key}")
        return round(self.p[key] * n_chars / 1000.0, 4)
