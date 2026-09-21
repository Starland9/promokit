"""Config-driven overlays rendered with Pillow (full-frame transparent PNGs overlaid at 0:0). Works for 16:9 and 9:16.
Item types:
  title        big text block (wrapped), y, size, gradient: bottom|top|none, underline
  chip         pill with a dot; align left|center, x, y, size (auto-shrinks to max_width)
  url_tag      small dark pill; x/y or bottom-right by default
  endcard      opaque gradient card: logo, headline, url pill, tagline (all wrapped and vertically centered)
  doc_hero     document image on a soft background (e.g. an exported PDF): image, doc_width, canvas_height, badge
  device_frame phone/tablet frame for screen recordings: x, y, w, h (screen area), radius, bezel, bg (background spec) -> <id>_bg.png + <id>_mask.png
  background   opaque full frame: color, to (vertical gradient), blobs [{x, y, r, color, alpha, blur}]
  notification phone notification card: x, y, w, sender, body, app, time, theme light|dark, icon_color, icon_text
  tap          touch ripple: x, y (frame px) or at {frame, image: [w, h], x, y} (screenshot px, fit contain), r, color
  image        picture placed on a transparent frame: src, w, x|align center, y, radius, shadow
  magnify      enlarged crop of a screenshot ("loupe"): src, box [x0, y0, x1, y1] (image px), w, x|align center, y, radius, border, border_width
  code         syntax-highlighted code card (mono font): lines|text, lang (python|js|sql|bash|http|json|yaml|generic), size, w, x|align, y,
               title, window (mac dots), numbers, hl [line numbers], style: terminal ($ prompt lines), bg, border, hl_color
Colors accept #RRGGBB or #RRGGBBAA. Common text options: color, accent (words), accent_color.
"""

from __future__ import annotations
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import pathlib, re

CODE_COLORS = {
    "kw": "#FF7B72",
    "str": "#A5D6FF",
    "num": "#79C0FF",
    "cmt": "#8B949E",
    "fn": "#D2A8FF",
    "const": "#7EE787",
    "type": "#FFA657",
    "punct": "#C9D1D9",
    "prompt": "#3FB950",
    "muted": "#8B949E",
    "text": "#E6EDF3",
}
KEYWORDS = {
    "python": "def class return if elif else for while in not and or import from as with try except finally raise yield lambda pass break continue True False None async await is del assert",
    "js": "const let var function return if else for while in of new class extends import from export default async await try catch finally throw this true false null undefined typeof switch case break continue",
    "sql": "select from where insert into values update set delete join left right inner outer on group by order having limit offset create table index primary key not null unique default as and or in is like between distinct count sum avg min max begin commit rollback transaction alter drop explain",
    "bash": "if then else fi for do done while in echo export cd ls cat grep curl docker git npm pip python sudo apt exit return function local",
    "http": "HTTP GET POST PUT PATCH DELETE HEAD OPTIONS",
    "go": "func package import return if else for range var const type struct interface map chan go defer select switch case nil true false",
    "php": "function return if else elseif foreach for while class public private protected static new echo namespace use true false null",
    "java": "public private protected class interface static void int long boolean return if else for while new this extends implements import try catch finally throw true false null",
    "yaml": "true false null",
    "json": "true false null",
    "generic": "if else for while return function def class import from true false null",
}
TOKEN_RE = re.compile(
    r"(?P<cmt>#.*|//.*|--\s.*|/\*.*?\*/)|(?P<str>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`[^`]*`)|(?P<num>\b\d+(?:\.\d+)?\b)|(?P<word>[A-Za-z_][A-Za-z0-9_]*)|(?P<ws>\s+)|(?P<punct>.)"
)


def tokenize(line: str, lang: str = "generic"):
    """[(text, kind)] for a line of code; kind in CODE_COLORS."""
    kws = set(KEYWORDS.get(lang, KEYWORDS["generic"]).split())
    out = []
    low = lang == "sql"
    for m in TOKEN_RE.finditer(line):
        k = m.lastgroup
        t = m.group()
        if k == "word":
            nxt = line[m.end() : m.end() + 1]
            if (t.lower() if low else t) in kws:
                k = "kw"
            elif lang == "http" and t.isupper() and len(t) > 2:
                k = "const"
            elif nxt == "(":
                k = "fn"
            elif (
                t[:1].isupper()
                and not t.isupper()
                and lang in ("python", "js", "java", "go", "php")
            ):
                k = "type"
            elif t.isupper() and len(t) > 1:
                k = "const"
            else:
                k = "text"
            if (
                lang in ("http", "yaml")
                and k == "text"
                and nxt == ":"
                and m.start() == len(line) - len(line.lstrip())
            ):
                k = "type"
        out.append((t, k))
    return out


