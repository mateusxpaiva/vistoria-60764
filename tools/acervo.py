"""Copia o acervo de fotos e vídeos da vistoria de entrada (MSYS Vistorias) para este repositório."""
import asyncio, json, os, re, subprocess, html, zipfile, hashlib, shutil
import requests
from PIL import Image, ImageOps
from playwright.async_api import async_playwright

URL = "https://www.msysvistorias.com.br/inspection-web/templates/inspection/openview.html?aWR0SW5zcGVjdGlvbj0yMDYxNyZxPW93bmVyLWVtcHR5fG9jY3VwYW50LWVtcHR5fDE4NA=="
OUT = "laudo-fotos"
ORIG = "/tmp/originais"

GRAB = r"""
async (val) => {
  const s=document.getElementById('outerForm:selectAmbience'); s.value=val; s.onchange.call(s,new Event('change'));
  let prev=-1,stable=0;
  for(let k=0;k<80;k++){await new Promise(r=>setTimeout(r,500));
    const ms=[...document.querySelectorAll('.medias-div img,.medias-div source,.medias-div video,.medias-div a')].map(e=>e.getAttribute('src')||e.getAttribute('href')||'').filter(x=>x.includes('/20617/'));
    const ok=ms.length&&ms.every(x=>x.includes('/20617/'+val+'/'));
    const n=document.querySelectorAll('.medias-div').length;
    if(ok&&n===prev){if(++stable>=3)break}else stable=0; prev=n;}
  return [...document.querySelectorAll('.medias-div')].map(d=>{const c=[...d.querySelectorAll('img,source,video,a')].map(e=>e.getAttribute('src')||e.getAttribute('href')||'').filter(x=>x.includes('/20617/'));
    const v=c.find(x=>/\.(mp4|mov|m4v)/i.test(x)); return [d.innerText.trim(), (v||c[0]||'').split('?')[0]]}).filter(x=>x[1]);
}
"""

async def scrape():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.goto(URL, wait_until="domcontentloaded", timeout=180000)
        print("titulo:", await pg.title(), flush=True)
        await pg.wait_for_selector("#outerForm\\:selectAmbience", timeout=180000)
        await pg.wait_for_timeout(3000)
        opts = await pg.eval_on_selector_all("#outerForm\\:selectAmbience option", "os=>os.filter(o=>o.value).map(o=>[o.value,o.text])")
        data = []
        for val, name in opts:
            items = await pg.evaluate(GRAB, val)
            print(name, len(items), flush=True)
            data.append({"id": val, "nome": name, "midias": [{"legenda": c, "url": u} for c, u in items]})
        await b.close()
        return data

def slug(s):
    s = re.sub(r"[^\w\s-]", "", s.lower(), flags=re.U)
    for a, b2 in zip("áàãâéêíóôõúç", "aaaaeeiooouc"): s = s.replace(a, b2)
    return re.sub(r"[\s_]+", "-", s).strip("-")

