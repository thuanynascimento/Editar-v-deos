"""Estilo "RGA" (referência da cliente: Reels "Comecei o jiu-jitsu com 40 anos").

Elementos (HyperFrames), todos NA FRENTE do vídeo (sem recorte da pessoa):
  * titulo   — palavras grandes em caixa alta, fonte condensada (Anton), brancas com sombra dura
               azul-marinho deslocada; cada palavra "pula" no momento em que é dita; brilho (✦)
               depois da última; manuscrito pequeno (Caveat) acima ou abaixo.
  * etiquetas — 1–3 etiquetas brancas arredondadas, texto azul-marinho Montserrat 900, levemente
               inclinadas e alternando esquerda/direita (como "DEPOIS DOS 40 / TREINAM MELHOR").
  * cta      — botão azul-marinho com ícone de calendário e texto branco ("Agende pelo link da bio").
  * zoom     — (opcional, --zoom-cuts) punch-in alternado 1.0 / 1.15 nos pontos de corte do EDL,
               como as trocas de enquadramento da referência.

Spec JSON (lista; tempos na timeline do vídeo cortado; y = topo do bloco em % da altura):
  [{"type": "titulo", "id": "t1", "start": 0.9, "end": 3.0, "y": 15,
    "words": [["JIU-JITSU", 1.04]], "script": "não deixa seu filho agressivo", "script_at": 1.5,
    "script_pos": "below"},
   {"type": "etiquetas", "id": "e1", "start": 5.9, "end": 9.25, "y": 14,
    "items": [["DISCIPLINA", 6.2], ["RESPEITO", 7.2], ["LIDAR COM A FRUSTRAÇÃO", 8.4]]},
   {"type": "cta", "id": "c1", "start": 18.4, "end": 21.1, "y": 58, "text": "Agende pelo link da bio"}]

Uso:
    python tools/make_estilo_rga.py <hf_dir> spec.json [--zoom-cuts edit/edl.json]
Fontes necessárias em <hf_dir>/assets/fonts: anton.woff2, caveat-700.woff2, montserrat-900-normal.woff2,
montserrat-800-normal.woff2 (npm pack @fontsource/anton @fontsource/caveat @fontsource/montserrat).
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAVY = "#093B6E"

FONTS = """
    @font-face { font-family: "AntonR"; font-weight: 400; src: url("assets/fonts/anton.woff2") format("woff2"); }
    @font-face { font-family: "CaveatR"; font-weight: 700; src: url("assets/fonts/caveat-700.woff2") format("woff2"); }
    @font-face { font-family: "MontserratR"; font-weight: 900; src: url("assets/fonts/montserrat-900-normal.woff2") format("woff2"); }
    @font-face { font-family: "MontserratR"; font-weight: 800; src: url("assets/fonts/montserrat-800-normal.woff2") format("woff2"); }
"""

SPARKLE = ('<svg class="spk" viewBox="0 0 40 40"><path d="M20 0 C22 14 26 18 40 20 C26 22 22 26 20 40 '
           'C18 26 14 22 0 20 C14 18 18 14 20 0Z" fill="#fff"/></svg>')


def titulo(sp, W, H, navy):
    tid, s, e = sp["id"], sp["start"], sp["end"]
    words = sp["words"]
    text_len = sum(len(w) for w, _ in words) + len(words) - 1
    size = int(min(sp.get("size", 150), W * 0.84 / max(text_len * 0.47, 1)))
    top = int(H * sp.get("y", 15) / 100)
    sh = max(4, size // 22)
    spans = " ".join(f'<span class="w" id="{tid}-w{i}">{html.escape(w)}</span>' for i, (w, _) in enumerate(words))
    script = sp.get("script", "")
    s_size = sp.get("script_size", max(58, int(size * 0.5)))
    pos = sp.get("script_pos", "below")
    script_html = (f'<div id="{tid}-s" class="scr" style="font-size:{s_size}px">{html.escape(script)}</div>'
                   if script else "")
    inner = (script_html + f'<div id="{tid}-big" class="big">{spans}{SPARKLE}</div>' if pos == "above"
             else f'<div id="{tid}-big" class="big">{spans}{SPARKLE}</div>' + script_html)
    css = f"""
    #{tid}-box {{ position: absolute; left: 0; top: {top}px; width: {W}px; text-align: center; }}
    #{tid}-box .big {{ font-family: "AntonR", sans-serif; font-size: {size}px; line-height: 1.02; color: #fff;
      text-transform: uppercase; letter-spacing: 0.005em; white-space: nowrap;
      text-shadow: {sh}px {sh}px 0 {navy}, 0 6px 18px rgba(0,0,0,.25); }}
    #{tid}-box .w {{ display: inline-block; }}
    #{tid}-box .spk {{ display: inline-block; width: {int(size * 0.2)}px; height: {int(size * 0.2)}px;
      vertical-align: {int(size * 0.18)}px; margin-left: 6px; }}
    #{tid}-box .scr {{ font-family: "CaveatR", cursive; font-weight: 700; color: #fff; line-height: 1;
      transform: rotate(-4deg); text-shadow: 0 2px 10px rgba(0,0,0,.45); white-space: nowrap;
      margin: {'0 0 -8px' if pos == 'above' else '-4px 0 0'}; }}
