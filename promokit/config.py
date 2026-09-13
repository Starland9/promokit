"""Project loading: project.yaml (+ optional variants/<name>.yaml) + .env, resolved paths, defaults.

A variant (e.g. `tiktok`) reuses the base project's paid assets (vo/, clips/, prompts/, assets/) and overrides
format-specific sections. Top-level keys of the variant REPLACE the base ones, except MERGE_KEYS which are deep-merged.
Variant outputs go to screens/out/<variant>/, overlays/<variant>/, build/<variant>/."""
from __future__ import annotations
import os, pathlib, yaml

DEFAULTS = {
    "video": {"width": 1920, "height": 1080, "fps": 30},
    "budget": {"max_usd": 5.0, "per_call_max_usd": 1.5, "max_clips_per_run": 6},
    "voice": {"model": "speech-2.8-hd", "language": "French", "speed": 1.0},
    "clips_defaults": {"model": "MiniMax-H3", "draft_resolution": "768P", "final_resolution": "2K", "ratio": "16:9"},
}
MERGE_KEYS = {"budget", "voice", "pricing", "site", "clips_defaults", "video"}

def load_env(start: pathlib.Path):
    """Load the nearest .env upwards (KEY=VALUE lines) without overriding real env vars."""
    for d in [start, *start.parents]:
        p = d / ".env"
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return p
    return None

def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out

class Project:
    def __init__(self, path, variant: str | None = None):
        p = pathlib.Path(path)
        self.file = p / "project.yaml" if p.is_dir() else p
        self.dir = self.file.parent.resolve()
        raw = yaml.safe_load(self.file.read_text()) or {}
        self.variant = variant
        if variant:
            vf = self.dir / "variants" / f"{variant}.yaml"
            if not vf.exists():
                avail = sorted(x.stem for x in (self.dir / "variants").glob("*.yaml")) if (self.dir / "variants").exists() else []
                raise FileNotFoundError(f"variant '{variant}' not found ({vf}); available: {avail or 'none'}")
            vraw = yaml.safe_load(vf.read_text()) or {}
            for k, v in vraw.items():
                raw[k] = deep_merge(raw.get(k) or {}, v) if k in MERGE_KEYS and isinstance(v, dict) else v
        self.cfg = deep_merge(DEFAULTS, raw)
        self.name = self.cfg.get("name") or self.dir.name
        self.env_file = load_env(self.dir)
        if not self.cfg["voice"].get("voice_id") and os.environ.get("PROMOKIT_VOICE_ID"):
            self.cfg["voice"]["voice_id"] = os.environ["PROMOKIT_VOICE_ID"]
        self.kit_root = pathlib.Path(__file__).resolve().parents[1]
        self.cache_dir = pathlib.Path(self.cfg.get("cache_dir") or (self.kit_root / "cache")).expanduser()
        self.ledger_file = pathlib.Path(self.cfg.get("ledger_file") or (self.kit_root / "ledger.jsonl")).expanduser()
        sub = variant or ""
        self.screens_out = self.dir / "screens" / "out" / sub
        self.overlays_dir = self.dir / "overlays" / sub
        self.build_dir = self.dir / "build" / sub
        for d in (self.dir / "vo", self.dir / "clips", self.screens_out, self.overlays_dir, self.build_dir): d.mkdir(parents=True, exist_ok=True)
    @property
    def label(self) -> str: return f"{self.name}:{self.variant}" if self.variant else self.name
    @property
    def portrait(self) -> bool: return self.cfg["video"]["height"] > self.cfg["video"]["width"]
    def path(self, rel) -> pathlib.Path:
        p = pathlib.Path(rel)
        return p if p.is_absolute() else (self.dir / p)
    def __getitem__(self, k): return self.cfg[k]
    def get(self, k, default=None): return self.cfg.get(k, default)