def main():
    data = asyncio.run(scrape())
    total = sum(len(a["midias"]) for a in data)
    print("total", total, flush=True)
    assert total > 2000, "acervo incompleto"
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(ORIG, exist_ok=True)
    sess = requests.Session()
    for a in data:
        a["slug"] = f"{data.index(a)+1:02d}-{slug(a['nome'])}"
        d_full = f"{OUT}/{a['slug']}"; d_th = f"{OUT}/{a['slug']}/mini"; d_o = f"{ORIG}/{a['slug']}"
        for d in (d_full, d_th, d_o): os.makedirs(d, exist_ok=True)
        for i, m in enumerate(a["midias"], 1):
            ext = os.path.splitext(m["url"])[1].lower() or ".jpg"
            base = f"{i:03d}"
            o = f"{d_o}/{base}{ext}"
            for t in range(4):
                try:
                    r = sess.get(m["url"], timeout=120); r.raise_for_status(); open(o, "wb").write(r.content); break
                except Exception as e:
                    print("retry", m["url"], e, flush=True)
            m["sha256"] = hashlib.sha256(open(o, "rb").read()).hexdigest()
            if ext in (".mp4", ".mov", ".m4v"):
                f = f"{d_full}/{base}.mp4"
                subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", o, "-vf", "scale='if(gt(iw,ih),1280,-2)':'if(gt(iw,ih),-2,1280)'", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", f], check=True)
                th = f"{d_th}/{base}.jpg"
                subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", "1", "-i", f, "-frames:v", "1", "-vf", "scale=480:-2", th])
                m.update(tipo="video", arquivo=f"{a['slug']}/{base}.mp4", mini=f"{a['slug']}/mini/{base}.jpg")
            else:
                im = ImageOps.exif_transpose(Image.open(o)).convert("RGB")
                big = im.copy(); big.thumbnail((1600, 1600)); big.save(f"{d_full}/{base}.jpg", quality=80, optimize=True, progressive=True)
                sm = im.copy(); sm.thumbnail((480, 480)); sm.save(f"{d_th}/{base}.jpg", quality=72, optimize=True, progressive=True)
                m.update(tipo="foto", arquivo=f"{a['slug']}/{base}.jpg", mini=f"{a['slug']}/mini/{base}.jpg")
        with zipfile.ZipFile(f"/tmp/{a['slug']}.zip", "w", zipfile.ZIP_STORED) as z:
            for fn in sorted(os.listdir(d_o)): z.write(f"{d_o}/{fn}", f"{a['slug']}/{fn}")
        print("ok", a["nome"], flush=True)
    json.dump(data, open(f"{OUT}/acervo.json", "w"), ensure_ascii=False, indent=1)
    gerar_pagina(data)

CSS = """*,*::before,*::after{box-sizing:border-box}body{margin:0}img,video{max-width:100%}
:root{--navy:#0a1a33;--navy-2:#0f2a52;--blue:#1d5fd1;--sky:#4aa3ff;--ice:#e8f1fd;--bg:#f4f7fc;--surface:#fff;--ink:#0d1b2e;--muted:#5a6b85;--line:#dbe4f1;--chip:#eaf1fb;--chip-ink:#1b3a66;--f-ui:"Poppins",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--f-mono:"JetBrains Mono",ui-monospace,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#07111f;--surface:#0e1c31;--ink:#e6eefb;--muted:#93a6c3;--line:#1c2f4b;--chip:#132743;--chip-ink:#bcd6ff;--ice:#0f2340;--blue:#4c8dff;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#07111f;--surface:#0e1c31;--ink:#e6eefb;--muted:#93a6c3;--line:#1c2f4b;--chip:#132743;--chip-ink:#bcd6ff;--ice:#0f2340;--blue:#4c8dff;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font-family:var(--f-ui);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
.in{max-width:1180px;margin:0 auto;padding-left:max(18px,env(safe-area-inset-left,0px));padding-right:max(18px,env(safe-area-inset-right,0px))}
.hero{background:linear-gradient(135deg,var(--navy) 0%,var(--navy-2) 60%,#123d78 100%);color:#eaf2ff}
.hero .in{padding-block:34px 30px;display:grid;grid-template-columns:minmax(0,1fr);gap:14px}
.back{color:#8cc4ff;font-size:13px;text-decoration:none}.back:hover{text-decoration:underline}
h1{margin:0;font-weight:600;font-size:clamp(24px,4vw,38px);line-height:1.15;letter-spacing:-.02em}
.sub{margin:0;color:#a9bfdf;max-width:70ch;font-weight:300}
.idx{display:flex;flex-wrap:wrap;margin:6px 0 0}.idx a{font:500 12.5px var(--f-ui);color:#cfe2ff;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);border-radius:999px;padding:5px 11px;margin:0 6px 6px 0;text-decoration:none}.idx a:hover{background:rgba(255,255,255,.16)}
main.in{padding-block:24px 40px}
.amb{margin:0 0 34px;scroll-margin-top:12px}
.amb h2{margin:0 0 6px;font-size:20px;font-weight:600}.amb h2 small{font:500 12px var(--f-mono);color:var(--blue);background:var(--ice);padding:2px 8px;border-radius:6px;margin-left:8px;vertical-align:middle}
details{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin:0 0 14px}
summary{cursor:pointer;font-weight:500;font-size:13.5px;color:var(--blue)}
details ol{margin:10px 0 2px;padding-left:18px;font-size:13px;color:var(--muted)}details li{margin-bottom:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.m{background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden;display:block;text-decoration:none;color:var(--ink)}
.m .ph{position:relative;height:0;padding-top:75%;background:#06101f}
.m img{position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover}
.m .play{position:absolute;left:8px;bottom:8px;font:600 11px var(--f-mono);background:var(--blue);color:#fff;padding:3px 8px;border-radius:6px}
.m span.c{display:block;font-size:12px;padding:6px 8px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
footer{border-top:1px solid var(--line)}footer .in{padding-block:20px 30px;color:var(--muted);font-size:13px}footer strong{color:var(--ink)}
"""

