"""Gera um EDL (edl.json do video-use) cortando silêncios e repetições.

Estratégia (rascunho — o Claude revisa antes de renderizar):
  1. Lê as palavras de edit/transcripts/<nome>.json (formato Scribe).
  2. Remove trechos pedidos com --drop "ini-fim" (segundos, timeline da fonte).
  3. Com --auto-repeats, detecta repetições imediatas ("a inteligência, a inteligência")
     e falsos começos, e remove a PRIMEIRA ocorrência (a segunda costuma ser a boa).
  4. Agrupa palavras restantes em blocos; um gap > --max-gap entre palavras vira corte.
  5. Refina com o áudio real (ffmpeg silencedetect): silêncios detectados dentro de um
     bloco também são cortados — o Whisper costuma esticar o fim das palavras.
  6. Aplica padding (Hard Rule 7 do video-use: 30–200 ms) e grava edl.json.

Uso:
    python tools/auto_edl.py videos/proj/bruto.mp4
    python tools/auto_edl.py videos/proj/bruto.mp4 --auto-repeats --drop 12.3-14.1 --drop 40-41.5
    python tools/auto_edl.py videos/proj/bruto.mp4 --max-gap 0.6 --pad-before 0.08 --pad-after 0.15

Também imprime um relatório: blocos mantidos, cortes, repetições encontradas e duração final.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import unicodedata
from pathlib import Path


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^\w%]", "", t)


FILLERS = {"hum", "humm", "hm", "ahn", "ah", "eh", "e", "ee", "eee", "han", "uhm", "um", "uh",
           "hã", "ha", "tipo", "ne"}
# Só tratamos como filler se a palavra estiver isolada por pausa ou repetida; "e"/"tipo"/"né"
# são palavras reais. Fillers "puros" (sem significado) são cortados sempre:
# ("um" fica fora: em português é artigo — "comprar um imóvel".)
PURE_FILLERS = {"hum", "humm", "hm", "ahn", "ah", "ee", "eee", "han", "uhm", "uh", "ha"}


def probe_duration(video: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    return float(out.stdout.strip())


def detect_silences(video: Path, noise_db: float, min_dur: float) -> list[tuple[float, float]]:
    out = subprocess.run(
        ["ffmpeg", "-i", str(video), "-vn", "-af",
         f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    sil, start = [], None
    for line in out.splitlines():
        if m := re.search(r"silence_start: (-?[\d.]+)", line):
            start = max(0.0, float(m.group(1)))
        elif (m := re.search(r"silence_end: ([\d.]+)", line)) and start is not None:
            sil.append((start, float(m.group(1))))
            start = None
    return sil


def find_repeats(words: list[dict], max_n: int = 6, max_inner_gap: float = 0.9) -> list[tuple[int, int, str]]:
    """Retorna (i_ini, i_fim_exclusivo, texto) da 1ª ocorrência de n-gramas repetidos
    imediatamente em seguida. Prefere o maior n. As duas ocorrências não podem estar
    separadas por uma pausa longa (senão é só a mesma ideia em frases diferentes)."""
    toks = [norm(w["text"]) for w in words]
    drops: list[tuple[int, int, str]] = []
    i = 0
    while i < len(toks):
        found = False
        for n in range(max_n, 0, -1):
            a, b = toks[i:i + n], toks[i + n:i + 2 * n]
            if len(b) < n or a != b or not all(a):
                continue
            span = words[i:i + 2 * n]
            if any(span[k + 1]["start"] - span[k]["end"] > max_inner_gap for k in range(len(span) - 1)):
                continue
            if n == 1 and len(a[0]) <= 2 and a[0] not in PURE_FILLERS:
                continue  # "e e", "a a" curtos: deixa para a revisão manual
            drops.append((i, i + n, " ".join(w["text"] for w in words[i:i + n])))
            i += n
            found = True
            break
        if not found:
            i += 1
    return drops


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--edit-dir", type=Path, default=None)
    ap.add_argument("--max-gap", type=float, default=0.45, help="gap entre palavras que vira corte (s)")
    ap.add_argument("--pad-before", type=float, default=0.06)
    ap.add_argument("--pad-after", type=float, default=0.12)
    ap.add_argument("--noise-db", type=float, default=-35.0, help="limiar do silencedetect")
    ap.add_argument("--min-silence", type=float, default=0.45, help="silêncio mínimo do áudio a cortar (s)")
    ap.add_argument("--min-block", type=float, default=0.25, help="descarta blocos menores que isso (s)")
    ap.add_argument("--auto-repeats", action="store_true", help="remove repetições imediatas")
    ap.add_argument("--keep-fillers", action="store_true", help="não corta 'hum', 'ahn' etc.")
    ap.add_argument("--drop", action="append", default=[], help="faixa a remover 'ini-fim' (s, fonte)")
    ap.add_argument("--grade", default="none")
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()

    video = args.video.resolve()
    edit_dir = (args.edit_dir or video.parent / "edit").resolve()
    tjson = edit_dir / "transcripts" / f"{video.stem}.json"
    data = json.loads(tjson.read_text())
    words = [w for w in data["words"] if w.get("type") == "word" and w["text"].strip()]
    dur = probe_duration(video)

    removed: list[tuple[float, float, str]] = []

    # 1) faixas manuais
    drops = []
    for d in args.drop:
        a, b = (float(x) for x in d.split("-"))
        drops.append((a, b))
        removed.append((a, b, "manual"))

    def in_drop(w: dict) -> bool:
        mid = (w["start"] + w["end"]) / 2
        return any(a <= mid <= b for a, b in drops)

    keep_mask = [not in_drop(w) for w in words]

    # 2) fillers puros
    if not args.keep_fillers:
        for i, w in enumerate(words):
            if keep_mask[i] and norm(w["text"]) in PURE_FILLERS:
                keep_mask[i] = False
                removed.append((w["start"], w["end"], f"filler '{w['text']}'"))

    # 3) repetições
    repeats = find_repeats([w for w, k in zip(words, keep_mask) if k])
    if args.auto_repeats and repeats:
        kept_idx = [i for i, k in enumerate(keep_mask) if k]
        for a, b, txt in repeats:
            for j in kept_idx[a:b]:
                keep_mask[j] = False
            removed.append((words[kept_idx[a]]["start"], words[kept_idx[b - 1]]["end"], f"repetição '{txt}'"))

    kept = [w for w, k in zip(words, keep_mask) if k]
    if not kept:
        raise SystemExit("nada sobrou depois dos cortes")

    # 4) blocos por gap entre palavras (e por palavras removidas no meio)
    blocks: list[list[float]] = []
    prev_i = None
    for i, w in enumerate(words):
        if not keep_mask[i]:
            continue
        contiguous = prev_i is not None and all(keep_mask[prev_i:i + 1])
        if blocks and contiguous and w["start"] - words[prev_i]["end"] <= args.max_gap:
            blocks[-1][1] = w["end"]
        else:
            blocks.append([w["start"], w["end"]])
        prev_i = i

    # 5) refina com silêncios reais do áudio
    silences = detect_silences(video, args.noise_db, args.min_silence)
    refined: list[list[float]] = []
    for s, e in blocks:
        segs = [[s, e]]
        for ss, se in silences:
            nxt = []
            for a, b in segs:
                # corta o silêncio, mas preserva a margem de padding nas bordas
                cs, ce = ss + args.pad_after, se - args.pad_before
                if ce - cs < 0.15 or ce <= a or cs >= b:
                    nxt.append([a, b])
                    continue
                if cs > a:
                    nxt.append([a, cs - args.pad_after])
                if ce < b:
                    nxt.append([ce + args.pad_before, b])
            segs = nxt
        refined.extend(segs)

    # 6) padding e merge
    ranges: list[list[float]] = []
    for s, e in refined:
        s = max(0.0, s - args.pad_before)
        e = min(dur, e + args.pad_after)
        if e - s < args.min_block:
            continue
        if ranges and s <= ranges[-1][1] + 0.02:
            ranges[-1][1] = max(ranges[-1][1], e)
        else:
            ranges.append([s, e])

    def quote(a: float, b: float) -> str:
        return " ".join(w["text"] for w, k in zip(words, keep_mask) if k and w["end"] > a and w["start"] < b)

    edl = {
        "version": 1,
        "sources": {video.stem: str(video)},
        "ranges": [{"source": video.stem, "start": round(s, 3), "end": round(e, 3),
                    "quote": quote(s, e)} for s, e in ranges],
        "grade": args.grade,
        "overlays": [],
        "total_duration_s": round(sum(e - s for s, e in ranges), 2),
    }
    out = args.output or edit_dir / "edl.json"
    out.write_text(json.dumps(edl, indent=2, ensure_ascii=False))

    print(f"fonte: {dur:.1f}s  →  editado: {edl['total_duration_s']:.1f}s "
          f"({100 * (1 - edl['total_duration_s'] / dur):.0f}% removido), {len(ranges)} blocos")
    if repeats:
        print("repetições detectadas" + (" (removidas):" if args.auto_repeats else " (NÃO removidas, use --auto-repeats):"))
        for a, b, txt in repeats:
            print(f"   - '{txt}'")
    for a, b, why in removed:
        print(f"   corte {a:7.2f}-{b:7.2f}  {why}")
    for r in edl["ranges"]:
        print(f"   mantém {r['start']:7.2f}-{r['end']:7.2f}  {r['quote'][:70]}")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