"""
    markup = f'<div id="{tid}-box" data-layout-allow-overflow>{inner}</div>'
    js = []
    for i, (_, t) in enumerate(words):
        js.append(f'tl.fromTo("#{tid}-w{i}", {{ opacity: 0, y: 30, scale: 1.25 }}, '
                  f'{{ opacity: 1, y: 0, scale: 1, duration: 0.2, ease: "back.out(2)" }}, {max(s, t - 0.06):.3f});')
    last = max(s, words[-1][1])
    js.append(f'tl.fromTo("#{tid}-box .spk", {{ opacity: 0, scale: 0, rotation: -90 }}, '
              f'{{ opacity: 1, scale: 1, rotation: 0, duration: 0.3, ease: "back.out(3)" }}, {last + 0.12:.3f});')
    js.append(f'tl.to("#{tid}-box .spk", {{ rotation: 90, duration: {max(0.5, e - last - 0.6):.3f}, ease: "none" }}, {last + 0.42:.3f});')
    if script:
        at = sp.get("script_at", s + 0.3)
        js.append(f'tl.fromTo("#{tid}-s", {{ opacity: 0, clipPath: "inset(-30% 100% -30% 0%)" }}, '
                  f'{{ opacity: 1, clipPath: "inset(-30% 0% -30% 0%)", duration: 0.45, ease: "power1.out" }}, {at:.3f});')
    js.append(f'tl.to("#{tid}-box", {{ opacity: 0, y: -14, duration: 0.18, ease: "power2.in" }}, {max(s + 0.5, e - 0.2):.3f});')
    return css, markup, js


def etiquetas(sp, W, H, navy):
    tid, s, e = sp["id"], sp["start"], sp["end"]
    items = sp["items"]
    size = sp.get("size", 66)
    top = int(H * sp.get("y", 14) / 100)
    gap = int(size * sp.get("gap", 1.85))
    rows, css_rows = [], []
    for i, (txt, _) in enumerate(items):
        left = i % 2 == 0
        rot = -3.2 if left else -1.6
        side = f"left: {int(W * 0.06)}px;" if left else f"right: {int(W * 0.06)}px;"
        css_rows.append(f"    #{tid}-i{i} {{ {side} top: {i * gap}px; transform: rotate({rot}deg); "
                        f"transform-origin: {'0% 50%' if left else '100% 50%'}; }}")
        rows.append(f'<div class="tag" id="{tid}-i{i}">{html.escape(txt)}</div>')
    css = f"""
    #{tid}-box {{ position: absolute; left: 0; top: {top}px; width: {W}px; height: {gap * len(items) + size}px; }}
    #{tid}-box .tag {{ position: absolute; background: #fff; color: {navy}; font-family: "MontserratR", sans-serif;
      font-weight: 900; font-size: {size}px; line-height: 1; padding: {int(size * .26)}px {int(size * .5)}px {int(size * .22)}px;
      border-radius: {int(size * .3)}px; white-space: nowrap; box-shadow: 0 8px 24px rgba(0,0,0,.28); }}
{chr(10).join(css_rows)}
"""
    markup = f'<div id="{tid}-box" data-layout-allow-overflow data-layout-allow-overlap>{"".join(rows)}</div>'
    js = []
    for i, (_, t) in enumerate(items):
        dx = -60 if i % 2 == 0 else 60
        js.append(f'tl.fromTo("#{tid}-i{i}", {{ opacity: 0, x: {dx}, scale: 0.7 }}, '
                  f'{{ opacity: 1, x: 0, scale: 1, duration: 0.28, ease: "back.out(1.8)" }}, {max(s, t - 0.08):.3f});')
    js.append(f'tl.to("#{tid}-box", {{ opacity: 0, y: -14, duration: 0.18, ease: "power2.in" }}, {max(s + 0.5, e - 0.2):.3f});')
    return css, markup, js


def cta(sp, W, H, navy):
    tid, s, e = sp["id"], sp["start"], sp["end"]
    size = sp.get("size", 58)
    top = int(H * sp.get("y", 58) / 100)
    icon = (f'<svg class="ic" viewBox="0 0 24 24"><rect x="3" y="4.5" width="18" height="16" rx="3" fill="none" '
            f'stroke="#fff" stroke-width="2"/><line x1="3" y1="9.5" x2="21" y2="9.5" stroke="#fff" stroke-width="2"/>'
            f'<line x1="8" y1="2.5" x2="8" y2="6.5" stroke="#fff" stroke-width="2" stroke-linecap="round"/>'
            f'<line x1="16" y1="2.5" x2="16" y2="6.5" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>')
    css = f"""
    #{tid}-box {{ position: absolute; left: 0; top: {top}px; width: {W}px; display: flex; justify-content: center; }}
    #{tid}-btn {{ display: flex; align-items: center; gap: {int(size * .4)}px; background: {navy}; color: #fff;
      font-family: "MontserratR", sans-serif; font-weight: 800; font-size: {size}px; line-height: 1;
      padding: {int(size * .4)}px {int(size * .55)}px; border-radius: {int(size * .25)}px; white-space: nowrap;
      box-shadow: 0 10px 30px rgba(0,0,0,.3); }}
    #{tid}-btn .ic {{ width: {int(size * .8)}px; height: {int(size * .8)}px; flex: none; }}