def gerar_pagina(data):
    texto = json.load(open("tools/laudo_texto.json"))
    e = html.escape
    def txt_for(nome):
        for k, v in texto.items():
            if k.split(". ", 1)[1].lower() == nome.lower(): return k, v
        return nome, []
    idx = "".join(f'<a href="#{a["slug"]}">{e(a["nome"])}</a>' for a in data)
    secs = []
    for a in data:
        k, linhas = txt_for(a["nome"])
        det = f'<details><summary>Descrição do laudo para este ambiente ({len(linhas)} itens)</summary><ol>' + "".join(f"<li>{e(l)}</li>" for l in linhas) + "</ol></details>" if linhas else ""
        cards = []
        for i, m in enumerate(a["midias"], 1):
            play = '<span class="play">▶ vídeo</span>' if m["tipo"] == "video" else ""
            cards.append(f'<a class="m" href="{m["arquivo"]}" target="_blank" rel="noopener"><span class="ph"><img loading="lazy" src="{m["mini"]}" alt="{e(m["legenda"])}">{play}</span><span class="c">{i:03d} · {e(m["legenda"])}</span></a>')
        secs.append(f'<section class="amb" id="{a["slug"]}"><h2>{e(k)}<small>{len(a["midias"])}</small></h2>{det}<div class="grid">{"".join(cards)}</div></section>')
    fotos = sum(1 for a in data for m in a["midias"] if m["tipo"] == "foto"); vids = sum(1 for a in data for m in a["midias"] if m["tipo"] == "video")
    page = f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><meta name="robots" content="noindex, nofollow"><meta name="author" content="Mateus Paiva"><meta name="theme-color" content="#0a1a33"><title>Acervo da Vistoria 60764</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600&family=JetBrains+Mono:wght@500&display=swap"><style>{CSS}</style></head><body>
<section class="hero"><div class="in"><a class="back" href="../">← Voltar aos apontamentos</a><h1>Acervo da vistoria de entrada</h1>
<p class="sub">Cópia integral das {fotos} fotos e {vids} vídeos da vistoria realizada pela administradora em 28/10/2026 (MSYS Vistorias, imóvel 60764), organizados pelos ambientes do laudo. Toque em uma imagem para ampliar. Os arquivos originais, com verificação SHA-256, estão em <a style="color:#8cc4ff" href="acervo.json">acervo.json</a> e nos pacotes da seção Releases do repositório.</p>
<nav class="idx" aria-label="Ambientes">{idx}</nav></div></section>
<main class="in">{"".join(secs)}</main>
<footer><div class="in">Fonte: link público da vistoria citado na página 1 do Laudo de Vistoria de Entrada. Copiado em {os.environ.get("DATA_COPIA","")}. · Sistema desenvolvido por <strong>Mateus Paiva</strong></div></footer></body></html>'''
    open(f"{OUT}/index.html", "w").write(page)

if __name__ == "__main__":
    main()
