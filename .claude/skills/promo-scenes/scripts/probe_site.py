#!/usr/bin/env python
"""Site reconnaissance for promokit scenes: screenshots, text, links, controls, theme.
usage: python probe_site.py https://site.tld [/path ...] [--out DIR] [--width 1920] [--mobile]"""
import asyncio, json, sys, argparse, pathlib
from playwright.async_api import async_playwright

JS_CONTROLS = """() => {
  const q=s=>Array.from(document.querySelectorAll(s)); const vis=e=>!!(e.offsetWidth||e.offsetHeight);
  const r=e=>{const b=e.getBoundingClientRect(); return [Math.round(b.x),Math.round(b.y),Math.round(b.width),Math.round(b.height)]};
  return {
    links: q('a[href]').map(a=>[a.getAttribute('href'),(a.innerText||'').trim().slice(0,40)]).filter((v,i,a)=>a.findIndex(x=>x[0]===v[0])===i).slice(0,80),
    buttons: q('button,[role=button]').filter(vis).map(b=>({text:(b.innerText||b.getAttribute('aria-label')||'').trim().slice(0,40), rect:r(b)})).slice(0,80),
    inputs: q('input,textarea,select').map(i=>({tag:i.tagName,type:i.type,id:i.id,name:i.name,ph:i.placeholder,val:(i.value||'').slice(0,30),vis:vis(i),rect:r(i)})),
    special: q('[role=switch],[role=combobox],[role=tab],input[type=file],input[type=color],input[type=range]').map(e=>({tag:e.tagName,role:e.getAttribute('role')||e.type,label:(e.innerText||e.getAttribute('aria-label')||'').trim().slice(0,30),rect:r(e)})),
    theme: (()=>{const s=getComputedStyle(document.documentElement); const out={}; for(const k of ['--primary','--accent','--background','--foreground','--secondary','--muted','--border']) out[k]=s.getPropertyValue(k).trim(); const h1=document.querySelector('h1'); const p=document.querySelector('p'); const btn=q('a,button').find(e=>vis(e)&&getComputedStyle(e).backgroundColor!=='rgba(0, 0, 0, 0)'&&/^(a|button)$/i.test(e.tagName)&&e.innerText.trim()); out.h1font=h1?getComputedStyle(h1).fontFamily:null; out.pfont=p?getComputedStyle(p).fontFamily:null; out.buttonBg=btn?getComputedStyle(btn).backgroundColor:null; out.bodyBg=getComputedStyle(document.body).backgroundColor; return out;})(),
    docHeight: document.documentElement.scrollHeight
  }; }"""

async def main():
    ap=argparse.ArgumentParser(); ap.add_argument("url"); ap.add_argument("paths", nargs="*"); ap.add_argument("--out", default="/tmp/probe"); ap.add_argument("--width", type=int, default=1920); ap.add_argument("--mobile", action="store_true", help="emulate a phone: 432x768 CSS px, DPR 2.5, touch"); a=ap.parse_args()
    out=pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True); base=a.url.rstrip("/"); paths=a.paths or ["/"]
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await (b.new_context(viewport={"width":432,"height":768}, device_scale_factor=2.5, is_mobile=True, has_touch=True, locale="fr-FR") if a.mobile else b.new_context(viewport={"width":a.width,"height":1080}, locale="fr-FR"))
        page=await ctx.new_page()
        report={}
        for path in paths:
            url=base+path if path.startswith("/") else path
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try: await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception: pass
            await page.wait_for_timeout(2500)
            for name in ("Tout accepter","Accepter","Accept all","Accept","OK"):
                try: await page.get_by_role("button", name=name).click(timeout=800); break
                except Exception: pass
            slug=(path.strip("/").replace("/","_").replace("?","_").replace("=","-") or "home")
            await page.screenshot(path=str(out/f"{slug}_full.png"), full_page=True); await page.screenshot(path=str(out/f"{slug}_fold.png"))
            info=await page.evaluate(JS_CONTROLS); info["text"]=(await page.evaluate("() => document.body.innerText"))[:6000]; info["title"]=await page.title(); info["final_url"]=page.url
            report[path]=info
            print(f"== {path} -> {page.url} | {info['title']} | docHeight {info['docHeight']}")
            print("  links:", [l[0] for l in info["links"]][:30]); print("  buttons:", [x["text"] for x in info["buttons"] if x["text"]][:30])
            print("  inputs:", [(i["id"] or i["name"] or i["ph"], i["type"]) for i in info["inputs"]][:30]); print("  special:", info["special"][:12]); print("  theme:", info["theme"])
        (out/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1)); print(f"\nscreenshots + report.json in {out}")
        await b.close()
asyncio.run(main())
