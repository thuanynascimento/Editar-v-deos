"""Adiciona uma animação (cena HyperFrames) sobre o vídeo cortado.

Copia templates/hyperframes/<modelo>.html para compositions/<id>.html (trocando __ID__),
e monta a cena no index.html no tempo pedido (timeline do vídeo CORTADO).

Uso:
    python tools/add_overlay.py <edit>/hyperframes titulo  ov-tema 1.0 3.5 --var kicker=Hoje --var "title=Inteligência Artificial"
    python tools/add_overlay.py <edit>/hyperframes numero  ov-stat 4.6 5   --var value=50 --var prefix=+ --var suffix=% --var "label=em 2025"
    python tools/add_overlay.py <edit>/hyperframes cta     ov-cta 13.6 2.4
    python tools/add_overlay.py <edit>/hyperframes --list
    python tools/add_overlay.py <edit>/hyperframes --remove ov-stat

Para uma animação sob medida (que não é modelo), escreva compositions/<id>.html à mão e use
--custom: só o host é inserido.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates" / "hyperframes"
MARK = "    </div>\n    <script>"  # fim do #root no index gerado por prepare_hyperframes.py


def parse_var(s: str):
    k, v = s.split("=", 1)
    try:
        return k, (int(v) if re.fullmatch(r"-?\d+", v) else float(v) if re.fullmatch(r"-?\d+\.\d+", v) else v)
    except ValueError:
        return k, v


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hf_dir", type=Path)
    ap.add_argument("template", nargs="?")
    ap.add_argument("id", nargs="?")
    ap.add_argument("start", nargs="?", type=float)
    ap.add_argument("duration", nargs="?", type=float)
    ap.add_argument("--var", action="append", default=[])
    ap.add_argument("--custom", action="store_true", help="compositions/<id>.html já existe; só monta")
    ap.add_argument("--kind", default="graphics", choices=["graphics", "captions"],
                    help="trilha no Studio: graphics (padrão) ou captions (legendas)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--remove")
    args = ap.parse_args()

    hf = args.hf_dir.resolve()
    index = hf / "index.html"
    html = index.read_text()

    if args.list:
        print("modelos:", ", ".join(p.stem for p in sorted(TEMPLATES.glob("*.html"))))
        live = re.sub(r"<!--.*?-->", "", html, flags=re.S)
        for m in re.finditer(r'<div id="([\w-]+)" data-composition-id="[\w-]+" data-composition-src="[^"]+"\s+data-start="([\d.]+)" data-duration="([\d.]+)"', live):
            print(f"  {m.group(1):16s} {float(m.group(2)):7.2f}s  +{float(m.group(3)):.2f}s")
        return

    if args.remove:
        html, n = re.subn(rf'\n      <div id="{re.escape(args.remove)}" data-composition-id=.*?</div>', "", html, flags=re.S)
        index.write_text(html)
        (hf / "compositions" / f"{args.remove}.html").unlink(missing_ok=True)
        print(f"removido {args.remove}" if n else f"{args.remove} não encontrado")
        return

    if None in (args.template, args.id, args.start, args.duration):
        ap.error("informe modelo, id, início e duração")
    if not re.fullmatch(r"[a-z][\w-]*", args.id):
        ap.error("id: minúsculas, números, - e _")
    if f'id="{args.id}"' in html:
        ap.error(f"{args.id} já existe no index.html (use --remove antes)")

    comp = hf / "compositions" / f"{args.id}.html"
    if not args.custom:
        src = TEMPLATES / f"{args.template}.html"
        if not src.exists():
            ap.error(f"modelo '{args.template}' não existe em {TEMPLATES}")
        comp.write_text(src.read_text().replace("__ID__", args.id))
    elif not comp.exists():
        ap.error(f"{comp} não existe")

    # fim não pode passar do root
    root_dur = float(re.search(r'data-composition-id="main" data-start="0" data-duration="([\d.]+)"', html).group(1))
    W, H = re.search(r'data-width="(\d+)" data-height="(\d+)"', html).groups()
    dur = min(args.duration, round(root_dur - args.start, 3))
    # legendas sempre por cima de tudo (Hard Rule 1 do video-use)
    z = 100 if args.kind == "captions" else 2 + re.sub(r"<!--.*?-->", "", html, flags=re.S).count("data-composition-src=")
    values = dict(parse_var(v) for v in args.var)
    vv = f" data-variable-values='{json.dumps(values, ensure_ascii=False)}'" if values else ""
    host = (f'\n      <div id="{args.id}" data-composition-id="{args.id}" data-composition-src="compositions/{args.id}.html"\n'
            f'           data-start="{args.start}" data-duration="{dur}" data-track-index="{2 if args.kind == "captions" else 1}" data-track-kind="{args.kind}"\n'
            f'           data-width="{W}" data-height="{H}"{vv} style="z-index: {z}"></div>')
    if MARK not in html:
        raise SystemExit("não achei o fim do #root no index.html")
    index.write_text(html.replace(MARK, host + "\n" + MARK, 1))
    print(f"+ {args.id} ({args.template}) em {args.start:.2f}s por {dur:.2f}s")


if __name__ == "__main__":
    main()