def find_mono(project):
    """Monospace font: overlays.fonts.mono, else JetBrains Mono / DejaVu Sans Mono found on the machine, else the body font."""
    fonts = project.get("overlays", {}).get("fonts", {})
    cands = []
    if fonts.get("mono"):
        cands.append(project.path(fonts["mono"]))
    names = (
        "JetBrainsMono.ttf",
        "JetBrainsMono-Regular.ttf",
        "JetBrainsMono[wght].ttf",
        "JetBrainsMonoNL-Regular.ttf",
    )
    for d in (
        project.dir / "assets" / "fonts",
        project.path(fonts.get("dir", "assets/fonts")),
        project.kit_root / "templates" / "project" / "assets" / "fonts",
        pathlib.Path.home() / ".fonts",
        pathlib.Path.home() / ".local" / "share" / "fonts",
        pathlib.Path("/usr/share/fonts/truetype/jetbrains-mono"),
    ):
        cands += [d / n for n in names]
    cands += [
        pathlib.Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        pathlib.Path("/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf"),
    ]
    return next(
        (c for c in cands if c.exists()),
        project.path(fonts.get("body", "assets/fonts/DMSans.ttf")),
    )


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))


def _rgba(c, default_alpha=255):
    c = c.lstrip("#")
    a = int(c[6:8], 16) if len(c) >= 8 else default_alpha
    return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4)) + (a,)


