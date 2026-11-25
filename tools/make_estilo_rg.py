"""Gráficos no estilo da referência da cliente "Renzo Gracie" (reels-02) — HyperFrames.

Estilo (tirado de videos/reels-02/referencia/ref.mp4):
  * title — PALAVRA(S) em caixa alta, fonte condensada (Anton), branca com sombra azul-marinho
    dura deslocada; entra "focando" (desfoque + escala → nítido) e sai desfocando.
    Complemento manuscrito (Caveat), branco: "left" = pequeno à esquerda ("no TATAME"),
    "above" = acima do título, levemente inclinado ("bora experimentar?"), escrito com wipe.
  * tags — etiquetas brancas arredondadas, texto azul-marinho Montserrat 900, levemente
    giradas; aparecem com pulo; opcionalmente são riscadas (strike_at) e saem desfocando.
  * pin — pílula azul-marinho com ícone de localização e texto branco (endereço/unidade).

Spec JSON (lista; tempos GLOBAIS na timeline do vídeo cortado; x/y = centro em % da tela):
  [{"id": "t-tatame", "type": "title", "start": 2.1, "end": 5.3, "big": "TATAME",
    "script": "no", "script_pos": "left", "y": 19, "big_at": 2.2, "script_at": 2.1},
   {"id": "tg-obj", "type": "tags", "start": 0, "end": 2.6, "strike_at": 2.05,
    "tags": [{"text": "BOLETO", "at": 0.1, "x": 28, "y": 18, "rot": -3},
             {"text": "TRABALHO", "at": 1.5, "x": 68, "y": 25, "rot": 2}]},
   {"id": "pin-1", "type": "pin", "start": 4.5, "end": 7.2, "text": "Renzo Gracie · Kobrasol", "y": 70}]

Uso:
    python tools/make_estilo_rg.py <hf_dir> graficos.json [--blue "#013971"]
Fontes em <hf_dir>/assets/fonts: anton-400-normal.woff2, caveat-600-normal.woff2,
montserrat-700/900-normal.woff2 (npm pack @fontsource/anton @fontsource/caveat @fontsource/montserrat).
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

FONTS = """
    @font-face { font-family: "AntonT"; font-weight: 400; src: url("assets/fonts/anton-400-normal.woff2") format("woff2"); }
    @font-face { font-family: "CaveatT"; font-weight: 600; src: url("assets/fonts/caveat-600-normal.woff2") format("woff2"); }
    @font-face { font-family: "MontT"; font-weight: 700; src: url("assets/fonts/montserrat-700-normal.woff2") format("woff2"); }
    @font-face { font-family: "MontT"; font-weight: 900; src: url("assets/fonts/montserrat-900-normal.woff2") format("woff2"); }
