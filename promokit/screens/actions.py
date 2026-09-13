"""Scene DSL executor: a scene is a list of steps (YAML) driven on a real browser and recorded at 30 fps.

Steps (one key per item):
  wait: 1.2                         seconds
  mark: label                       timestamp marker (saved next to the mp4, used for editing)
  goto: "/path"                     navigate (networkidle) and re-inject the cursor
  cursor: [x, y]                    place the fake cursor without moving
  move: {selector|xy, dur, dx, dy}  move cursor to element (or [x,y])
  hover: {selector, dur, dx, dy}    same as move (semantic alias)
  click: {selector|xy, dur, pause}  real click with cursor animation
  fxclick: {selector, dur, pause}   visual-only click (no event fired) - use for buttons that need auth / would navigate away
  scroll: {to, dur, selector?}      smooth scroll of window (or an element) to y
  scroll_to: {selector|role|text, offset, dur}  smooth scroll so the element top sits `offset` px below the viewport top
  type: {selector, text, delay}     focus + clear + keystroke typing (React-safe)
  fill: {selector, text}            instant fill (no keystrokes)
  set_value: {selector, value}      set an input value via the native setter + input/change events (color inputs, etc.)
  press: "Escape"                   keyboard key
  eval: "js"                        run JS in page
  wait_load: networkidle            wait for load state
  style: "css"                      inject CSS (e.g. hide a header)
"""
from __future__ import annotations
import asyncio, json, pathlib, time
from .recorder import Recorder, prep, ensure_cursor, move, click, click_el, hover_el, smooth_scroll, accept_cookies, hide_scrollbars

SET_VALUE_JS = "(el,v)=>{ const proto = el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; const s=Object.getOwnPropertyDescriptor(proto,'value').set; s.call(el,v); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }"

async def nav(page, url: str, retries: int = 2):
    """Navigate robustly: DOM ready (60 s), then best-effort network idle (8 s). Retries on timeout."""
    last = None
    for i in range(retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000); break
        except Exception as e:
            last = e; await asyncio.sleep(2 * (i + 1))
    else: raise last
    try: await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception: pass
    await page.wait_for_timeout(600)

def _loc(page, spec):
    if isinstance(spec, str): return page.locator(spec).first
    sel = spec.get("selector"); nth = spec.get("nth", 0)
    if sel: return page.locator(sel).nth(nth)          # selector wins (a `type` step also carries a `text` payload)
    if spec.get("role"): return page.get_by_role(spec["role"], name=spec.get("name"), exact=spec.get("exact", False)).nth(nth)
    if spec.get("text"): return page.get_by_text(spec["text"], exact=spec.get("exact", False)).nth(nth)
    raise ValueError(f"step needs selector, role or text: {spec}")

async def run_step(page, rec, step: dict, base_url: str):
    (k, v), = step.items()
    if k == "wait": await asyncio.sleep(float(v))
    elif k == "mark": rec and rec.mark(str(v))
    elif k == "goto":
        await nav(page, base_url + v if v.startswith("/") else v); await hide_scrollbars(page); await ensure_cursor(page, mode=(await page.evaluate("() => window.__cursorMode || null")))
    elif k == "cursor": await ensure_cursor(page, v[0], v[1])
    elif k in ("move", "hover"):
        if "xy" in v: await move(page, v["xy"][0], v["xy"][1], v.get("dur", 0.6))
        else: await hover_el(page, _loc(page, v), v.get("dur", 0.7), v.get("dx", 0), v.get("dy", 0))
    elif k == "click":
        if "xy" in v: await click(page, v["xy"][0], v["xy"][1], v.get("dur", 0.6), v.get("pause", 0.3))
        else: await click_el(page, _loc(page, v), v.get("dur", 0.7), v.get("pause", 0.3), v.get("dx", 0), v.get("dy", 0))
    elif k == "fxclick":
        await hover_el(page, _loc(page, v), v.get("dur", 0.8), v.get("dx", 0), v.get("dy", 0)); await asyncio.sleep(0.15)
        await page.evaluate("window.__clickFx()"); await asyncio.sleep(v.get("pause", 0.8))
    elif k == "scroll": await smooth_scroll(page, v["to"], v.get("dur", 1.2), v.get("selector"))
    elif k == "scroll_to":
        y = await _loc(page, v).evaluate("(e, off) => Math.max(0, e.getBoundingClientRect().top + window.scrollY - off)", v.get("offset", 120))
        await smooth_scroll(page, y, v.get("dur", 1.0))
    elif k == "type":
        loc = _loc(page, v); await loc.focus(); await loc.fill(""); await loc.type(v["text"], delay=v.get("delay", 12))
    elif k == "fill": await _loc(page, v).fill(v["text"])
    elif k == "set_value": await _loc(page, v).evaluate(SET_VALUE_JS, v["value"])
    elif k == "press": await page.keyboard.press(v)
    elif k == "eval": await page.evaluate(v)
    elif k == "wait_load":
        try: await page.wait_for_load_state("domcontentloaded", timeout=30000); await page.wait_for_load_state(v if isinstance(v, str) else "networkidle", timeout=8000)
        except Exception: pass
    elif k == "style": await page.add_style_tag(content=v)
    else: raise ValueError(f"unknown step: {k}")