class Painter:
    def __init__(self, project):
        ov = project.get("overlays", {})
        self.project = project
        self.W, self.H = project["video"]["width"], project["video"]["height"]
        f = ov.get("fonts", {})
        self.font_h = project.path(f.get("heading", "assets/fonts/Sora.ttf"))
        self.font_b = project.path(f.get("body", "assets/fonts/DMSans.ttf"))
        self.font_m = find_mono(project)
        c = ov.get("colors", {})
        self.primary = _hex(c.get("primary", "#4a21ed"))
        self.accent = _hex(c.get("accent", "#b447eb"))
        self.ink = _hex(c.get("ink", "#111117"))
        self.w_heading = f.get("heading_weight", "Bold")
        self.w_semibold = f.get("semibold_weight", "SemiBold")
        self.w_body = f.get("body_weight", "Medium")
        self.default_bg = ov.get("background")
        self.out = project.overlays_dir
        self.out.mkdir(parents=True, exist_ok=True)

    # ---- helpers
    def font(self, which, size, var=None):
        f = ImageFont.truetype(
            str(
                {"h": self.font_h, "b": self.font_b, "m": self.font_m}.get(
                    which, self.font_h
                )
            ),
            int(size),
        )
        if var:
            try:
                f.set_variation_by_name(var)
            except Exception:
                pass
        return f

    @staticmethod
    def shadow(layer, radius=18, offset=(0, 10), alpha=90):
        a = layer.split()[3]
        sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        sh.putalpha(a.point(lambda v: v * alpha // 255))
        sh = sh.filter(ImageFilter.GaussianBlur(radius))
        out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        out.alpha_composite(sh, offset)
        out.alpha_composite(layer)
        return out

    @staticmethod
    def tsize(f, t):
        d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        b = d.textbbox((0, 0), t, font=f)
        return b[2] - b[0], b[3] - b[1], b

    def wrap(self, f, text, max_w):
        # les sauts de ligne explicites du project.yaml ("HTTP\nvs HTTPS") sont respectés :
        # sinon un titre censé tenir sur deux lignes débordait du cadre sur une seule.
        lines = []
        for para in str(text).split("\n"):
            cur = ""
            for w in para.split():
                cand = (cur + " " + w).strip()
                if cur and self.tsize(f, cand)[0] > max_w:
                    lines.append(cur)
                    cur = w
                else:
                    cur = cand
            if cur or para.strip() == "":
                lines.append(cur)
        while lines and not lines[-1]:
            lines.pop()
        return lines or [str(text)]

    def text_block(
        self, d, lines, f, cx, y, fill, spacing=1.12, accent=(), accent_fill=None
    ):
        _, lh, _ = self.tsize(f, "ÉgjpÀ")
        step = int(lh * spacing)
        acc = {a.upper().strip(".,?!…:;") for a in accent}
        for i, ln in enumerate(lines):
            tw, th, bb = self.tsize(f, ln)
            x = cx - tw // 2 - bb[0]
            yy = y + i * step - bb[1]
            if not acc:
                d.text((x, yy), ln, font=f, fill=fill)
                continue
            space = self.tsize(f, "a a")[0] - self.tsize(f, "aa")[0]
            for w in ln.split(" "):
                col = accent_fill if w.upper().strip(".,?!…:;") in acc else fill
                d.text((x, yy), w, font=f, fill=col)
                x += self.tsize(f, w)[0] + space
        return step * len(lines)

    def canvas(self):
        return Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))

    def gradient(self, w, h):
        im = Image.new("RGB", (w, h))
        px = im.load()
        for yy in range(h):
            for xx in range(w):
                t = xx / w * 0.62 + yy / h * 0.38
                px[xx, yy] = tuple(
                    int(self.primary[i] * (1 - t) + self.accent[i] * t)
                    for i in range(3)
                )
        return im

    def brand_bg(self, glow=True, spec=None):
        spec = spec or self.default_bg
        if spec:
            return self.bg_from_spec(spec)
        bg = (
            self.gradient(max(4, self.W // 4), max(4, self.H // 4))
            .resize((self.W, self.H), Image.BICUBIC)
            .convert("RGBA")
        )
        if glow:
            g = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
            ImageDraw.Draw(g).ellipse(
                (self.W * 0.45, -self.H * 0.2, self.W * 1.25, self.H * 0.6),
                fill=(255, 255, 255, 60),
            )
            bg.alpha_composite(
                g.filter(ImageFilter.GaussianBlur(min(self.W, self.H) // 7))
            )
        return bg

    def bg_from_spec(self, sp):
        c0 = _hex(sp.get("color", "#000000"))
        c1 = _hex(sp.get("to", sp.get("color", "#000000")))
        small = Image.new("RGB", (8, 64))
        px = small.load()
        for yy in range(64):
            t = yy / 63
            col = tuple(int(c0[i] * (1 - t) + c1[i] * t) for i in range(3))
            for xx in range(8):
                px[xx, yy] = col
        bg = small.resize((self.W, self.H), Image.BICUBIC).convert("RGBA")
        for b in sp.get("blobs", []):
            layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
            r = int(b.get("r", 200))
            x, y = int(b["x"]), int(b["y"])
            ImageDraw.Draw(layer).ellipse(
                (x - r, y - r, x + r, y + r),
                fill=_hex(b.get("color", "#FFFFFF")) + (int(b.get("alpha", 120)),),
            )
            if b.get("blur", 0):
                layer = layer.filter(ImageFilter.GaussianBlur(int(b["blur"])))
            bg.alpha_composite(layer)
        if sp.get("vignette", 0):
            v = Image.new("L", (self.W, self.H), 0)
            ImageDraw.Draw(v).ellipse(
                (-self.W * 0.3, -self.H * 0.15, self.W * 1.3, self.H * 1.15), fill=255
            )
            v = v.filter(ImageFilter.GaussianBlur(self.W // 5))
            dark = Image.new(
                "RGBA", (self.W, self.H), (0, 0, 0, int(255 * float(sp["vignette"])))
            )
            dark.putalpha(
                Image.eval(v, lambda a: int((255 - a) * float(sp["vignette"])))
            )
            bg.alpha_composite(dark)
        return bg

    def background(self, it):
        return self.bg_from_spec(it).convert("RGB")

    def image(self, it):
        im = Image.open(self.project.path(it["src"])).convert("RGBA")
        w = int(it.get("w", 300))
        im = im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)
        if it.get("radius"):
            m = Image.new("L", im.size, 0)
            ImageDraw.Draw(m).rounded_rectangle(
                (0, 0, im.width - 1, im.height - 1), radius=int(it["radius"]), fill=255
            )
            im.putalpha(Image.composite(im.split()[3], Image.new("L", im.size, 0), m))
        x = (
            (self.W - im.width) // 2
            if it.get("align", "center") == "center" and "x" not in it
            else int(it.get("x", 0))
        )
        y = int(it.get("y", (self.H - im.height) // 2))
        L = self.canvas()
        L.alpha_composite(im, (x, y))
        return (
            self.shadow(
                L, int(it.get("shadow_blur", 40)), (0, 24), int(it.get("shadow", 120))
            )
            if it.get("shadow", 120)
            else L
        )

    def magnify(self, it):
        im = (
            Image.open(self.project.path(it["src"]))
            .convert("RGBA")
            .crop(tuple(int(v) for v in it["box"]))
        )
        w = int(it.get("w", 900))
        im = im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)
        r = int(it.get("radius", 36))
        m = Image.new("L", im.size, 0)
        ImageDraw.Draw(m).rounded_rectangle(
            (0, 0, im.width - 1, im.height - 1), radius=r, fill=255
        )
        im.putalpha(m)
        x = (self.W - w) // 2 if "x" not in it else int(it["x"])
        y = int(it["y"])
        L = self.canvas()
        L.alpha_composite(im, (x, y))
        if it.get("border"):
            bw = int(it.get("border_width", 6))
            ImageDraw.Draw(L).rounded_rectangle(
                (x - bw // 2, y - bw // 2, x + w + bw // 2, y + im.height + bw // 2),
                radius=r + bw // 2,
                outline=_rgba(it["border"]),
                width=bw,
            )
        return self.shadow(
            L, int(it.get("shadow_blur", 44)), (0, 26), int(it.get("shadow", 170))
        )

    def notification(self, it):
        x, y, w = int(it.get("x", 60)), int(it["y"]), int(it.get("w", self.W - 120))
        pad = int(it.get("pad", 34))
        dark = it.get("theme", "light") == "dark"
        card = _rgba(it.get("bg", "#26232dF2" if dark else "#FFFFFFF5"))
        fg = _rgba(it.get("fg", "#F4F2F8" if dark else "#15131A"))
        sub = _rgba(it.get("sub", "#B7B0C4" if dark else "#5E5a66"))
        f_app, f_sender, f_body = (
            self.font("b", 28, "Medium"),
            self.font("h", 38, self.w_heading),
            self.font("b", 34, "Regular"),
        )
        icon = 84
        tx = x + pad + icon + 26
        tw = x + w - pad - tx
        body_lines = self.wrap(f_body, it["body"], tw)[: int(it.get("max_lines", 2))]
        _, lh_b, _ = self.tsize(f_body, "ÉgjpÀ")
        _, lh_s, _ = self.tsize(f_sender, "ÉgjpÀ")
        _, lh_a, _ = self.tsize(f_app, "ÉgjpÀ")
        h = pad + lh_a + 14 + lh_s + 10 + int(lh_b * 1.25) * len(body_lines) + pad
        L = self.canvas()
        d = ImageDraw.Draw(L)
        d.rounded_rectangle(
            (x, y, x + w, y + h), radius=int(it.get("radius", 40)), fill=card
        )
        ic = _rgba(it.get("icon_color", "#4F46E5"))
        cy = y + pad + lh_a + 14
        d.ellipse((x + pad, cy, x + pad + icon, cy + icon), fill=ic)
        if it.get("icon_text"):
            fi = self.font("h", 30, self.w_heading)
            iw_, ih_, ib = self.tsize(fi, it["icon_text"])
            d.text(
                (x + pad + (icon - iw_) // 2 - ib[0], cy + (icon - ih_) // 2 - ib[1]),
                it["icon_text"],
                font=fi,
                fill=(255, 255, 255, 255),
            )
        else:  # chat bubble glyph
            bx, by = x + pad + 22, cy + 24
            d.rounded_rectangle(
                (bx, by, bx + 40, by + 30), radius=9, fill=(255, 255, 255, 255)
            )
            d.polygon(
                [(bx + 8, by + 28), (bx + 8, by + 40), (bx + 20, by + 28)],
                fill=(255, 255, 255, 255),
            )
        header = f"{it.get('app', 'Messages')}  ·  {it.get('time', 'maintenant')}"
        hb = self.tsize(f_app, header)[2]
        d.text((x + pad - hb[0], y + pad - hb[1]), header, font=f_app, fill=sub)
        sb = self.tsize(f_sender, it["sender"])[2]
        d.text((tx - sb[0], cy - sb[1]), it["sender"], font=f_sender, fill=fg)
        yy = cy + lh_s + 10
        for ln in body_lines:
            lb = self.tsize(f_body, ln)[2]
            d.text((tx - lb[0], yy - lb[1]), ln, font=f_body, fill=sub)
            yy += int(lh_b * 1.25)
        return self.shadow(L, 30, (0, 16), int(it.get("shadow", 110)))

    def resolve_point(self, it):
        if "at" not in it:
            return int(it["x"]), int(it["y"])
        at = it["at"]
        fr = next(
            x
            for x in self.project.get("overlays", {}).get("items", [])
            if x["id"] == at["frame"]
        )
        iw_, ih_ = at["image"]
        fw, fh = int(fr["w"]), int(fr["h"])
        if (
            at.get("fit", "contain") == "width"
        ):  # same geometry as a segment with fit: width, pan: <pan>
            sc = fw / iw_
            oy = -max(0.0, ih_ * sc - fh) * float(at.get("pan", 0.0))
            return int(fr["x"] + at["x"] * sc), int(fr["y"] + oy + at["y"] * sc)
        sc = min(fw / iw_, fh / ih_)
        return int(fr["x"] + (fw - iw_ * sc) / 2 + at["x"] * sc), int(
            fr["y"] + (fh - ih_ * sc) / 2 + at["y"] * sc
        )

    def tap(self, it):
        x, y = self.resolve_point(it)
        r = int(it.get("r", 46))
        col = _hex(it.get("color", "#FFFFFF"))
        L = self.canvas()
        d = ImageDraw.Draw(L)
        d.ellipse(
            (x - r * 1.6, y - r * 1.6, x + r * 1.6, y + r * 1.6),
            outline=col + (150,),
            width=6,
        )
        d.ellipse((x - r, y - r, x + r, y + r), fill=col + (110,))
        return L

    # ---- items
    def chip(self, it):
        size = int(it.get("size", 32))
        max_w = int(it.get("max_width", self.W - 2 * 64))
        padx, dot, gap = int(size * 1.06), int(size * 0.44), int(size * 0.56)
        while True:
            f = self.font("h", size, it.get("weight", self.w_semibold))
            tw, th, bb = self.tsize(f, it["text"])
            w = padx + dot + gap + tw + padx
            if w <= max_w or size <= 18:
                break
            size -= 2
            padx, dot, gap = int(size * 1.06), int(size * 0.44), int(size * 0.56)
        h = int(size * 2.38)
        x = (self.W - w) // 2 if it.get("align") == "center" else int(it.get("x", 64))
        y = int(it.get("y", self.H - 64 - h))
        L = self.canvas()
        d = ImageDraw.Draw(L)
        d.rounded_rectangle(
            (x, y, x + w, y + h), radius=h // 2, fill=_rgba(it.get("bg", "#FFFFFFF5"))
        )
        if it.get("border"):
            d.rounded_rectangle(
                (x, y, x + w, y + h),
                radius=h // 2,
                outline=_rgba(it["border"]),
                width=int(it.get("border_width", 3)),
            )
        d.ellipse(
            (x + padx, y + h // 2 - dot // 2, x + padx + dot, y + h // 2 + dot // 2),
            fill=_rgba(it["dot"]) if it.get("dot") else self.primary,
        )
        d.text(
            (x + padx + dot + gap - bb[0], y + (h - th) // 2 - bb[1]),
            it["text"],
            font=f,
            fill=_rgba(it["fg"]) if it.get("fg") else self.ink,
        )
        return self.shadow(L, 22, (0, 10), 70)

    def url_tag(self, it):
        f = self.font("b", it.get("size", 30), "Medium")
        tw, th, bb = self.tsize(f, it["text"])
        padx, h = 26, int(it.get("size", 30) * 1.87)
        w = tw + 2 * padx
        x = (
            (self.W - w) // 2
            if it.get("align") == "center"
            else int(it.get("x", self.W - 64 - w))
        )
        y = int(it.get("y", self.H - 64 - h))
        L = self.canvas()
        d = ImageDraw.Draw(L)
        d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=(17, 17, 23, 170))
        d.text(
            (x + padx - bb[0], y + (h - th) // 2 - bb[1]),
            it["text"],
            font=f,
            fill=(255, 255, 255, 255),
        )
        return L

    def title(self, it):
        size = int(it.get("size", 78))
        f = self.font("h", size, it.get("weight", self.w_heading))
        text = it["text"].upper() if it.get("caps") else it["text"]
        lines = self.wrap(f, text, int(it.get("max_width", self.W - 160)))
        y = int(it.get("y", int(self.H * 0.77)))
        L = self.canvas()
        d = ImageDraw.Draw(L)
        hgt = self.text_block(
            d,
            lines,
            f,
            self.W // 2,
            y,
            _rgba(it.get("color", "#FFFFFF")),
            it.get("spacing", 1.12),
            it.get("accent", ()),
            _rgba(it.get("accent_color", "#FFD84D")),
        )
        if it.get("underline", True):
            lw0 = self.tsize(f, lines[-1])[0]
            ux = (
                self.W // 2 - lw0 // 2
                if len(lines) > 1 or it.get("center_underline")
                else (self.W - self.tsize(f, lines[0])[0]) // 2
            )
            d.rounded_rectangle(
                (ux, y + hgt + 14, ux + 140, y + hgt + 22),
                radius=4,
                fill=_rgba(it["underline_color"])
                if it.get("underline_color")
                else self.primary,
            )
        out = self.canvas()
        grad = it.get("gradient", "bottom")
        if grad in ("bottom", "top", True):
            g = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
            gp = g.load()
            if grad == "top":
                y1 = min(self.H, y + hgt + int(self.H * 0.12))
                for yy in range(0, y1):
                    a = int(150 * (1 - yy / y1) ** 1.2)
                    for xx in range(self.W):
                        gp[xx, yy] = (0, 0, 0, a)
            else:
                y0 = int(self.H * 0.59)
                for yy in range(y0, self.H):
                    a = int(150 * ((yy - y0) / (self.H - y0)) ** 1.3)
                    for xx in range(self.W):
                        gp[xx, yy] = (0, 0, 0, a)
            out.alpha_composite(g)
        out.alpha_composite(self.shadow(L, 26, (0, 8), 150))
        return out

    def endcard(self, it):
        bg = self.brand_bg(spec=it.get("bg"))
        d = ImageDraw.Draw(bg)
        maxw = int(it.get("max_width", self.W - 160))
        parts = []
        if it.get("icon"):
            isz = int(it.get("icon_size", 300))
            ic = (
                Image.open(self.project.path(it["icon"]))
                .convert("RGBA")
                .resize((isz, isz), Image.LANCZOS)
            )
            m = Image.new("L", ic.size, 0)
            ImageDraw.Draw(m).rounded_rectangle(
                (0, 0, isz - 1, isz - 1), radius=int(isz * 0.22), fill=255
            )
            ic.putalpha(m)
            if it.get("name"):
                fn = self.font("h", it.get("name_size", 110), self.w_heading)
                nw, nh, nb = self.tsize(fn, it["name"])
                gap = int(isz * 0.12)
                if it.get("stack", True):
                    lock = Image.new(
                        "RGBA", (max(isz, nw), isz + gap + nh + 20), (0, 0, 0, 0)
                    )
                    lock.alpha_composite(ic, ((lock.width - isz) // 2, 0))
                    ImageDraw.Draw(lock).text(
                        ((lock.width - nw) // 2 - nb[0], isz + gap - nb[1]),
                        it["name"],
                        font=fn,
                        fill=_rgba(it.get("name_color", "#FFFFFF")),
                    )
                else:
                    lock = Image.new(
                        "RGBA", (isz + gap + nw, max(isz, nh)), (0, 0, 0, 0)
                    )
                    lock.alpha_composite(ic, (0, (lock.height - isz) // 2))
                    ImageDraw.Draw(lock).text(
                        (isz + gap - nb[0], (lock.height - nh) // 2 - nb[1]),
                        it["name"],
                        font=fn,
                        fill=_rgba(it.get("name_color", "#FFFFFF")),
                    )
            else:
                lock = ic
            parts.append(
                (
                    "logo",
                    self.shadow(lock, 36, (0, 20), 110),
                    lock.height,
                    int(it.get("logo_gap", 70)),
                )
            )
        if it.get("logo"):
            logo = Image.open(self.project.path(it["logo"])).convert("RGBA")
            lw = min(int(it.get("logo_width", 640)), maxw)
            logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
            parts.append(("logo", logo, logo.height, 60))
        fh = self.font(
            "h", it.get("headline_size", 84), it.get("headline_weight", self.w_heading)
        )
        hl = self.wrap(fh, it["headline"], maxw) if it.get("headline") else []
        _, lh, _ = self.tsize(fh, "ÉgjpÀ")
        if hl:
            parts.append(
                (
                    "headline",
                    hl,
                    int(lh * 1.15) * len(hl),
                    int(it.get("headline_gap", 90)),
                )
            )
        if it.get("url"):
            f2 = self.font("h", it.get("url_size", 60), self.w_semibold)
            uw, uh, ub = self.tsize(f2, it["url"])
            if uw + 120 > maxw:
                f2 = self.font(
                    "h",
                    int(it.get("url_size", 60) * maxw / (uw + 120)),
                    self.w_semibold,
                )
                uw, uh, ub = self.tsize(f2, it["url"])
            parts.append(("url", (f2, uw, uh, ub), 118, 80))
        if it.get("tagline"):
            f3 = self.font("b", it.get("tagline_size", 34), self.w_body)
            tl = self.wrap(f3, it["tagline"], maxw)
            _, th3, _ = self.tsize(f3, "ÉgjpÀ")
            parts.append(("tagline", (f3, tl), int(th3 * 1.35) * len(tl), 0))
        block = sum(h + g for _, _, h, g in parts) - (parts[-1][3] if parts else 0)
        y = int(it.get("y", max(80, (self.H - block) // 2)))
        for kind, obj, h, gap in parts:
            if kind == "logo":
                bg.alpha_composite(obj, ((self.W - obj.width) // 2, y))
            elif kind == "headline":
                self.text_block(
                    d,
                    obj,
                    fh,
                    self.W // 2,
                    y,
                    _rgba(it.get("headline_color", "#FFFFFF")),
                    1.15,
                    it.get("accent", ()),
                    _rgba(it.get("accent_color", "#FFD84D")),
                )
            elif kind == "url":
                f2, uw, uh, ub = obj
                pw, ph = uw + 120, 118
                px = (self.W - pw) // 2
                d.rounded_rectangle(
                    (px, y, px + pw, y + ph),
                    radius=ph // 2,
                    fill=_rgba(it.get("pill_bg", "#FFFFFF")),
                )
                d.text(
                    (px + 60 - ub[0], y + (ph - uh) // 2 - ub[1]),
                    it["url"],
                    font=f2,
                    fill=_rgba(it["pill_fg"]) if it.get("pill_fg") else self.primary,
                )
            elif kind == "tagline":
                f3, tl = obj
                self.text_block(
                    d,
                    tl,
                    f3,
                    self.W // 2,
                    y,
                    _rgba(it.get("tagline_color", "#FFFFFFE1")),
                    1.35,
                )
            y += h + gap
        return bg.convert("RGB")

    def doc_hero(self, it):
        src = self.project.path(it["image"])
        if not src.exists():
            raise FileNotFoundError(
                f"doc_hero image missing: {src} (run `screens` first)"
            )
        cv = Image.open(src).convert("RGBA")
        CW, CH = self.W, int(it.get("canvas_height", 1600))
        bg = Image.new("RGBA", (CW, CH), (244, 242, 255, 255))
        px = bg.load()
        for yy in range(CH):
            for xx in range(0, CW, 4):
                t = xx / CW * 0.5 + yy / CH * 0.5
                c = (int(244 + (232 - 244) * t), int(242 + (226 - 242) * t), 255)
                for k in range(min(4, CW - xx)):
                    px[xx + k, yy] = (*c, 255)
        dw = int(it.get("doc_width", min(1120, int(self.W * 0.83))))
        cv = cv.resize((dw, int(cv.height * dw / cv.width)), Image.LANCZOS)
        L = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        x, y = (CW - dw) // 2, int(it.get("doc_y", 120))
        L.alpha_composite(cv, (x, y))
        bg.alpha_composite(self.shadow(L, 40, (0, 24), 110))
        if it.get("badge"):
            d = ImageDraw.Draw(bg)
            f = self.font("h", it.get("badge_size", 34), "SemiBold")
            tw, th, bb = self.tsize(f, it["badge"])
            bw, bh = tw + 64, int(it.get("badge_size", 34) * 2.18)
            bx = min(CW - bw - 24, x + dw - bw + 40)
            by = max(24, y - 30)
            d.rounded_rectangle(
                (bx, by, bx + bw, by + bh), radius=bh // 2, fill=self.primary
            )
            d.text(
                (bx + 32 - bb[0], by + (bh - th) // 2 - bb[1]),
                it["badge"],
                font=f,
                fill=(255, 255, 255, 255),
            )
        return bg.convert("RGB")

    def code(self, it):
        lines = [
            str(x) for x in (it.get("lines") or str(it.get("text", "")).split("\n"))
        ]
        lang = it.get("lang", "generic")
        size = int(it.get("size", 34))
        f = self.font("m", size)
        lh = int(self.tsize(f, "ÉgjpÀ|")[1] * float(it.get("spacing", 1.55)))
        pad = int(it.get("pad", 36))
        w = int(it.get("w", self.W - 160))
        header = 60 if it.get("window", True) else 0
        numbers = it.get("numbers", False)
        gutter = int(size * 1.9) if numbers else 0
        h = header + pad + lh * len(lines) + pad
        x = (
            (self.W - w) // 2
            if it.get("align", "center") == "center" and "x" not in it
            else int(it.get("x", 80))
        )
        y = int(it.get("y", 640))
        L = self.canvas()
        d = ImageDraw.Draw(L)
        d.rounded_rectangle(
            (x, y, x + w, y + h),
            radius=int(it.get("radius", 26)),
            fill=_rgba(it.get("bg", "#0B0F14F5")),
            outline=_rgba(it.get("border", "#30363D")),
            width=3,
        )
        if header:
            for i, c in enumerate(("#F85149", "#D29922", "#3FB950")):
                cx = x + pad + 6 + i * 30
                d.ellipse(
                    (cx - 9, y + header // 2 - 9, cx + 9, y + header // 2 + 9),
                    fill=_hex(c),
                )
            if it.get("title"):
                ft = self.font("m", int(size * 0.8))
                tw, th, bb = self.tsize(ft, str(it["title"]))
                d.text(
                    (x + (w - tw) // 2 - bb[0], y + (header - th) // 2 - bb[1]),
                    str(it["title"]),
                    font=ft,
                    fill=(139, 148, 158, 255),
                )
            d.line((x, y + header, x + w, y + header), fill=(48, 54, 61, 255), width=2)
        hl = {int(v) for v in (it.get("hl") or [])}
        term = it.get("style") == "terminal" or (
            lang == "bash" and it.get("style") != "code"
        )
        yy = y + header + pad
        asc = f.getmetrics()[0]
        base_off = (
            int(lh * 0.12) + asc
        )  # one baseline per line: punctuation stays aligned with letters
        for li, ln in enumerate(lines):
            if li + 1 in hl:
                d.rounded_rectangle(
                    (x + 10, yy - int(lh * 0.06), x + w - 10, yy + int(lh * 0.94)),
                    radius=8,
                    fill=_rgba(it.get("hl_color", "#58A6FF2E")),
                )
            xx = x + pad + gutter
            if numbers:
                fn = self.font("m", int(size * 0.85))
                d.text(
                    (xx - int(size * 0.8), yy + base_off),
                    str(li + 1),
                    font=fn,
                    fill=(139, 148, 158, 150),
                    anchor="rs",
                )
            toks = (
                [("$ ", "prompt")] + tokenize(ln[2:], lang)
                if term and ln.startswith("$ ")
                else ([(ln, "muted")] if term else tokenize(ln, lang))
            )
            for t, k in toks:
                if not t:
                    continue
                if t.strip():
                    d.text(
                        (xx, yy + base_off),
                        t,
                        font=f,
                        fill=_rgba(CODE_COLORS.get(k, CODE_COLORS["text"])),
                        anchor="ls",
                    )
                xx += int(d.textlength(t, font=f))
            yy += lh
        return self.shadow(L, 30, (0, 14), int(it.get("shadow", 120)))

    def device_frame(self, it):
        x, y, w, h = int(it["x"]), int(it["y"]), int(it["w"]), int(it["h"])
        r = int(it.get("radius", 56))
        bz = int(it.get("bezel", 16))
        bg = self.brand_bg(spec=it.get("bg"))
        body = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(body)
        d.rounded_rectangle(
            (x - bz, y - bz, x + w + bz, y + h + bz),
            radius=r + bz,
            fill=_hex(it.get("bezel_color", "#0e0e14")) + (255,),
        )
        d.rounded_rectangle(
            (x - bz + 3, y - bz + 3, x + w + bz - 3, y + h + bz - 3),
            radius=r + bz - 3,
            outline=(70, 70, 86, 255),
            width=2,
        )
        bg.alpha_composite(self.shadow(body, 46, (0, 30), 120))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
        mask.save(self.out / f"{it['id']}_mask.png")
        return bg.convert("RGB")

    def render(self, only=None, log=print):
        outs = {}
        for it in self.project.get("overlays", {}).get("items", []):
            if only and it["id"] not in only:
                continue
            try:
                im = getattr(self, it["type"])(it)
                p = self.out / (
                    f"{it['id']}_bg.png"
                    if it["type"] == "device_frame"
                    else f"{it['id']}.png"
                )
                im.save(p)
                outs[it["id"]] = str(p)
                log(f"  overlay {it['id']} ({it['type']})")
            except FileNotFoundError as e:
                log(f"  overlay {it['id']} skipped: {e}")
        self.check_caption_overlap(log)
        return outs

    def check_caption_overlap(self, log=print):
        """Warn when a chip's bottom edge runs into the burned-caption band (`chip()` anchors `y` at the
        TOP with height size*2.38; `write_captions()` in assemble.py anchors `captions.y` at the BOTTOM of
        the text). Nothing else compares the two, so a beat with several stacked chips (e.g. numbered steps)
        can silently collide with the word-by-word subtitles once real voice-over durations are in."""
        cap = self.project.get("captions", {}) or {}
        if not cap.get("burn"):
            return
        cap_y = int(cap.get("y", int(self.H * 0.75)))
        cap_size = int(cap.get("size", 76))
        cap_top = cap_y - int(cap_size * 1.3)  # rough allowance for caps-height + outline above the anchor
        for it in self.project.get("overlays", {}).get("items", []):
            if it.get("type") != "chip" or "y" not in it:
                continue
            bottom = int(it["y"]) + int(int(it.get("size", 32)) * 2.38)
            if bottom > cap_top:
                log(f"  warning: chip {it['id']} bottom (y={bottom}) is close to or overlaps the caption band (starts ~y={cap_top}); move it up (lower y) or shorten the stack")
