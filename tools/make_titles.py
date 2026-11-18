"""Títulos de palavra-chave estilo "Reels de autoridade" (HyperFrames).

Estilo (tirado da referência da cliente, reels-01):
  * PALAVRA GRANDE em caixa alta, Montserrat 900, cor de destaque com brilho neon,
    letras caindo uma a uma com desfoque; saem desfocando.
  * Complemento em fonte manuscrita (Yellowtail), branco, abaixo e à direita, "escrito" da
    esquerda para a direita (wipe), levemente inclinado.
  * Ficam no terço superior; quando há recorte da pessoa (--atras), o título fica ATRÁS dela.
  * Estilo "fim": linha branca palavra a palavra + PALAVRA FINAL em itálico pesado.

Spec JSON (lista):
  [{"id": "t-praia", "start": 0.5, "end": 3.3, "big": "APARTAMENTO", "script": "na praia",
    "script_at": 1.07, "y": 17},
   {"id": "t-fim", "style": "fim", "start": 16.0, "end": 18.25, "y": 58,
    "line": [["qual", 16.02], ["imóvel", 16.18], ["você", 16.61], ["gostaria", 16.89], ["de", 17.23]],
    "big": "CONQUISTAR?", "big_at": 17.41}]
  y = centro vertical em % da altura. Tempos na timeline do vídeo cortado.

Uso:
    python tools/make_titles.py <hf_dir> spec.json --accent "#5CE1E6"
Precisa de assets/fonts/montserrat-900-normal.woff2, montserrat-900-italic.woff2,
montserrat-800-normal.woff2 e yellowtail.woff2 no projeto.
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
    @font-face { font-family: "MontserratT"; font-weight: 900; font-style: normal; src: url("assets/fonts/montserrat-900-normal.woff2") format("woff2"); }
    @font-face { font-family: "MontserratT"; font-weight: 900; font-style: italic; src: url("assets/fonts/montserrat-900-italic.woff2") format("woff2"); }
    @font-face { font-family: "MontserratT"; font-weight: 800; font-style: normal; src: url("assets/fonts/montserrat-800-normal.woff2") format("woff2"); }
    @font-face { font-family: "Yellowtail"; font-weight: 400; src: url("assets/fonts/yellowtail.woff2") format("woff2"); }
"""


def rgba(hex_color: str, a: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{a})"


def fit_size(text: str, max_w: int, base: int, per_char: float = 0.80) -> int:
    """Montserrat 900 caixa alta: ~0.80 em por caractere."""
    return int(min(base, max_w / (len(text) * per_char)))


