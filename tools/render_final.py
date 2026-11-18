"""Render final: HyperFrames (vídeo cortado + animações) → final.mp4 com o áudio do video-use.

1. Roda `hyperframes check` (falha se houver erro).
2. Renderiza edit/hyperframes → edit/final_hf.mp4 usando o chrome-headless-shell
   (captura "beginframe", ~30% mais rápida que screenshot).
3. Troca a trilha de áudio pela do corte do video-use (já normalizado a -14 LUFS,
   com fades de 30 ms nos cortes) — o mixer do HyperFrames sobe o volume.
4. Confere duração e loudness.

Uso:
    python tools/render_final.py videos/proj/edit
    python tools/render_final.py videos/proj/edit --quality draft     # rascunho rápido
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HF_BIN = ROOT / "node_modules" / ".bin" / "hyperframes"


def headless_shell() -> str | None:
    hits = sorted(glob.glob("/opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    return hits[-1] if hits else None


def duration(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit_dir", type=Path)
    ap.add_argument("--quality", default="looks", choices=["draft", "looks", "delivery"])
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--skip-check", action="store_true")
    args = ap.parse_args()

    edit = args.edit_dir.resolve()
    hf = edit / "hyperframes"
    out = (args.output or edit / "final.mp4").resolve()
    raw = edit / "final_hf.mp4"
    audio_src = edit / "cortado.mp4"

    env = dict(os.environ)
    if (hs := headless_shell()) and "HYPERFRAMES_BROWSER_PATH" not in env:
        env["HYPERFRAMES_BROWSER_PATH"] = hs

    if not args.skip_check:
        r = subprocess.run([str(HF_BIN), "check"], cwd=hf, env=env, capture_output=True, text=True)
        tail = "\n".join((r.stdout + r.stderr).splitlines()[-25:])
        if r.returncode != 0 or "Check passed" not in r.stdout + r.stderr:
            print(tail)
            sys.exit("hyperframes check falhou — corrija antes de renderizar")
        print("check: ok")

    print(f"renderizando HyperFrames ({args.quality})...", flush=True)
    r = subprocess.run([str(HF_BIN), "render", "--quality", args.quality, "-o", str(raw)],
                       cwd=hf, env=env, capture_output=True, text=True)
    summary = [ln for ln in (r.stdout + r.stderr).splitlines() if re.search(r"rendered in|capture ·|✗|Fix:", ln)]
    print("\n".join(summary))
    if r.returncode != 0 or not raw.exists():
        sys.exit("render falhou")

    # áudio do video-use por cima do vídeo do HyperFrames
    subprocess.run(["ffmpeg", "-y", "-i", str(raw), "-i", str(audio_src), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(out)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    raw.unlink(missing_ok=True)

    d_out, d_cut = duration(out), duration(audio_src)
    loud = subprocess.run(["ffmpeg", "-i", str(out), "-af", "ebur128=peak=true", "-f", "null", "-"],
                          capture_output=True, text=True).stderr
    i_lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", loud)
    peak = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", loud)
    print(f"final: {out}")
    print(f"  duração {d_out:.2f}s (corte {d_cut:.2f}s) · loudness {i_lufs[-1] if i_lufs else '?'} LUFS · "
          f"pico {peak[-1] if peak else '?'} dBTP · {out.stat().st_size / 1e6:.1f} MB")
    if abs(d_out - d_cut) > 0.15:
        print("  ATENÇÃO: duração diverge do corte")


if __name__ == "__main__":
    main()
