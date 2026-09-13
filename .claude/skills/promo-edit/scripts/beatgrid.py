#!/usr/bin/env python
"""Beat grid of a music file for music-driven edits (free).
usage: python beatgrid.py track.mp3 [--seconds 60]
Prints bpm (-> timeline.bpm), bar length, downbeat times and loudness per second, and suggests `music.in`
so that the first full-energy bar lands on a cut."""
import argparse, subprocess
import numpy as np

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("track"); ap.add_argument("--seconds", type=float, default=60.0); ap.add_argument("--bpb", type=int, default=4); a = ap.parse_args()
    sr = 22050
    x = np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-i", a.track, "-t", str(a.seconds), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]), np.float32)
    hop, win = 256, 1024; n = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    X = np.abs(np.fft.rfft(x[idx] * np.hanning(win), axis=1)); f = np.fft.rfftfreq(win, 1 / sr); fps = sr / hop
    flux = np.maximum(0, np.diff(np.log1p(X), axis=0)).sum(1); fl = flux - flux.mean()
    ac = np.correlate(fl, fl, "full")[len(fl) - 1:]; lo, hi = int(fps * 60 / 180), int(fps * 60 / 70)
    lag = lo + int(np.argmax(ac[lo:hi])); y0, y1, y2 = ac[lag - 1], ac[lag], ac[lag + 1]; d = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2)
    period = (lag + d) / fps; bpm = 60 / period
    phases = np.linspace(0, period, 200, endpoint=False); T = len(flux) / fps
    score = [sum(flux[int((p + k * period) * fps)] for k in range(int((T - p) / period)) if int((p + k * period) * fps) < len(flux)) for p in phases]
    ph = float(phases[int(np.argmax(score))]); beats = [ph + k * period for k in range(int((T - ph) / period))]
    low = X[:, f < 150].sum(1); lowe = [low[int(b * fps):int((b + 0.08) * fps)].mean() for b in beats]
    off = max(range(a.bpb), key=lambda o: np.mean(lowe[o::a.bpb])); bars = beats[off::a.bpb]
    rms = [20 * np.log10(np.sqrt(np.mean(x[i * sr:(i + 1) * sr] ** 2)) + 1e-9) for i in range(int(len(x) / sr))]
    sm = np.convolve(rms, [1 / 3] * 3, "same"); loud = float(np.percentile(sm, 75))
    first_full = next((b for b in bars if b > 2 and sm[min(len(sm) - 1, int(b) + 1)] >= loud - 1.5), bars[0])
    print(f"timeline.bpm: {bpm:.3f}   (beat {period:.4f}s, bar {period * a.bpb:.4f}s)")
    print("downbeats (s):", ", ".join(f"{b:.3f}" for b in bars[:24]))
    print("loudness/s (dB):", " ".join(f"{i}:{v:.0f}" for i, v in enumerate(rms)))
    print(f"first full-energy bar ~ {first_full:.3f}s")
    for k in (1, 2):
        start = first_full - k * a.bpb * period
        if start >= 0: print(f"  music.in: {start:.3f}  -> full energy starts after {k} bar(s) of video (put the hook there, cut on the drop)")

if __name__ == "__main__": main()