"""

PIN_SVG = ('<svg viewBox="0 0 24 24" width="1em" height="1em" aria-hidden="true">'
           '<path fill="#fff" d="M12 2C7.6 2 4 5.5 4 9.9 4 15.6 12 22 12 22s8-6.4 8-12.1C20 5.5 16.4 2 12 2zm0 '
           '11a3.2 3.2 0 1 1 0-6.4 3.2 3.2 0 0 1 0 6.4z"/></svg>')


def T(t: float, s0: float) -> str:
    return f"{max(0.0, t - s0):.3f}"


def title(sp, W, H, blue):
    tid, s0, dur = sp["id"], sp["start"], sp["end"] - sp["start"]
    big = sp["big"]
    size = int(min(sp.get("size", 160), W * 0.88 / (len(big) * 0.47)))
    cy = H * sp.get("y", 19) / 100
    script = sp.get("script", "")
    pos = sp.get("script_pos", "above")
    s_size = int(sp.get("script_size", 64 if pos == "above" else max(54, size * 0.42)))
    if script and pos == "left":
        s_html = (f'<span id="{tid}-s" class="S" style="font-size:{s_size}px;margin-right:{int(s_size*0.15)}px;'
                  f'align-self:flex-end;margin-bottom:{int(size*0.12)}px">{html.escape(script)}</span>')
    elif script:
        s_html = (f'<span id="{tid}-s" class="S" style="font-size:{s_size}px;position:absolute;'
                  f'left:{int(sp.get("script_x", 12))}%;bottom:{int(size*1.02)}px;transform:rotate(-4deg)">'
                  f'{html.escape(script)}</span>')
    else:
        s_html = ""
    markup = (f'<div class="row" style="top:{int(cy - size*0.62)}px;height:{int(size*1.25)}px">'
              f'<div class="inner">{s_html if pos == "left" else ""}'
              f'<span id="{tid}-b" class="B" style="font-size:{size}px">{html.escape(big)}</span>'
              f'{s_html if pos != "left" else ""}</div></div>')
    big_at = sp.get("big_at", s0 + 0.05)
    js = [f'tl.fromTo("#{tid}-b", {{ opacity: 0, scale: 1.35, filter: "blur(22px)" }}, '
          f'{{ opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.42, ease: "power3.out" }}, {T(big_at, s0)});']
    if script:
        js.append(f'tl.fromTo("#{tid}-s", {{ opacity: 1, clipPath: "inset(-20% 100% -20% 0)" }}, '
                  f'{{ clipPath: "inset(-20% 0% -20% 0)", duration: {0.12 + 0.045*len(script):.2f}, ease: "none" }}, '
                  f'{T(sp.get("script_at", s0 + 0.05), s0)});')
    out = f"{max(0.0, dur - 0.32):.3f}"
    sel = f'["#{tid}-b"' + (f', "#{tid}-s"' if script else "") + "]"
    if not sp.get("hold"):
        js.append(f'tl.to({sel}, {{ opacity: 0, filter: "blur(16px)", scale: 1.06, duration: 0.3, ease: "power2.in" }}, {out});')
    css = f"""
    .row {{ position: absolute; left: 0; width: {W}px; display: flex; justify-content: center; align-items: center; }}
    .inner {{ position: relative; display: flex; align-items: center; }}
    .B {{ font-family: "AntonT", sans-serif; color: #fff; line-height: 1; white-space: nowrap; letter-spacing: 0.005em;
      text-shadow: 5px 6px 0 {blue}, 0 10px 28px rgba(0,0,0,.35); opacity: 0; display: inline-block; }}
    .S {{ font-family: "CaveatT", cursive; font-weight: 600; color: #fff; white-space: nowrap; line-height: 1;
      text-shadow: 0 3px 12px rgba(0,0,0,.5); clip-path: inset(-20% 100% -20% 0); }}"""
    return css, markup, js


def tags(sp, W, H, blue):
    tid, s0, dur = sp["id"], sp["start"], sp["end"] - sp["start"]
    parts, js = [], []
    for i, tg in enumerate(sp["tags"]):
        size = tg.get("size", 62)
        parts.append(
            f'<div class="tagw" style="left:{tg.get("x", 50)}%;top:{tg.get("y", 20)}%">'
            f'<div id="{tid}-t{i}" class="tag" style="font-size:{size}px;transform:rotate({tg.get("rot", -3)}deg)">'
            f'{html.escape(tg["text"])}<span id="{tid}-k{i}" class="strike"></span></div></div>')
        js.append(f'tl.fromTo("#{tid}-t{i}", {{ opacity: 0, scale: 0.5, filter: "blur(8px)" }}, '
                  f'{{ opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.34, ease: "back.out(2.2)" }}, {T(tg["at"], s0)});')
    if "strike_at" in sp:
        for i, _ in enumerate(sp["tags"]):
            js.append(f'tl.fromTo("#{tid}-k{i}", {{ scaleX: 0 }}, {{ scaleX: 1, duration: 0.22, ease: "power2.out" }}, '
                      f'{T(sp["strike_at"] + 0.12*i, s0)});')
    sel = "[" + ", ".join(f'"#{tid}-t{i}"' for i in range(len(sp["tags"]))) + "]"
    js.append(f'tl.to({sel}, {{ opacity: 0, filter: "blur(14px)", duration: 0.3, ease: "power2.in" }}, {max(0.0, dur - 0.32):.3f});')
    css = f"""
    .tagw {{ position: absolute; width: 0; height: 0; display: flex; align-items: center; justify-content: center; }}
    .tag {{ position: relative; flex: none; background: #fff; color: {blue}; font-family: "MontT", sans-serif; font-weight: 900;
      line-height: 1; padding: 0.32em 0.5em 0.3em; border-radius: 0.24em; white-space: nowrap; letter-spacing: -0.01em;
      box-shadow: 0 8px 26px rgba(0,0,0,.28); opacity: 0; }}
    .strike {{ position: absolute; left: 0.25em; right: 0.25em; top: 50%; height: 0.11em; margin-top: -0.055em;
      background: {blue}; border-radius: 0.06em; transform: scaleX(0); transform-origin: 0 50%; }}"""
    return css, "".join(parts), js


def pin(sp, W, H, blue):
    tid, s0, dur = sp["id"], sp["start"], sp["end"] - sp["start"]
    size = sp.get("size", 50)
    markup = (f'<div class="pinrow" style="top:{H*sp.get("y", 70)/100 - size}px;height:{size*2}px">'
              f'<div id="{tid}-p" class="pin" style="font-size:{size}px"><span id="{tid}-i" class="ico">{PIN_SVG}</span>'
              f'{html.escape(sp["text"])}</div></div>')
    js = [f'tl.fromTo("#{tid}-p", {{ opacity: 0, y: 40, scale: 0.9 }}, {{ opacity: 1, y: 0, scale: 1, duration: 0.42, ease: "back.out(1.7)" }}, '
          f'{T(sp.get("at", s0 + 0.05), s0)});',
          f'tl.fromTo("#{tid}-i", {{ y: -18 }}, {{ y: 0, duration: 0.45, ease: "bounce.out" }}, {T(sp.get("at", s0 + 0.05) + 0.2, s0)});']
    if not sp.get("hold"):
        js.append(f'tl.to("#{tid}-p", {{ opacity: 0, y: 24, duration: 0.28, ease: "power2.in" }}, {max(0.0, dur - 0.3):.3f});')
    css = f"""
    .pinrow {{ position: absolute; left: 0; width: {W}px; display: flex; align-items: center; justify-content: center; }}
    .pin {{ display: flex; align-items: center; gap: 0.35em; background: {blue}; color: #fff; font-family: "MontT", sans-serif;
      font-weight: 700; line-height: 1; padding: 0.42em 0.7em 0.42em 0.55em; border-radius: 0.3em; white-space: nowrap;
      box-shadow: 0 8px 26px rgba(0,0,0,.3); opacity: 0; }}
    .ico {{ display: inline-flex; font-size: 1.1em; }}"""
    return css, markup, js


MAKERS = {"title": title, "tags": tags, "pin": pin}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hf_dir", type=Path)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--blue", default="#013971", help="azul-marinho da marca (referência)")
    args = ap.parse_args()
    hf = args.hf_dir.resolve()
    page = (hf / "index.html").read_text()
    W, H = (int(x) for x in re.search(r'data-width="(\d+)" data-height="(\d+)"', page).groups())
    for sp in json.loads(args.spec.read_text()):
        tid, s0 = sp["id"], sp["start"]
        dur = round(sp["end"] - s0, 3)
        css, markup, js = MAKERS[sp.get("type", "title")](sp, W, H, args.blue)
        comp = f"""<!-- Gerado por tools/make_estilo_rg.py ({sp.get('type', 'title')}) -->
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
                       stdout=subprocess.DEVNULL)
        (hf / "compositions" / f"{tid}.html").write_text(comp)
        subprocess.run([sys.executable, str(ROOT / "tools" / "add_overlay.py"), str(hf), "x", tid,
                        str(s0), str(dur), "--custom"], check=True)


if __name__ == "__main__":
    main()
