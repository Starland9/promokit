"""Screen recorder for Playwright: CDP screencast -> PNG frames -> 30fps mp4. Injects a fake cursor."""
import asyncio, base64, json, os, pathlib, shutil, subprocess, time, math
from playwright.async_api import async_playwright

CURSOR_JS = r"""
(() => {
  const install = () => {
  if (window.__cur) return;
  const c = document.createElement('div'); c.id='__fakecursor';
  c.innerHTML = `<svg width="28" height="34" viewBox="0 0 28 34" xmlns="http://www.w3.org/2000/svg"><path d="M2 2 L2 26 L8.5 20.5 L13 30 L17.5 28 L13 18.5 L21 18 Z" fill="#111" stroke="#fff" stroke-width="2" stroke-linejoin="round"/></svg>`;
  Object.assign(c.style,{position:'fixed',left:'0px',top:'0px',zIndex:'2147483647',pointerEvents:'none',transform:'translate(-2px,-2px)',filter:'drop-shadow(0 2px 3px rgba(0,0,0,.35))',transition:'none'});
  document.documentElement.appendChild(c);
  const r = document.createElement('div'); r.id='__clickring';
  Object.assign(r.style,{position:'fixed',width:'36px',height:'36px',borderRadius:'50%',border:'3px solid #2563eb',zIndex:'2147483646',pointerEvents:'none',opacity:'0',transform:'translate(-18px,-18px) scale(.4)'});
  document.documentElement.appendChild(r);
  window.__cur = {x:0,y:0};
  window.__setCursorMode = (m)=>{ c.style.display = (m==='tap')?'none':''; r.style.width=r.style.height=(m==='tap')?'64px':'36px'; r.style.borderWidth=(m==='tap')?'4px':'3px'; r.style.transform=(m==='tap')?'translate(-32px,-32px) scale(.4)':'translate(-18px,-18px) scale(.4)'; window.__cursorMode=m; };
  window.__moveCursor = (x,y)=>{ window.__cur={x,y}; c.style.left=x+'px'; c.style.top=y+'px'; };
  window.__clickFx = ()=>{ const {x,y}=window.__cur; const tap=window.__cursorMode==='tap'; const o=tap?32:18; r.style.left=x+'px'; r.style.top=y+'px'; r.style.transition='none'; r.style.opacity='.9'; r.style.transform=`translate(-${o}px,-${o}px) scale(.4)`; requestAnimationFrame(()=>{ r.style.transition='opacity .45s ease-out, transform .45s ease-out'; r.style.opacity='0'; r.style.transform=`translate(-${o}px,-${o}px) scale(1.4)`; }); };
  // keep cursor after DOM swaps
  new MutationObserver(()=>{ if(!document.getElementById('__fakecursor')){ document.documentElement.appendChild(c); document.documentElement.appendChild(r);} }).observe(document.documentElement,{childList:true});
  };
  if (document.documentElement) install(); else document.addEventListener('DOMContentLoaded', install);
})();
"""

def ease(t): return 0.5-0.5*math.cos(math.pi*t)  # ease in-out

