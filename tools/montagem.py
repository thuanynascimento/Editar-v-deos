"""Montagem com passagens suaves e camadas de b-roll (substitui o render.py na fase 1).

Folha de estilo do Paulo Rosa Luz: nada de corte seco.
  * Entre dois trechos da fala: o trecho que sai continua por baixo e some em
    --dissolve segundos (padrão 0,15 s) por cima do que entra. A timeline NÃO muda:
    cada segmento dura exatamente ceil(len*fps)/fps, igual ao render.py, então
    prepare_hyperframes.py e render_final.py (áudio exato do EDL) continuam valendo.
  * Transições especiais por corte (troca de ambiente/etapa) e camadas de takes extras
    (b-roll, sem som) vêm de edit/montagem.json:

    {
      "transicoes": {"3": {"dur": 0.5, "zoom": 0.04}},       # chave = índice do range que ENTRA
      "camadas": [
        {"arquivo": "../broll/6418.mov", "de": 1.0, "inicio": 4.2, "dur": 3.0,
         "fade": 0.4, "zoom": 0.05}
      ]
    }
      de      = segundo do take onde a camada começa
      inicio  = segundo do vídeo CORTADO onde ela aparece
      zoom    = aproximação lenta (0.04 = 4% ao longo da duração; transições: em 1,5 s)

Uso:
    python tools/montagem.py videos/proj/edit              # → edit/cortado.mp4
    python tools/montagem.py videos/proj/edit --dissolve 0.2 --fps 30
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(r.stderr[-3000:])


def probe_size(path: str) -> tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:stream_side_data=rotation", "-of", "json", path],
                       capture_output=True, text=True)
    st = json.loads(r.stdout)["streams"][0]
    w, h = st["width"], st["height"]
    rot = 0
    for sd in st.get("side_data_list", []) or []:
        rot = int(sd.get("rotation", 0) or 0)
    return (h, w) if abs(rot) in (90, 270) else (w, h)


def fit(w: int, h: int, zoom: float, dur: float) -> str:
    """Escala para cobrir w×h (com aproximação lenta opcional) e corta no centro."""
    if zoom > 0:
        z = f"(1+{zoom}*min(t/{dur:.3f},1))"
        return (f"scale=w='{w}*{z}':h='{h}*{z}':force_original_aspect_ratio=increase:eval=frame,"
                f"crop={w}:{h},setsar=1")
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit_dir", type=Path)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--dissolve", type=float, default=0.15, help="mistura padrão entre trechos da fala (s)")
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--crf", type=int, default=17)
    args = ap.parse_args()

    edit = args.edit_dir.resolve()
    edl = json.loads((edit / "edl.json").read_text())
    cfg_path = edit / "montagem.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    trans = {int(k): v for k, v in cfg.get("transicoes", {}).items()}
    layers = cfg.get("camadas", [])
    fps = args.fps
    out = args.output or edit / "cortado.mp4"

    ranges = edl["ranges"]
    nframes = [math.ceil(round((r["end"] - r["start"]) * fps, 6)) for r in ranges]
    offsets = [sum(nframes[:i]) / fps for i in range(len(ranges))]
    total = sum(nframes) / fps
    W, H = probe_size(edl["sources"][ranges[0]["source"]])

    inputs: list[str] = []
    graph: list[str] = []
    cat_v, cat_a = [], []
    tails: list[tuple[str, float]] = []   # (label, início na saída)
    for i, r in enumerate(ranges):
        src = edl["sources"][r["source"]]
        n = nframes[i]
        t_in = trans.get(i + 1, {})
        d_out = 0.0 if i == len(ranges) - 1 else float(t_in.get("dur", args.dissolve))
        tail_n = round(d_out * fps)
        span = (n + tail_n) / fps + 0.2
        inputs += ["-ss", f"{r['start']:.6f}", "-t", f"{span:.6f}", "-i", src]
        k = len(inputs) // 6 - 1
        zoom_in = float(trans.get(i, {}).get("zoom", 0) or 0)
        body = fit(W, H, zoom_in, 1.5) if zoom_in else f"scale={W}:{H},setsar=1"
        v = f"[{k}:v]fps={fps},{body},format=yuv420p"
        if tail_n:
            graph.append(f"{v},split[b{i}][t{i}]")
            graph.append(f"[b{i}]trim=end_frame={n},setpts=PTS-STARTPTS[v{i}]")
            st = offsets[i + 1]
            graph.append(f"[t{i}]trim=start_frame={n}:end_frame={n + tail_n},setpts=PTS-STARTPTS+{st:.6f}/TB,"
                         f"format=yuva420p,fade=t=out:st={st:.6f}:d={d_out:.6f}:alpha=1[tl{i}]")
            tails.append((f"tl{i}", st))
        else:
            graph.append(f"{v},trim=end_frame={n},setpts=PTS-STARTPTS[v{i}]")
        dur = n / fps
        graph.append(f"[{k}:a]atrim=duration={dur:.6f},asetpts=PTS-STARTPTS,aresample=48000,"
                     f"apad=whole_dur={dur:.6f},afade=t=in:d=0.03,afade=t=out:st={max(0, dur - 0.03):.6f}:d=0.03[a{i}]")
        cat_v.append(f"[v{i}]")
        cat_a.append(f"[a{i}]")
    graph.append("".join(x for pair in zip(cat_v, cat_a) for x in pair) +
                 f"concat=n={len(ranges)}:v=1:a=1[base][aout]")

    cur = "base"
    for j, (lab, _) in enumerate(tails):
        graph.append(f"[{cur}][{lab}]overlay=eof_action=pass:format=auto[o{j}]")
        cur = f"o{j}"

    for j, L in enumerate(layers):
        p = Path(L["arquivo"])
        p = p if p.is_absolute() else (edit / p).resolve()
        inputs += ["-ss", f"{float(L.get('de', 0)):.3f}", "-t", f"{float(L['dur']):.3f}", "-i", str(p)]
        k = len(inputs) // 6 - 1
        d, f, st = float(L["dur"]), float(L.get("fade", 0.4)), float(L["inicio"])
        graph.append(f"[{k}:v]fps={fps},{fit(W, H, float(L.get('zoom', 0) or 0), d)},format=yuva420p,"
                     f"trim=duration={d:.3f},fade=t=in:st=0:d={f:.3f}:alpha=1,"
                     f"fade=t=out:st={d - f:.3f}:d={f:.3f}:alpha=1,setpts=PTS-STARTPTS+{st:.6f}/TB[L{j}]")
        graph.append(f"[{cur}][L{j}]overlay=eof_action=pass:format=auto[c{j}]")
        cur = f"c{j}"
    graph.append(f"[{cur}]format=yuv420p,trim=duration={total:.6f}[vout]")

    script = edit / "montagem.filtergraph"
    script.write_text(";\n".join(graph))
    print(f"  {len(ranges)} trechos, {len(tails)} passagens suaves, {len(layers)} camadas → {total:.2f} s")
    run(["ffmpeg", "-y", *inputs, "-filter_complex_script", str(script), "-map", "[vout]", "-map", "[aout]",
         "-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf), "-r", str(fps),
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    print(f"→ {out}")


if __name__ == "__main__":
    main()