def neon(spec: dict, W: int, H: int, accent: str, glow: float, part: str = "all"):
    """part: "big" = só a palavra grande (camada ATRÁS da pessoa); "script" = só o manuscrito
    (camada NA FRENTE, para não sumir atrás da cabeça); "all" = os dois juntos."""
    tid, s, e = spec["id"], spec["start"], spec["end"]
    big = spec["big"]
    size = fit_size(big, int(W * 0.86), spec.get("size", 190))
    cy = H * spec.get("y", 17) / 100
    box_h = int(size * 2.2)
    top = int(cy - size * 0.75)
    letters = "".join(
        f'<span class="L" id="{tid}-l{i}">{html.escape(ch) if ch != " " else "&nbsp;"}</span>'
        for i, ch in enumerate(big))
    script = spec.get("script", "")
    s_size = int(spec.get("script_size", max(70, size * 0.62)))
    script_html = (f'<div id="{tid}-s" class="S" style="font-size:{s_size}px">{html.escape(script)}</div>'
                   if script else "")
    # manuscrito "below" (padrão, sobre fotos) ou "above" (sobre a pessoa: fica entre o topo da
    # tela e a cabeça, nunca no rosto), à esquerda do centro para começar a leitura
    if spec.get("script_pos", "below") == "above":
        s_pos = f"left: {int(W * 0.14)}px; top: {-int(s_size * 1.02)}px;"
    else:
        s_pos = f"right: {int(W * 0.08)}px; top: {int(size * 0.80)}px;"
    shadow = (f"0 0 {int(10 * glow)}px {rgba(accent, .95)}, 0 0 {int(26 * glow)}px {rgba(accent, .7)}, "
              f"0 0 {int(60 * glow)}px {rgba(accent, .45)}, 0 4px 14px rgba(0,0,0,.35)")
    css = f"""
    #{tid}-box {{ position: absolute; left: 0; top: {top}px; width: {W}px; height: {box_h}px; overflow: visible; }}
    #{tid}-big {{ position: absolute; left: 0; top: 0; width: {W}px; text-align: center; white-space: nowrap;
      font-family: "MontserratT", "Montserrat", sans-serif; font-weight: 900; font-size: {size}px;
      line-height: 1; letter-spacing: -0.01em; color: {accent}; text-shadow: {shadow}; }}
    #{tid}-big .L {{ display: inline-block; }}
    #{tid}-s {{ position: absolute; {s_pos} }}
"""
    big_html = f'<div id="{tid}-big">{letters}</div>' if part != "script" else ""
    if part == "big":
        script_html = ""
    markup = (f'<div id="{tid}-box" data-layout-allow-overflow data-layout-allow-overlap>'
              f'{big_html}{script_html}</div>')
    n = len(big)
    js = [] if part == "script" else [
        f'tl.fromTo("#{tid}-big .L", {{ opacity: 0, y: -60, scale: 1.35, filter: "blur(14px)" }}, '
        f'{{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)", duration: 0.26, ease: "power3.out", '
        f'stagger: {min(0.045, 0.5 / max(n, 1)):.3f} }}, {spec.get("big_at", s):.3f});',
    ]
    if script and part != "big":
        at = spec.get("script_at", s + 0.35)
        js.append(f'tl.fromTo("#{tid}-s", {{ opacity: 0, clipPath: "inset(-20% 100% -20% 0%)", x: -16 }}, '
                  f'{{ opacity: 1, clipPath: "inset(-20% 0% -20% 0%)", x: 0, duration: 0.35, ease: "power2.out" }}, {at:.3f});')
    # brilho "respira" levemente enquanto está na tela
    if part != "script":
      b0 = spec.get("big_at", s)
      js.append(f'tl.fromTo("#{tid}-big", {{ scale: 1 }}, {{ scale: 1.035, duration: {max(0.4, e - b0 - 0.9):.3f}, '
              f'ease: "sine.inOut" }}, {b0 + 0.5:.3f});')
    out_at = max(s + 0.6, e - 0.32)
    js.append(f'tl.to("#{tid}-box", {{ opacity: 0, y: -24, filter: "blur(12px)", duration: 0.28, ease: "power2.in" }}, {out_at:.3f});')
    return css, markup, js


