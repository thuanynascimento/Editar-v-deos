"""Gera a composição de legendas (HyperFrames) a partir de assets/words.json.

Estilo padrão (ajustável por argumentos):
  * Montserrat, branca, SEM contorno (só uma sombra suave e difusa para leitura)
  * centralizada na horizontal; na vertical um pouco abaixo do centro (--y, em % da altura)
  * grupos de até 4 palavras / ~20 caracteres, quebrando em pontuação e pausas
  * palavras de ÊNFASE (--emphasis) em cor de destaque, mais pesadas, com um "pulo" ao serem ditas

Uso:
    python tools/make_captions.py videos/proj/edit/hyperframes \\
        --emphasis "apartamento,praia,renda,Black Servopa,patrimônio" --accent "#5CE1E6" --y 58

Escreve compositions/legendas.html e monta (ou remonta) o host no index.html.
Ênfase: lista separada por vírgula; cada item pode ter várias palavras ("Black Servopa").
Para forçar uma quebra de grupo antes de uma palavra, use --break "palavra,outra".
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return re.sub(r"[^\w%]", "", "".join(c for c in t if not unicodedata.combining(c)))


def group_words(words, max_words, max_chars, pause, breaks):
    """breaks: lista de sequências de tokens; quebra o grupo ANTES de cada ocorrência."""
    toks = [norm(w["text"]) for w in words]
    break_at = {i for seq in breaks for i in range(len(toks)) if toks[i:i + len(seq)] == seq}
    groups, cur = [], []
    for i, w in enumerate(words):
        if cur and i in break_at:
            groups.append(cur)
            cur = []
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        chars = len(" ".join(x["text"] for x in cur))
        nxt_chars = chars + 1 + len(nxt["text"]) if nxt else 0
        if (nxt is None or w["text"][-1] in ".?!,;:" or nxt["start"] - w["end"] >= pause or nxt.get("_cut_before")
                or len(cur) >= max_words or nxt_chars > max_chars):
            groups.append(cur)
            cur = []
    # evita grupo de uma palavra só curtinha pendurada: junta ao anterior se couber
    merged = []
    for g in groups:
        if merged and len(g) == 1 and len(g[0]["text"]) <= 3 and merged[-1][-1]["text"][-1] not in ".?!":
            if len(" ".join(x["text"] for x in merged[-1] + g)) <= max_chars + 4:
                merged[-1] = merged[-1] + g
                continue
        merged.append(g)
    return merged


def mark_emphasis(words, phrases):
    seqs = [[norm(t) for t in p.split()] for p in phrases if p.strip()]
    toks = [norm(w["text"]) for w in words]
    emph = [False] * len(words)
    for seq in seqs:
        n = len(seq)
        for i in range(len(toks) - n + 1):
            if toks[i:i + n] == seq:
                for j in range(i, i + n):
                    emph[j] = True
    return emph


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hf_dir", type=Path)
    ap.add_argument("--emphasis", default="", help="palavras/expressões de ênfase, separadas por vírgula")
    ap.add_argument("--break", dest="breaks", default="", help="força quebra de grupo antes destas palavras/expressões (ex.: \"do que,uma renda\")")
    ap.add_argument("--accent", default="#FFD43B", help="cor das palavras de ênfase")
    ap.add_argument("--color", default="#FFFFFF", help="cor do texto")
    ap.add_argument("--font", default="Montserrat")
    ap.add_argument("--weight", type=int, default=700)
    ap.add_argument("--emph-weight", type=int, default=900)
    ap.add_argument("--size", type=int, default=0, help="px (0 = automático: 6.8%% da largura)")
    ap.add_argument("--width", type=float, default=72.0,
                    help="largura máxima da legenda em %% da tela (72 deixa livre a coluna de botões do Reels/TikTok)")
    ap.add_argument("--y", type=float, default=58.0, help="centro vertical da legenda, %% da altura (50 = meio)")
    ap.add_argument("--max-words", type=int, default=4)
    ap.add_argument("--max-chars", type=int, default=20)
    ap.add_argument("--pause", type=float, default=0.18, help="pausa que quebra o grupo (s)")
    ap.add_argument("--uppercase", action="store_true")
    ap.add_argument("--no-shadow", action="store_true", help="tira até a sombra suave")
    ap.add_argument("--exclude", default="",
                    help="faixas 'ini-fim,ini-fim' (timeline do corte) cujas palavras NÃO viram legenda "
                         "(ex.: já aparecem num título grande)")
    ap.add_argument("--emph-box", default="",
                    help="cor de uma CAIXA atrás da palavra de ênfase (texto fica em --accent). "
                         "Ex.: --emph-box \"#093B6E\" --accent \"#FFFFFF\" (estilo da referência jiu-jitsu)")
    ap.add_argument("--lead", type=float, default=0.08, help="legenda aparece X s antes da 1ª palavra")
    args = ap.parse_args()

    hf = args.hf_dir.resolve()
    index = hf / "index.html"
    page = index.read_text()
    W, H = (int(x) for x in re.search(r'data-width="(\d+)" data-height="(\d+)"', page).groups())
    root_dur = float(re.search(r'data-composition-id="main" data-start="0" data-duration="([\d.]+)"', page).group(1))
    words = [w for w in json.loads((hf / "assets" / "words.json").read_text()) if w["text"].strip()]
    excl = [tuple(float(v) for v in r.split("-")) for r in args.exclude.split(",") if r.strip()]
    if excl:
        words = [w for w in words if not any(a <= w["start"] < b for a, b in excl)]
        # uma faixa excluída quebra o grupo: marca pausa artificial
        for i in range(1, len(words)):
            if any(words[i - 1]["start"] < a <= words[i]["start"] for a, _ in excl):
                words[i]["_cut_before"] = True

    emph = mark_emphasis(words, args.emphasis.split(","))
    for w, e in zip(words, emph):
        w["emph"] = e
    breaks = [[norm(t) for t in b.split()] for b in args.breaks.split(",") if b.strip()]
    groups = group_words(words, args.max_words, args.max_chars, args.pause, breaks)

    size = args.size or round(W * 0.068)
    max_w = round(W * args.width / 100)
    # janelas: abre um pouco antes da 1ª palavra; fecha quando o próximo grupo abre (sem buraco
    # piscando em pausas curtas) ou 0.35 s após a última palavra
    spans = []
    for gi, g in enumerate(groups):
        start = max(0.12 if gi == 0 else 0.0, g[0]["start"] - args.lead)
        spans.append([start, g[-1]["end"]])
    for gi in range(len(spans)):
        nxt = spans[gi + 1][0] if gi + 1 < len(spans) else root_dur
        end = spans[gi][1] + 0.35
        if nxt - spans[gi][1] < 0.6:
            end = nxt
        for a, _b in excl:  # não invade uma faixa excluída (título/encerramento no mesmo lugar)
            if groups[gi][-1]["end"] - 0.01 <= a < end:
                end = a
        spans[gi][1] = round(min(end, nxt, root_dur), 3)
        spans[gi][0] = round(spans[gi][0], 3)

    shadow = "none" if args.no_shadow else "0 3px 22px rgba(0,0,0,.38), 0 1px 3px rgba(0,0,0,.25)"
    tt = "uppercase" if args.uppercase else "none"
    cap_h = round(size * 2.6)
    top = round(H * args.y / 100 - cap_h / 2)

    groups_html, js = [], []
    for gi, (g, (s, e)) in enumerate(zip(groups, spans)):
        gid = f"cap-{gi}"
        spans_html = []
        js.append(f'tl.fromTo("#{gid}-in", {{ opacity: 0, y: 18 }}, {{ opacity: 1, y: 0, duration: 0.16, ease: "power2.out" }}, {s:.3f});')
        for wi, w in enumerate(g):
            cls = "w e" if w["emph"] else "w"
            spans_html.append(f'<span id="{gid}-w{wi}" class="{cls}">{html.escape(w["text"])}</span>')
            if w["emph"]:
                t = max(s, w["start"])
                js.append(f'tl.fromTo("#{gid}-w{wi}", {{ y: 0, scale: 1 }}, {{ y: -10, scale: 1.04, duration: 0.14, ease: "power2.out", '
                          f'yoyo: true, repeat: 1 }}, {t:.3f});')
        js.append(f'tl.to("#{gid}-in", {{ opacity: 0, duration: 0.1, ease: "power2.in" }}, {max(s, e - 0.1):.3f});')
        groups_html.append(
            f'    <div id="{gid}" class="clip grp" data-start="{s}" data-duration="{round(e - s, 3)}" data-track-index="0">'
            f'<div id="{gid}-in" class="in">{" ".join(spans_html)}</div></div>')

    # fonte local (assets/fonts/montserrat-<peso>-normal.woff2) garante o peso exato no render
    font_faces = ""
    if args.font.lower() == "montserrat":
        for wgt in sorted({args.weight, args.emph_weight}):
            if (hf / "assets" / "fonts" / f"montserrat-{wgt}-normal.woff2").exists():
                font_faces += (f'    @font-face {{ font-family: "Montserrat"; font-weight: {wgt}; '
                               f'src: url("assets/fonts/montserrat-{wgt}-normal.woff2") format("woff2"); }}\n')
    box_css = ""
    if args.emph_box:
        box_css = (f"    .e {{{{ background: {args.emph_box}; padding: 0.04em 0.26em 0.1em; border-radius: 0.16em; "
                   f"text-shadow: none; box-shadow: 0 4px 14px rgba(0,0,0,.25); margin: 0 0.12em; }}}}")
        box_css = box_css.replace("{{", "{").replace("}}", "}")
    comp = f"""<!-- Legendas geradas por tools/make_captions.py — edite o texto direto aqui ou rode o script de novo. -->
