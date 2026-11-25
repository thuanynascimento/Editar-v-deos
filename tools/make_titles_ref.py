"""Títulos no estilo da referência "Reels jiu-jitsu" da cliente (HyperFrames).

Estilo (tirado de videos/referencia-reels/ref.mp4):
  * "condensado": palavras GRANDES em caixa alta, fonte condensada (Anton), brancas com sombra
    sólida azul-marinho deslocada; entram PALAVRA POR PALAVRA no momento em que são ditas,
    com um brilho (estrelinha) no fim. Manuscrito pequeno (Kaushan Script) acima ou abaixo.
  * "etiqueta": etiquetas brancas arredondadas, levemente inclinadas, texto azul-marinho
    Montserrat 900; a segunda entra deslocada para a direita (escada).
  * "cta": pílula azul-marinho com ícone de calendário e texto branco.
  * Saída de todos: desfoque + fade.

Spec JSON (lista; tempos na timeline do vídeo cortado; y = centro vertical em % da altura):
  [{"id": "t-40", "style": "condensado", "start": 0.6, "end": 4.0, "y": 11,
    "words": [["AOS", 0.8], ["+40", 1.3], ["ANOS.", 1.9]],
    "script": "será que dá tempo", "script_at": 2.6, "script_pos": "below"},
   {"id": "t-dep", "style": "etiqueta", "start": 5.0, "end": 9.0, "y": 9,
    "labels": [["DEPOIS DOS 40", 5.2], ["TREINAM MELHOR", 6.4]]},
   {"id": "t-cta", "style": "cta", "start": 15.0, "end": 17.8, "y": 80,
    "text": "Agende pelo link da bio", "at": 15.2}]

Uso:
    python tools/make_titles_ref.py <hf_dir> spec.json [--navy "#093B6E"]
Precisa em assets/fonts/: anton.woff2, kaushan.woff2, montserrat-900-normal.woff2,
montserrat-800-normal.woff2 (npm pack @fontsource/anton @fontsource/kaushan-script @fontsource/montserrat).
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
    @font-face { font-family: "AntonR"; src: url("assets/fonts/anton.woff2") format("woff2"); }
    @font-face { font-family: "KaushanR"; src: url("assets/fonts/kaushan.woff2") format("woff2"); }
    @font-face { font-family: "MontR"; font-weight: 900; src: url("assets/fonts/montserrat-900-normal.woff2") format("woff2"); }
    @font-face { font-family: "MontR"; font-weight: 800; src: url("assets/fonts/montserrat-800-normal.woff2") format("woff2"); }
"""

STAR = ('<svg viewBox="0 0 40 40" width="100%" height="100%"><path d="M20 0 C21.5 14 26 18.5 40 20 '
        'C26 21.5 21.5 26 20 40 C18.5 26 14 21.5 0 20 C14 18.5 18.5 14 20 0Z" fill="#fff"/></svg>')

CAL = ('<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="#fff" stroke-width="2.2" '
       'stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4.5" width="18" height="16.5" rx="2.5"/>'
       '<path d="M3 9.5h18M8 2.5v4M16 2.5v4"/></svg>')


def exit_tween(sel: str, t: float) -> str:
    return (f'tl.to({sel}, {{ opacity: 0, y: -14, filter: "blur(10px)", duration: 0.32, '
            f'ease: "power2.in" }}, {t:.3f});')