def fim(spec: dict, W: int, H: int, accent: str, glow: float):
    tid, s, e = spec["id"], spec["start"], spec["end"]
    cy = H * spec.get("y", 58) / 100
    words = spec.get("line", [])
    line_size = spec.get("line_size", 64)
    big = spec["big"]
    big_size = fit_size(big, int(W * 0.80), spec.get("size", 150), 0.78)
    top = int(cy - (line_size + big_size) / 2)
    wl = " ".join(f'<span class="w" id="{tid}-w{i}">{html.escape(t)}</span>' for i, (t, _) in enumerate(words))
    shadow = f"0 0 {int(12 * glow)}px {rgba(accent, .8)}, 0 0 {int(34 * glow)}px {rgba(accent, .45)}, 0 4px 14px rgba(0,0,0,.4)"
    css = f"""
    #{tid}-box {{ position: absolute; left: 0; top: {top}px; width: {W}px; text-align: center; overflow: visible; }}
    #{tid}-line {{ font-family: "MontserratT", "Montserrat", sans-serif; font-weight: 800; font-size: {line_size}px;
      color: #fff; line-height: 1.1; text-shadow: 0 3px 16px rgba(0,0,0,.45); }}
    #{tid}-line .w {{ display: inline-block; }}
    #{tid}-big {{ font-family: "MontserratT", "Montserrat", sans-serif; font-weight: 900; font-style: italic;
      font-size: {big_size}px; line-height: 1.02; color: {accent}; text-shadow: {shadow}; margin-top: 6px; white-space: nowrap; }}
"""
    markup = f'<div id="{tid}-box" data-layout-allow-overflow><div id="{tid}-line">{wl}</div><div id="{tid}-big">{html.escape(big)}</div></div>'
    js = []
    for i, (_, t) in enumerate(words):
        js.append(f'tl.fromTo("#{tid}-w{i}", {{ opacity: 0, y: 20 }}, {{ opacity: 1, y: 0, duration: 0.18, ease: "power2.out" }}, {max(s, t - 0.04):.3f});')
    bat = spec.get("big_at", s + 0.4)
    js.append(f'tl.fromTo("#{tid}-big", {{ opacity: 0, scale: 1.5, filter: "blur(16px)" }}, '
              f'{{ opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.3, ease: "power3.out" }}, {max(s, bat - 0.05):.3f});')
    return css, markup, js


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hf_dir", type=Path)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--accent", default="#5CE1E6")
    ap.add_argument("--glow", type=float, default=1.0, help="intensidade do brilho neon (1 = padrão)")
    args = ap.parse_args()

    hf = args.hf_dir.resolve()
    page = (hf / "index.html").read_text()
    W, H = (int(x) for x in re.search(r'data-width="(\d+)" data-height="(\d+)"', page).groups())
    specs = json.loads(args.spec.read_text())
    expanded = []
    for sp in specs:
        if sp.get("style") != "fim" and sp.get("script") and sp.get("split", True):
            expanded.append({**sp, "_part": "big"})
            expanded.append({**sp, "id": sp["id"] + "-esc", "_part": "script", "z": sp.get("z_script", 55)})
        else:
            expanded.append(sp)

    for sp in expanded:
        tid = sp["id"]
        maker = fim if sp.get("style") == "fim" else neon
        css, markup, js = (maker(sp, W, H, args.accent, args.glow, sp.get("_part", "all")) if maker is neon
                           else maker(sp, W, H, args.accent, args.glow))
        # tempos do spec são globais; a cena começa em sp["start"] → converte para local
        s0 = sp["start"]
        js = [re.sub(r"\}, (\d+\.\d+)\);$", lambda m: f"}}, {float(m.group(1)) - s0:.3f});", j) for j in js]
        dur = round(sp["end"] - s0, 3)
        comp = f"""<!-- Título gerado por tools/make_titles.py ({sp.get('style', 'neon')}) -->
<template>
  <style>
{FONTS}
    #root {{ position: absolute; inset: 0; background: transparent; }}
    .S {{ font-family: "Yellowtail", cursive; color: #fff; white-space: nowrap; transform: rotate(-5deg);
      text-shadow: 0 3px 14px rgba(0,0,0,.45); line-height: 1; }}
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
        (hf / "compositions" / f"{tid}.html").write_text(comp)
        subprocess.run([sys.executable, str(ROOT / "tools" / "add_overlay.py"), str(hf), "--remove", tid],
                       stdout=subprocess.DEVNULL)
        (hf / "compositions" / f"{tid}.html").write_text(comp)
        subprocess.run([sys.executable, str(ROOT / "tools" / "add_overlay.py"), str(hf), "x", tid,
                        str(s0), str(dur), "--custom"], check=True)
        # camada: "fim" fica NA FRENTE do recorte da pessoa (z 50); os neon ficam atrás dele
        z = sp.get("z", 60 if sp.get("style") == "fim" else None)
        if z is not None:
            idx = hf / "index.html"
            t = idx.read_text()
            t = re.sub(rf'(<div id="{re.escape(tid)}" [^>]*?style="z-index: )\d+', rf"\g<1>{z}", t, flags=re.S)
            idx.write_text(t)


if __name__ == "__main__":
    main()
