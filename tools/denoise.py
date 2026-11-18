"""Reduz o ruído de fundo do áudio da fonte (antes da montagem final).

Gera <edit>/audio_limpo.wav com a MESMA duração e timeline da fonte. O render_final.py usa
esse arquivo no lugar do áudio original quando ele existe, então os cortes do EDL continuam
valendo sem mudança.

Como funciona (cadeia medida no reels-01: ruído nas pausas -7 dB, timbre da voz idêntico):
  1. Passa-altas suave (padrão 80 Hz): tira ronco grave de trânsito/vento/ar-condicionado.
  2. RNNoise (ffmpeg arnndn, models/sh.rnnn): rede treinada em voz; acompanha ruído que muda
     ao longo do tempo sem afinar a voz.
  3. Redução espectral (noisereduce, estacionária) com um TRECHO SÓ DE RUÍDO como perfil
     (--ruido ini-fim, segundos da fonte). Escolha um silêncio LIMPO: sem toque no celular,
     bip de início de gravação etc. — isso contamina o perfil. Sem --ruido, pula esta etapa.
  4. --forca (0–1) controla a etapa 3. 0.8 limpa bem sem deixar a voz "metálica".

NÃO use o modo adaptativo do noisereduce: no teste ele baixou a voz 6 dB (som "embaixo d'água").

Uso:
    python tools/denoise.py videos/proj/bruto.mov --ruido 0.3-4.2
    python tools/denoise.py videos/proj/bruto.mov --ruido 0.3-4.2 --forca 0.9 --highpass 100
    python tools/denoise.py videos/proj/bruto.mov --off          # remove o áudio limpo (volta ao original)
"""

from __future__ import annotations

import argparse
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def read_wav(p: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(p), "rb") as w:
        sr, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return x.reshape(-1, ch).T, sr  # (canais, amostras)


def write_wav(p: Path, x: np.ndarray, sr: int) -> None:
    y = (np.clip(x.T, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(x.shape[0])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(y.tobytes())


def rms_db(x: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--edit-dir", type=Path, default=None)
    ap.add_argument("--ruido", default=None, help="trecho só de ruído 'ini-fim' (s, fonte)")
    ap.add_argument("--forca", type=float, default=0.8, help="0–1, quanto do ruído remover")
    ap.add_argument("--highpass", type=int, default=80, help="Hz (0 desliga)")
    ap.add_argument("--sem-rnnoise", action="store_true", help="pula a etapa RNNoise")
    ap.add_argument("--off", action="store_true")
    args = ap.parse_args()

    import noisereduce as nr

    video = args.video.resolve()
    edit = (args.edit_dir or video.parent / "edit").resolve()
    out = edit / "audio_limpo.wav"
    if args.off:
        out.unlink(missing_ok=True)
        print("áudio limpo removido; o render volta a usar o áudio original")
        return

    raw = edit / "audio_fonte.wav"
    af = [f"highpass=f={args.highpass}:poles=2"] if args.highpass else []
    model = ROOT / "models" / "sh.rnnn"
    if model.exists() and not args.sem_rnnoise:
        af.append(f"arnndn=m={model}")
    else:
        print("aviso: RNNoise desligado (models/sh.rnnn ausente ou --sem-rnnoise)")
    subprocess.run(["ffmpeg", "-y", "-i", str(video), "-map", "0:a:0", "-vn", "-ac", "2", "-ar", "48000",
                    *(["-af", ",".join(af)] if af else []), "-c:a", "pcm_s16le", str(raw)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    x, sr = read_wav(raw)

    kw = dict(sr=sr, prop_decrease=args.forca, n_fft=2048, freq_mask_smooth_hz=300, time_mask_smooth_ms=60)
    if args.ruido:
        a, b = (float(v) for v in args.ruido.split("-"))
        noise = x[:, int(a * sr):int(b * sr)]
        y = np.stack([nr.reduce_noise(y=ch, y_noise=nch, stationary=True, **kw) for ch, nch in zip(x, noise)])
        before, after = rms_db(noise), rms_db(y[:, int(a * sr):int(b * sr)])
        print(f"ruído de fundo: {before:.1f} dB → {after:.1f} dB ({before - after:.1f} dB a menos)")
    else:
        y = x
        print("sem trecho de ruído (--ruido): só passa-altas + RNNoise")

    write_wav(out, y.astype(np.float32), sr)
    raw.unlink(missing_ok=True)
    print(f"→ {out}")


if __name__ == "__main__":
    main()