"""
    markup = (f'<div id="{tid}-box" data-layout-allow-overflow><div id="{tid}-btn">{icon}'
              f'<span>{html.escape(sp["text"])}</span></div></div>')
    js = [f'tl.fromTo("#{tid}-btn", {{ opacity: 0, y: 40, scale: 0.85 }}, '
          f'{{ opacity: 1, y: 0, scale: 1, duration: 0.32, ease: "back.out(1.8)" }}, {s + 0.02:.3f});',
          f'tl.to("#{tid}-btn", {{ scale: 1.04, duration: 0.45, ease: "sine.inOut", yoyo: true, '
          f'repeat: {max(1, int((e - s - 0.8) / 0.45))} }}, {s + 0.5:.3f});']
    return css, markup, js


MAKERS = {"titulo": titulo, "etiquetas": etiquetas, "cta": cta}


def apply_zoom(hf: Path, edl_path: Path, scale: float, origin_y: float) -> None:
    """Punch-in alternado nos pontos de corte (segmentos pares 1.0, ímpares `scale`)."""
    edl = json.loads(edl_path.read_text())
    bounds, t = [], 0.0
    for r in edl["ranges"]:
        bounds.append(round(t, 3))
        t += r["end"] - r["start"]
    idx = hf / "index.html"
    page = idx.read_text()
    page = re.sub(r"\n\s*// zoom-cuts:start.*?// zoom-cuts:end", "", page, flags=re.S)
    sets = "\n".join(f'      tlMain.set("#base", {{ scale: {scale if i % 2 else 1} }}, {b});'
                     for i, b in enumerate(bounds))
    block = (f'\n      // zoom-cuts:start (tools/make_estilo_rga.py --zoom-cuts)\n'
             f'      gsap.set("#base", {{ transformOrigin: "50% {origin_y}%" }});\n{sets}\n      // zoom-cuts:end')
    page = page.replace('window.__timelines["main"] = gsap.timeline({ paused: true });',
                        'const tlMain = gsap.timeline({ paused: true });\n      window.__timelines["main"] = tlMain;')
    page = page.replace('window.__timelines["main"] = tlMain;', 'window.__timelines["main"] = tlMain;' + block, 1)
    idx.write_text(page)
    print(f"zoom nos cortes: {', '.join(f'{b:.2f}' for b in bounds)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hf_dir", type=Path)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--navy", default=NAVY)
    ap.add_argument("--zoom-cuts", type=Path, help="edl.json: punch-in alternado nos cortes")
    ap.add_argument("--zoom", type=float, default=1.15)
    ap.add_argument("--zoom-origin-y", type=float, default=36.0, help="centro do zoom (%% da altura; rosto/peito)")
    args = ap.parse_args()

    hf = args.hf_dir.resolve()
    page = (hf / "index.html").read_text()
    W, H = (int(x) for x in re.search(r'data-width="(\d+)" data-height="(\d+)"', page).groups())
    for sp in json.loads(args.spec.read_text()):
        tid, s0 = sp["id"], sp["start"]
        css, markup, js = MAKERS[sp["type"]](sp, W, H, args.navy)
        js = [re.sub(r"\}, (\d+\.\d+)\);$", lambda m: f"}}, {float(m.group(1)) - s0:.3f});", j) for j in js]
        dur = round(sp["end"] - s0, 3)
        comp = f"""<!-- Gerado por tools/make_estilo_rga.py ({sp['type']}) -->
<template>
  <style>
{FONTS}
    #root {{ position: absolute; inset: 0; background: transparent; }}
{css}
  </style>
  <div id="root" data-composition-id="{tid}" data-width="{W}" data-height="{H}" data-layout-allow-overflow>
    <div id="{tid}-clip" class="clip" data-start="0" data-duration="{dur}" data-track-index="0">{markup}</div>
  </div>
  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});
      {(chr(10) + '      ').join(js)}
      window.__timelines["{tid}"] = tl;
    }})();
  </script>
</template>
"""
        subprocess.run([sys.executable, str(ROOT / "tools" / "add_overlay.py"), str(hf), "--remove", tid],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (hf / "compositions" / f"{tid}.html").write_text(comp)
        subprocess.run([sys.executable, str(ROOT / "tools" / "add_overlay.py"), str(hf), "x", tid,
                        str(s0), str(dur), "--custom"], check=True)
    if args.zoom_cuts:
        apply_zoom(hf, args.zoom_cuts, args.zoom, args.zoom_origin_y)


if __name__ == "__main__":
    main()