def condensado(sp, W, H, navy):
    tid, s, e = sp["id"], sp["start"], sp["end"]
    words = sp["words"]
    chars = sum(len(w) for w, _ in words) + len(words) - 1
    size = int(min(sp.get("size", 160), W * 0.84 / (chars * 0.47)))
    cy = H * sp.get("y", 12) / 100
    off = max(4, round(size * 0.045))
    css = f"""
    #{tid}-box {{ position: absolute; left: 0; width: {W}px; top: {int(cy - size * 0.62)}px;
      display: flex; justify-content: center; align-items: baseline; }}
    #{tid}-row {{ position: relative; white-space: nowrap; }}
    .{tid}-w {{ display: inline-block; font-family: "AntonR", sans-serif; font-size: {size}px; line-height: 1.1;
      color: #fff; letter-spacing: 0.01em; margin: 0 {round(size * 0.1)}px;
      text-shadow: {off}px {off + 1}px 0 {navy}, 0 8px 22px rgba(0,0,0,.28); opacity: 0; }}
    #{tid}-star {{ position: absolute; right: {-round(size * 0.22)}px; top: {round(size * 0.48)}px;
      width: {round(size * 0.2)}px; height: {round(size * 0.2)}px; opacity: 0;
      filter: drop-shadow(0 0 6px rgba(255,255,255,.9)); }}
    #{tid}-s {{ position: absolute; white-space: nowrap; font-family: "KaushanR", cursive;
      font-size: {int(sp.get('script_size', size * 0.36))}px; color: {sp.get("script_color", "#fff")}; transform: rotate(-6deg);
      text-shadow: {"0 0 14px rgba(255,255,255,.85)" if sp.get("script_color", "#fff").lower() not in ("#fff", "#ffffff") else "0 3px 12px rgba(0,0,0,.45)"}; clip-path: inset(-20% 100% -20% 0); line-height: 1.2; }}
    """
    if sp.get("script_pos", "below") == "above":
        css += f"#{tid}-s {{ left: {round(size * 0.2)}px; bottom: {round(size * 0.98)}px; }}"
    else:
        css += f"#{tid}-s {{ left: 50%; margin-left: -{round(size * 1.0)}px; top: {round(size * 1.05)}px; }}"
    spans = "".join(f'<span id="{tid}-w{i}" class="{tid}-w">{html.escape(w)}</span>' for i, (w, _) in enumerate(words))
    script = sp.get("script", "")
    markup = (f'<div id="{tid}-box"><div id="{tid}-row">{spans}<div id="{tid}-star">{STAR}</div>'
              + (f'<div id="{tid}-s">{html.escape(script)}</div>' if script else "") + "</div></div>")
    js = []
    for i, (_, at) in enumerate(words):
        js.append(f'tl.fromTo("#{tid}-w{i}", {{ opacity: 0, y: 40, scale: 0.86, filter: "blur(8px)" }}, '
                  f'{{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)", duration: 0.28, ease: "power3.out" }}, {max(s, at - 0.06):.3f});')
    last = max(s, words[-1][1]) + 0.2
    js.append(f'tl.fromTo("#{tid}-star", {{ opacity: 0, scale: 0, rotation: -90 }}, '
              f'{{ opacity: 1, scale: 1, rotation: 0, duration: 0.35, ease: "back.out(2.4)" }}, {last:.3f});')
    js.append(f'tl.to("#{tid}-star", {{ scale: 0.7, rotation: 45, duration: 0.6, ease: "sine.inOut", yoyo: true, repeat: 3 }}, {last + 0.35:.3f});')
    if script:
        js.append(f'tl.fromTo("#{tid}-s", {{ clipPath: "inset(-20% 100% -20% 0)" }}, '
                  f'{{ clipPath: "inset(-20% 0% -20% 0)", duration: 0.6, ease: "power1.inOut" }}, {sp.get("script_at", last):.3f});')
    js.append(exit_tween(f'"#{tid}-box"', e - 0.34))
    return css, markup, js


