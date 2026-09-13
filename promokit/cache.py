"""Content-addressed cache: never pay twice for the same request. Key = sha256 of the canonical request."""
from __future__ import annotations
import hashlib, json, pathlib, shutil, time

def key_of(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]

def file_hash(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""): h.update(ch)
    return h.hexdigest()[:24]

class Cache:
    def __init__(self, root: pathlib.Path):
        self.root = pathlib.Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        self.index = json.loads(self.index_path.read_text()) if self.index_path.exists() else {}
    def get(self, kind: str, key: str):
        e = self.index.get(f"{kind}:{key}")
        if e and pathlib.Path(e["path"]).exists(): return e
        return None
    def put(self, kind: str, key: str, src_path, meta: dict, ext: str | None = None) -> dict:
        d = self.root / kind; d.mkdir(exist_ok=True)
        ext = ext or pathlib.Path(src_path).suffix
        dst = d / f"{key}{ext}"
        if pathlib.Path(src_path).resolve() != dst.resolve(): shutil.copy2(src_path, dst)
        e = {"path": str(dst), "meta": meta, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.index[f"{kind}:{key}"] = e; self._save(); return e
    def _save(self): self.index_path.write_text(json.dumps(self.index, indent=1, ensure_ascii=False))
