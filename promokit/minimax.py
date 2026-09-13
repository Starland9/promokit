"""Thin MiniMax client (no caching, no budget logic here): TTS, H3 video create/query/wait, 2K regeneration, voices."""
from __future__ import annotations
import os, json, time, base64, mimetypes, pathlib, requests

class MiniMax:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.key = api_key or os.environ.get("MINIMAX_API_KEY"); self.base = (base_url or os.environ.get("MINIMAX_BASE_URL") or "https://api.minimax.io").rstrip("/")
        if not self.key: raise RuntimeError("MINIMAX_API_KEY missing (set it in .env or the environment)")
        self.h = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
    # ---- helpers
    @staticmethod
    def data_uri(path) -> str:
        mt = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        return f"data:{mt};base64," + base64.b64encode(pathlib.Path(path).read_bytes()).decode()
    @staticmethod
    def download(url: str, out, retries: int = 4):
        last = None
        for i in range(retries):
            try:
                r = requests.get(url, stream=True, timeout=600); r.raise_for_status()
                with open(out, "wb") as f:
                    for ch in r.iter_content(1 << 16): f.write(ch)
                return out
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                last = e; time.sleep(5 * (i + 1))
        raise RuntimeError(f"download failed after {retries} tries: {last}")
    # ---- voices (free)
    def voices(self, voice_type: str = "voice_cloning") -> dict:
        r = requests.post(f"{self.base}/v1/get_voice", headers=self.h, json={"voice_type": voice_type}, timeout=60); return r.json()
    # ---- TTS
    def tts(self, text: str, out, voice_id: str, model: str = "speech-2.8-hd", speed: float = 1.0, emotion: str | None = None,
            language: str = "French", subtitles: bool = True) -> dict:
        body = {"model": model, "text": text, "voice_setting": {"voice_id": voice_id, "speed": speed, "vol": 1.0, "pitch": 0},
                "audio_setting": {"sample_rate": 44100, "bitrate": 256000, "format": "mp3", "channel": 1},
                "language_boost": language, "subtitle_enable": subtitles, "output_format": "hex"}
        if emotion: body["voice_setting"]["emotion"] = emotion
        r = requests.post(f"{self.base}/v1/t2a_v2", headers=self.h, json=body, timeout=300); j = r.json()
        if j.get("base_resp", {}).get("status_code") != 0: raise RuntimeError(f"tts failed: {j.get('base_resp')}")
        pathlib.Path(out).write_bytes(bytes.fromhex(j["data"]["audio"]))
        sub = j["data"].get("subtitle_file")
        if sub:
            try: self.download(sub, str(out) + ".subtitles.json", retries=2)
            except Exception: pass
        return j.get("extra_info", {})
    # ---- H3 video
    def video_create(self, text: str, duration: int, resolution: str = "768P", ratio: str | None = "16:9", model: str = "MiniMax-H3",
                     images: list[tuple[str, str]] = (), videos: list[str] = (), audios: list[str] = ()) -> str:
        u = lambda p: p if str(p).startswith(("http", "mm_file", "data:")) else self.data_uri(p)
        content = [{"type": "text", "text": text}]
        for role, p in images: content.append({"type": "image_url", "role": role, "image_url": {"url": u(p)}})
        for p in videos: content.append({"type": "video_url", "role": "reference_video", "video_url": {"url": u(p)}})
        for p in audios: content.append({"type": "audio_url", "role": "reference_audio", "audio_url": {"url": u(p)}})
        body = {"model": model, "content": content, "resolution": resolution, "duration": int(duration)}
        keyframe = any(r in ("first_frame", "last_frame") for r, _ in images)
        if ratio and not keyframe: body["ratio"] = ratio
        r = requests.post(f"{self.base}/v2/video_generation", headers=self.h, json=body, timeout=180)
        try: j = r.json()
        except Exception: j = {"raw": r.text[:500]}
        if r.status_code != 200 or "task_id" not in j: raise RuntimeError(f"video create failed {r.status_code}: {j}")
        return j["task_id"]
    def video_regenerate(self, source_task_id: str, resolution: str = "2K", model: str = "MiniMax-H3") -> str:
        r = requests.post(f"{self.base}/v2/video_regeneration", headers=self.h, json={"model": model, "source_task_id": source_task_id, "resolution": resolution}, timeout=120)
        j = r.json()
        if r.status_code != 200 or "task_id" not in j: raise RuntimeError(f"regeneration failed {r.status_code}: {j}")
        return j["task_id"]
    def video_query(self, task_id: str) -> dict:
        return requests.get(f"{self.base}/v2/query/video_generation/{task_id}", headers=self.h, timeout=60).json()
    def video_wait(self, task_id: str, out, interval: int = 15, max_wait: int = 3600, log=print) -> dict:
        t0 = time.time(); last = None
        while time.time() - t0 < max_wait:
            j = self.video_query(task_id); t = j.get("task", {}); st = t.get("status")
            if st != last and log: log(f"  [{task_id}] {st} (+{int(time.time()-t0)}s)"); last = st
            if st == "succeeded":
                self.download(t["content"]["url"], out); return j
            if st in ("failed", "cancelled"): raise RuntimeError(f"task {task_id} {st}: {json.dumps(j)[:600]}")
            time.sleep(interval)
        raise TimeoutError(task_id)
