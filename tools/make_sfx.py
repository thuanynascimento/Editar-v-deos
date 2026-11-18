"""Efeitos sonoros sintetizados (sem direitos autorais) → <edit>/sfx.wav, na timeline do corte.

O render_final.py soma o sfx.wav à voz + música automaticamente.

Efeitos:
  --tique INI-FIM  tique-taque de relógio/cronômetro de INI a FIM (s), um toque a cada --passo s
                   (tique agudo e taque grave alternados). Use o mesmo início/passo na animação
                   para o ponteiro "pular" junto com o som.

Uso:
    python tools/make_sfx.py videos/proj/edit --tique 8.6-12.0 --passo 0.25 --db -20
"""
from __future__ import annotations

import argparse
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 48000


def tick(high: bool) -> np.ndarray:
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(7 if high else 11)  # determinístico
    click = rng.standard_normal(n) * np.exp(-t / 0.0025)
    f1, f2 = (3200, 5100) if high else (2300, 3700)
    body = (np.sin(2 * np.pi * f1 * t) * 0.8 + np.sin(2 * np.pi * f2 * t) * 0.4) * np.exp(-t / 0.012)
    wood = np.sin(2 * np.pi * (900 if high else 700) * t) * np.exp(-t / 0.02) * 0.5
    x = click * 0.5 + body + wood
    return x / np.abs(x).max()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit_dir", type=Path)
    ap.add_argument("--tique", action="append", default=[], help="faixa INI-FIM (s) do tique-taque")
    ap.add_argument("--passo", type=float, default=0.25, help="intervalo entre toques (s)")
    ap.add_argument("--db", type=float, default=-20.0, help="pico de cada toque em dBFS")
    args = ap.parse_args()

    edit = args.edit_dir
    src = edit / "cortado.mp4"
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(src)], capture_output=True, text=True).stdout)
    out = np.zeros(int(dur * SR) + SR, np.float32)
    amp = 10 ** (args.db / 20)
    for rng_s in args.tique:
        a, b = (float(x) for x in rng_s.split("-"))
        k, t0 = 0, a
        while t0 <= b + 1e-6:
            x = tick(k % 2 == 0) * amp
            # leve crescendo e fade nos 3 últimos toques
            left = int(round((b - t0) / args.passo))
            x *= min(1.0, 0.6 + 0.08 * k) * (1.0 if left >= 3 else 0.55 + 0.15 * left)
            i = int(round(t0 * SR))
            out[i:i + len(x)] += x
            k += 1
            t0 = a + k * args.passo
        print(f"  tique-taque {a:.2f}–{b:.2f}s: {k} toques a cada {args.passo}s")
    out = out[:int(dur * SR)]
    st = np.stack([out, out], 1)
    y = (np.clip(st, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(edit / "sfx.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(y.tobytes())
    print(f"→ {edit / 'sfx.wav'}")


if __name__ == "__main__":
    main()