<template>
  <style>
{font_faces}
    #root {{ position: absolute; inset: 0; background: transparent; }}
    .grp {{ position: absolute; left: 0; top: {top}px; width: {W}px; height: {cap_h}px;
      display: flex; align-items: center; justify-content: center; overflow: visible; }}
    .in {{ max-width: {max_w}px; text-align: center; font-family: "{args.font}", sans-serif;
      font-size: {size}px; font-weight: {args.weight}; line-height: 1.12; color: {args.color};
      text-transform: {tt}; letter-spacing: -0.01em; text-shadow: {shadow}; opacity: 0; }}
    .w {{ display: inline-block; transform-origin: 50% 60%; }}
    .e {{ color: {args.accent}; font-weight: {args.emph_weight}; margin: 0 0.1em; }}
{box_css}
  </style>
  <div id="root" data-composition-id="legendas" data-width="{W}" data-height="{H}" data-layout-allow-caption-zone>
{chr(10).join(groups_html)}
  </div>
  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});
      {(chr(10) + '      ').join(js)}
      window.__timelines["legendas"] = tl;
    }})();
  </script>
</template>
"""
    (hf / "compositions" / "legendas.html").write_text(comp)

    # (re)monta o host
    subprocess.run([sys.executable, str(ROOT / "tools" / "add_overlay.py"), str(hf), "--remove", "legendas"],
                   check=True, stdout=subprocess.DEVNULL)
    (hf / "compositions" / "legendas.html").write_text(comp)  # --remove apaga o arquivo
    subprocess.run([sys.executable, str(ROOT / "tools" / "add_overlay.py"), str(hf), "legendas", "legendas",
                    "0", str(root_dur), "--custom", "--kind", "captions"], check=True)

    n_e = sum(w["emph"] for w in words)
    print(f"{len(groups)} grupos de legenda, {n_e} palavras em destaque, fonte {args.font} {size}px, "
          f"centro em {args.y:.0f}% da altura")
    for g, (s, e) in zip(groups, spans):
        txt = " ".join(("*" + w["text"] + "*") if w["emph"] else w["text"] for w in g)
        print(f"  {s:6.2f}-{e:6.2f}  {txt}")


if __name__ == "__main__":
    main()