async def run_scene(page, scene: dict, base_url: str, out_mp4: pathlib.Path, frames_dir: pathlib.Path, fps: int = 30, size=(1920, 1080), cursor_mode=None):
    """scene: {start: {url, cursor}, steps: [...], record: true}. Returns (duration, nframes)."""
    st = scene.get("start", {})
    if st.get("url"):
        await nav(page, base_url + st["url"] if st["url"].startswith("/") else st["url"]); await hide_scrollbars(page)
    cur = st.get("cursor"); await ensure_cursor(page, *(cur or ()), mode=cursor_mode); await asyncio.sleep(0.4)
    for s in scene.get("pre", []): await run_step(page, None, s, base_url)
    rec = Recorder(page, frames_dir, fps=fps, width=size[0], height=size[1]); await rec.start(); await asyncio.sleep(0.3)
    for s in scene["steps"]: await run_step(page, rec, s, base_url)
    return await rec.stop(out_mp4)

async def run_capture(browser, cap: dict, base_url: str, out_dir: pathlib.Path, width=1920, height=1080):
    """High-res still capture: {url, dpr, steps, hide_css, element: {selector | finder_js}, out}."""
    ctx = await browser.new_context(viewport={"width": width, "height": height}, locale=cap.get("locale", "fr-FR"), device_scale_factor=cap.get("dpr", 2))
    page = await ctx.new_page(); await prep(page)
    await nav(page, base_url + cap["url"] if cap["url"].startswith("/") else cap["url"]); await page.wait_for_timeout(600)
    await accept_cookies(page); await ensure_cursor(page, -100, -100)
    for s in cap.get("steps", []): await run_step(page, None, s, base_url)
    await page.evaluate("window.scrollTo(0,0); window.__moveCursor(-100,-100)")
    if cap.get("hide_css"): await page.add_style_tag(content=cap["hide_css"])
    el = cap.get("element", {})
    if el.get("finder_js"): rect = await page.evaluate(el["finder_js"])
    else: rect = await page.locator(el["selector"]).first.evaluate("e=>e.getBoundingClientRect().toJSON()")
    if not rect: raise RuntimeError("capture element not found")
    out = out_dir / cap["out"]
    await page.screenshot(path=str(out), scale="device", full_page=True, clip={"x": rect["x"], "y": rect["y"], "width": rect["width"], "height": rect["height"]})
    await ctx.close(); return out

async def run_all(scenes: dict, captures: list, base_url: str, out_dir: pathlib.Path, only: list | None = None, width=1920, height=1080, fps=30, viewport: dict | None = None):
    """viewport: {width, height, dpr, mobile, cursor} to emulate a device (CSS px); frames are recorded at device pixels and scaled to width x height."""
    from playwright.async_api import async_playwright
    out_dir.mkdir(parents=True, exist_ok=True); results = {}; vp = viewport or {}
    css_w, css_h, dpr = vp.get("width", width), vp.get("height", height), vp.get("dpr", 1); mobile = bool(vp.get("mobile", False)); cursor_mode = vp.get("cursor")
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=[f"--force-device-scale-factor={dpr}", "--hide-scrollbars"])
        ctx = await b.new_context(viewport={"width": css_w, "height": css_h}, locale="fr-FR", device_scale_factor=dpr, is_mobile=mobile, has_touch=mobile,
                                  **({"user_agent": vp["user_agent"]} if vp.get("user_agent") else {}))
        page = await ctx.new_page(); await prep(page)
        await nav(page, base_url); await accept_cookies(page)
        for name, sc in scenes.items():
            if only and name not in only: continue
            try:
                d, n = await run_scene(page, sc, base_url, out_dir / f"{name}.mp4", out_dir / "frames" / name, fps, (width, height), cursor_mode)
                results[name] = {"duration": d, "frames": n}; print(f"  scene {name}: {d:.2f}s ({n} frames)")
            except Exception as e:
                results[name] = {"error": str(e)[:300]}; print(f"  scene {name} FAILED: {str(e)[:200]}")
        for cap in captures:
            if only and cap["out"] not in only and cap.get("id") not in only: continue
            try: out = await run_capture(b, cap, base_url, out_dir, width, height); print(f"  capture {out.name}")
            except Exception as e: print(f"  capture {cap.get('out')} FAILED: {str(e)[:200]}")
        await b.close()
    (out_dir / "scenes.json").write_text(json.dumps(results, indent=1)); return results