def etiqueta(sp, W, H, navy):
    tid, s, e = sp["id"], sp["start"], sp["end"]
    labels = sp["labels"]
    size = sp.get("size", 58)
    top = int(H * sp.get("y", 10) / 100)
    css = f"""
    #{tid}-box {{ position: absolute; left: {sp.get('x', 70)}px; top: {top}px; display: flex; flex-direction: column; align-items: flex-start; }}
    .{tid}-l {{ background: #fff; color: {navy}; font-family: "MontR", sans-serif; font-weight: 900;
      font-size: {size}px; line-height: 1; padding: {round(size * .34)}px {round(size * .6)}px {round(size * .3)}px;
      border-radius: {round(size * .26)}px; box-shadow: 0 10px 30px rgba(0,0,0,.22); white-space: nowrap; opacity: 0; }}
    """
    rots = sp.get("rotations", [-4, -2.5, -4])
    step = sp.get("step", 150)
    parts = []
    for i, (txt, _) in enumerate(labels):
        css += f"#{tid}-l{i} {{ margin-left: {i * step}px; margin-top: {0 if i == 0 else -round(size * .12)}px; transform: rotate({rots[i % len(rots)]}deg); }}\n"
        parts.append(f'<div id="{tid}-l{i}" class="{tid}-l">{html.escape(txt)}</div>')
    markup = f'<div id="{tid}-box">{"".join(parts)}</div>'
    js = []
    for i, (_, at) in enumerate(labels):
        r = rots[i % len(rots)]
        js.append(f'tl.fromTo("#{tid}-l{i}", {{ opacity: 0, scale: 0.6, rotation: {r - 8} }}, '
                  f'{{ opacity: 1, scale: 1, rotation: {r}, duration: 0.38, ease: "back.out(2)" }}, {max(s, at - 0.08):.3f});')
    js.append(exit_tween(f'"#{tid}-box"', e - 0.34))
    return css, markup, js


def cta(sp, W, H, navy):
    tid, s, e = sp["id"], sp["start"], sp["end"]
    size = sp.get("size", 46)
    cy = H * sp.get("y", 80) / 100
    css = f"""
    #{tid}-box {{ position: absolute; left: 0; width: {W}px; top: {int(cy - size)}px; display: flex; justify-content: center; }}
    #{tid}-p {{ display: flex; align-items: center; gap: {round(size * .4)}px; background: {navy}; color: #fff;
      font-family: "MontR", sans-serif; font-weight: 800; font-size: {size}px; line-height: 1;
      padding: {round(size * .42)}px {round(size * .6)}px; border-radius: {round(size * .3)}px;
      box-shadow: 0 12px 30px rgba(0,0,0,.3); opacity: 0; white-space: nowrap; }}
    """
    markup = f'<div id="{tid}-box"><div id="{tid}-p">{CAL}<span>{html.escape(sp["text"])}</span></div></div>'
    at = sp.get("at", s)
    js = [f'tl.fromTo("#{tid}-p", {{ opacity: 0, y: 30, scale: 0.8 }}, {{ opacity: 1, y: 0, scale: 1, duration: 0.4, ease: "back.out(1.8)" }}, {at:.3f});',
          f'tl.to("#{tid}-p", {{ scale: 1.05, duration: 0.25, ease: "power1.inOut", yoyo: true, repeat: 1 }}, {at + 0.6:.3f});']
    if sp.get("exit", True):
        js.append(exit_tween(f'"#{tid}-box"', e - 0.34))
    return css, markup, js


MAKERS = {"condensado": condensado, "etiqueta": etiqueta, "cta": cta}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hf_dir", type=Path)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--navy", default="#093B6E", help="azul da referência")
    ap.add_argument("--script-color", default="",
                    help="cor do manuscrito (padrão branco; em fundo claro use o azul, ex. \"#093B6E\")")
    args = ap.parse_args()

    hf = args.hf_dir.resolve()
    page = (hf / "index.html").read_text()
    W, H = (int(x) for x in re.search(r'data-width="(\d+)" data-height="(\d+)"', page).groups())
    for sp in json.loads(args.spec.read_text()):
        tid, s0 = sp["id"], sp["start"]
        if args.script_color and "script_color" not in sp:
            sp["script_color"] = args.script_color
        css, markup, js = MAKERS[sp.get("style", "condensado")](sp, W, H, args.navy)
        js = [re.sub(r"\}, (\d+\.\d+)\);$", lambda m: f"}}, {float(m.group(1)) - s0:.3f});", j) for j in js]
        dur = round(sp["end"] - s0, 3)
        comp = f"""<!-- Título gerado por tools/make_titles_ref.py ({sp.get('style', 'condensado')}) -->
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