class Recorder:
    def __init__(self, page, outdir, fps=30, width=1920, height=1080):
        self.page=page; self.outdir=pathlib.Path(outdir); self.fps=fps; self.W=width; self.H=height; self.frames=[]; self.cdp=None; self.t0=None; self.running=False; self.marks=[]
    async def start(self):
        if self.outdir.exists(): shutil.rmtree(self.outdir)
        self.outdir.mkdir(parents=True)
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        await self.cdp.send("Page.startScreencast", {"format":"png","everyNthFrame":1,"maxWidth":self.W,"maxHeight":self.H})
        self.t0=time.time(); self.running=True
    def _on_frame(self, ev):
        if not self.running: return
        i=len(self.frames); p=self.outdir/f"f{i:06d}.png"
        p.write_bytes(base64.b64decode(ev["data"]))
        self.frames.append((ev["metadata"].get("timestamp", time.time()), p))
        asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]}))
    def mark(self, label):
        self.marks.append((label, round(time.time()-self.t0,3)))
    async def stop(self, out_mp4):
        end_ts=time.time(); self.running=False
        try: await self.cdp.send("Page.stopScreencast")
        except Exception: pass
        await asyncio.sleep(0.3)
        if not self.frames: raise RuntimeError("no frame captured")
        # build concat list with real durations (VFR) then encode CFR; keep static tail up to stop() and align marks on the first frame
        first_ts=self.frames[0][0]
        self.marks=[(label, round(t - max(0.0, first_ts - self.t0), 3)) for label, t in self.marks]
        lst=self.outdir/"list.txt"
        with open(lst,"w") as f:
            for i,(ts,p) in enumerate(self.frames):
                nxt = self.frames[i+1][0] if i+1<len(self.frames) else max(ts+1/self.fps, end_ts)
                d=max(nxt-ts, 0.001)
                f.write(f"file '{p.name}'\nduration {d:.4f}\n")
            f.write(f"file '{self.frames[-1][1].name}'\n")
        cmd=["ffmpeg","-y","-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",str(lst),
             "-vf",f"fps={self.fps},scale={self.W}:{self.H}:flags=lanczos,format=yuv420p","-c:v","libx264","-preset","medium","-crf","16",str(out_mp4)]
        subprocess.run(cmd, check=True)
        json.dump(self.marks, open(str(out_mp4)+'.marks.json','w'))
        dur = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(out_mp4)]))
        return dur, len(self.frames)

async def prep(page):
    await page.add_init_script(CURSOR_JS)

async def ensure_cursor(page, x=None, y=None, mode=None):
    await page.evaluate(CURSOR_JS)
    if mode: await page.evaluate(f"window.__setCursorMode('{mode}')")
    if x is not None: await page.evaluate(f"window.__moveCursor({x},{y})")

async def move(page, x, y, dur=0.6, steps=None):
    cur = await page.evaluate("() => window.__cur || {x:0,y:0}")
    x0,y0=cur["x"],cur["y"]; steps = steps or max(int(dur*60),8)
    for i in range(1,steps+1):
        t=ease(i/steps); nx=x0+(x-x0)*t; ny=y0+(y-y0)*t
        await page.evaluate(f"window.__moveCursor({nx},{ny})")
        await page.mouse.move(nx,ny)
        await asyncio.sleep(dur/steps)

async def click(page, x, y, dur=0.6, pause=0.25):
    await move(page,x,y,dur); await asyncio.sleep(0.12)
    await page.evaluate("window.__clickFx()"); await page.mouse.click(x,y); await asyncio.sleep(pause)

async def click_el(page, locator, dur=0.7, pause=0.3, dx=0, dy=0):
    bb = await locator.bounding_box(); assert bb, "no bbox"
    await click(page, bb["x"]+bb["width"]/2+dx, bb["y"]+bb["height"]/2+dy, dur, pause)

async def hover_el(page, locator, dur=0.6, dx=0, dy=0):
    bb = await locator.bounding_box(); assert bb
    await move(page, bb["x"]+bb["width"]/2+dx, bb["y"]+bb["height"]/2+dy, dur)

async def smooth_scroll(page, to_y, dur=1.2, el=None):
    js = """async ([toY, dur, sel]) => { const el = sel? document.querySelector(sel): null; const obj = el||window; const y0 = el? el.scrollTop : window.scrollY; const t0=performance.now();
      await new Promise(res=>{ function step(){ const t=Math.min(1,(performance.now()-t0)/dur); const e=0.5-0.5*Math.cos(Math.PI*t); const y=y0+(toY-y0)*e; if(el) el.scrollTop=y; else window.scrollTo(0,y); if(t<1) requestAnimationFrame(step); else res(); } requestAnimationFrame(step); }); }"""
    await page.evaluate(js, [to_y, dur*1000, el])

async def type_text(page, locator, text, delay=45):
    await locator.click(); await locator.fill("")
    await locator.type(text, delay=delay)

async def accept_cookies(page):
    try: await page.get_by_role("button", name="Tout accepter").click(timeout=2500); await asyncio.sleep(0.4)
    except Exception: pass

async def hide_scrollbars(page):
    await page.add_style_tag(content="::-webkit-scrollbar{width:0!important;height:0!important} html{scrollbar-width:none}")
