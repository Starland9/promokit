#!/usr/bin/env python
"""Blur secondary text lines (names, phone numbers, message bodies) in dark-UI app screenshots before using them in a video.

usage: python redact_screens.py IN.png OUT.png [--top 1240] [--bottom 0] [--x0 260 --x1 1060] [--extra x0,y0,x1,y1 ...] [--debug]
  --top/--bottom   vertical zone to scan (image px); keep headers, totals and filters above --top readable
  --x0/--x1        horizontal zone to scan (e.g. right of list icons)
  --extra          additional boxes to blur
  --debug          draw red outlines around blurred boxes (for checking, do not ship)
Heuristic: in a dark UI, secondary text is mid-gray (luma 95-222) and titles/amounts are white (luma > 222); only gray lines are blurred.
Always check the result visually: the heuristic is not a guarantee."""
import argparse
from PIL import Image, ImageFilter, ImageDraw

def luma(p): return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]

def gray_blocks(im, x0, x1, y0, y1, min_h=10, gap=6):
    px = im.load(); rows = []
    for y in range(y0, y1):
        bright = mid = 0
        for x in range(x0, x1, 2):
            L = luma(px[x, y])
            if L > 222: bright += 1
            elif L > 95: mid += 1
        rows.append("white" if bright > 2 else ("gray" if mid > 3 else None))
    out, start, last = [], None, None
    for i, kind in enumerate(rows):
        y = y0 + i
        if kind == "gray":
            if start is None: start = y
            last = y
        elif start is not None and y - last > gap:
            if last - start + 1 >= min_h: out.append((start, last))
            start = None
    if start is not None and last - start + 1 >= min_h: out.append((start, last))
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--top", type=int, default=0); ap.add_argument("--bottom", type=int, default=0)
    ap.add_argument("--x0", type=int, default=260); ap.add_argument("--x1", type=int, default=0)
    ap.add_argument("--extra", nargs="*", default=[]); ap.add_argument("--radius", type=int, default=18); ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    im = Image.open(a.src).convert("RGB"); W, H = im.size
    x1 = a.x1 or W - 20; y1 = H - a.bottom if a.bottom else H
    boxes = [(max(0, a.x0 - 10), max(a.top, s - 8), min(W, x1 + 10), min(H, e + 8)) for s, e in gray_blocks(im, a.x0, x1, a.top, y1)]
    boxes += [tuple(int(v) for v in b.split(",")) for b in a.extra]
    d = ImageDraw.Draw(im) if a.debug else None
    for b in boxes:
        region = im.crop(b).filter(ImageFilter.GaussianBlur(a.radius)).filter(ImageFilter.GaussianBlur(a.radius)); im.paste(region, b[:2])
        if d: d.rectangle(b, outline=(255, 0, 0), width=3)
    im.save(a.dst); print(f"{a.dst}: {len(boxes)} zones floutées")

if __name__ == "__main__": main()
