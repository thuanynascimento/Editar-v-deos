"""Render final: HyperFrames (vídeo cortado + animações) → final.mp4 com o áudio do video-use.

1. Roda `hyperframes check` (falha se houver erro).
2. Renderiza edit/hyperframes → edit/final_hf.mp4 usando o chrome-headless-shell
   (captura "beginframe", ~30% mais rápida que screenshot).
3. Troca a trilha de áudio por uma remontada da fonte com precisão de amostra (mesmos
   cortes do EDL, fades de 30 ms, -14 LUFS) — o mixer do HyperFrames sobe o volume e o
   concat de AAC do video-use desliza ~20 ms por corte.
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


def build_exact_audio(edit: Path, out_wav: Path) -> None:
    """Remonta o áudio direto da fonte, com precisão de amostra, usando as durações REAIS
    de cada segmento de vídeo (render.py arredonda cada um para um frame inteiro). Evita o
    deslize acumulado do AAC (priming de ~21 ms por segmento no concat -c copy).
    Fades de 30 ms em cada corte (Hard Rule 3) + loudnorm em 2 passes (-14 LUFS, -1 dBTP)."""
    import json
    sys.path.insert(0, str(ROOT / "tools"))
    from prepare_hyperframes import segment_durations  # noqa: E402
    edl = json.loads((edit / "edl.json").read_text())
    fps_raw = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=r_frame_rate", "-of", "csv=p=0", str(edit / "cortado.mp4")],
                             capture_output=True, text=True).stdout.strip()
    n, d = fps_raw.split("/")
    durs = segment_durations(edl, edit, round(int(n) / int(d)))
    srcs = list(edl["sources"].keys())
    inputs: list[str] = []
    clean = edit / "audio_limpo.wav"   # gerado por tools/denoise.py (mesma timeline da fonte)
    for k in srcs:
        use_clean = clean.exists() and len(srcs) == 1
        inputs += ["-i", str(clean) if use_clean else edl["sources"][k]]
    if clean.exists() and len(srcs) == 1:
        print("  áudio: usando a versão com ruído reduzido (audio_limpo.wav)")
    parts, labels = [], []
    for i, (r, dur) in enumerate(zip(edl["ranges"], durs)):
        si = srcs.index(r["source"])
        fo = max(0.0, dur - 0.03)
        parts.append(f"[{si}:a:0]atrim=start={r['start']:.6f}:duration={dur:.6f},asetpts=PTS-STARTPTS,"
                     f"aresample=48000,apad=whole_dur={dur:.6f},"
                     f"afade=t=in:st=0:d=0.03,afade=t=out:st={fo:.6f}:d=0.03[s{i}]")
        labels.append(f"[s{i}]")
    graph = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[cat]"
    raw = out_wav.with_suffix(".raw.wav")
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", graph, "-map", "[cat]",
                    "-c:a", "pcm_s16le", str(raw)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    meas = subprocess.run(["ffmpeg", "-i", str(raw), "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
                           "-f", "null", "-"], capture_output=True, text=True).stderr
    m = json.loads(meas[meas.rindex("{"):meas.rindex("}") + 1])
    ln = (f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-i", str(raw), "-af", ln + ",aresample=48000", "-c:a", "pcm_s16le", str(out_wav)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    raw.unlink(missing_ok=True)


def find_music(edit: Path) -> Path | None:
    for ext in ("wav", "mp3", "m4a", "aac", "flac", "ogg"):
        if (edit / f"musica.{ext}").exists():
            return edit / f"musica.{ext}"
    return None


def _lufs(wav: Path) -> float:
    r = subprocess.run(["ffmpeg", "-i", str(wav), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1])


def mix_music(voice_wav: Path, music: Path, out_wav: Path, gap_db: float, duck_db: float) -> None:
    """Mistura música de fundo sob a voz (já em -14 LUFS), de forma determinística e medida.
    - música ajustada para ficar gap_db abaixo da voz (loudness integrado) quando NÃO há fala
    - enquanto há fala, abaixa mais duck_db (envelope da voz: ataque 60 ms, soltura 400 ms)
    - fade-in 0.6 s, fade-out 1.2 s; repete a faixa se for mais curta que o vídeo
    - sem limitador com lookahead (atrasaria o áudio ~5 ms); se o pico passar de -1 dBFS,
      a mistura inteira desce o necessário — a sincronia fica exata"""
    import numpy as np
    sr = 48000

    def load(p: Path) -> np.ndarray:
        b = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                           capture_output=True, check=True).stdout
        return np.frombuffer(b, np.float32).reshape(-1, 2).copy()

    v = load(voice_wav)
    m = load(music)
    n = len(v)
    if len(m) < n:
        m = np.concatenate([m] * (n // len(m) + 1))
    m = m[:n]

    # nível: música (sozinha) gap_db abaixo da voz, em LUFS
    tmp = out_wav.with_suffix(".m.wav")
    _write(tmp, m, sr)
    gain_db = (_lufs(voice_wav) - gap_db) - _lufs(tmp)
    tmp.unlink(missing_ok=True)
    m *= 10 ** (gain_db / 20)

    # envelope da voz → ganho de ducking suave
    hop = sr // 100  # 10 ms
    mono = np.abs(v).mean(axis=1)
    frames = np.sqrt(np.add.reduceat(mono ** 2, np.arange(0, n, hop)) / hop)
    edb = 20 * np.log10(frames + 1e-9)
    speech = np.clip((edb + 45) / 10, 0, 1)  # 0 abaixo de -45 dB, 1 acima de -35 dB
    g = np.empty_like(speech)
    att, rel = 1 - np.exp(-1 / 6), 1 - np.exp(-1 / 40)  # 60 ms / 400 ms
    acc = 0.0
    for i, t in enumerate(speech):
        acc += (t - acc) * (att if t > acc else rel)
        g[i] = acc
    duck = 10 ** (-duck_db * np.repeat(g, hop)[:n] / 20)
    fade = np.ones(n, np.float32)
    fi, fo = int(0.6 * sr), int(1.2 * sr)
    fade[:fi] = np.linspace(0, 1, fi)
    fade[-fo:] = np.minimum(fade[-fo:], np.linspace(1, 0, fo))
    mix = v + m * (duck * fade)[:, None]
    peak = np.abs(mix).max()
    if peak > 0.89:
        mix *= 0.89 / peak
    _write(out_wav, mix, sr)


def _write(p: Path, x, sr: int) -> None:
    import numpy as np
    import wave
    y = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(y.shape[1]); w.setsampwidth(2); w.setframerate(sr); w.writeframes(y.tobytes())


def duration(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit_dir", type=Path)
    ap.add_argument("--quality", default="looks", choices=["draft", "looks", "delivery"])
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--skip-check", action="store_true")
    ap.add_argument("--musica-db", type=float, default=14.0,
                    help="quanto a música fica abaixo da voz nas pausas, em dB (padrão 14; menor = música mais alta)")
    ap.add_argument("--ducking-db", type=float, default=6.0, help="quanto a música abaixa a mais durante a fala")
    ap.add_argument("--sem-musica", action="store_true")
    ap.add_argument("--so-audio", action="store_true",
                    help="não renderiza o HyperFrames de novo: reaproveita o vídeo do final.mp4 e troca só o áudio")
    args = ap.parse_args()

    edit = args.edit_dir.resolve()
    hf = edit / "hyperframes"
    out = (args.output or edit / "final.mp4").resolve()
    raw = edit / "final_hf.mp4"
    audio_src = edit / "cortado.mp4"

    env = dict(os.environ)
    if (hs := headless_shell()) and "HYPERFRAMES_BROWSER_PATH" not in env:
        env["HYPERFRAMES_BROWSER_PATH"] = hs

    if args.so_audio:
        if not out.exists():
            sys.exit("--so-audio precisa de um final.mp4 já renderizado")
        subprocess.run(["ffmpeg", "-y", "-i", str(out), "-map", "0:v:0", "-c", "copy", str(raw)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("reaproveitando o vídeo do final.mp4 (só o áudio muda)")
    if not args.skip_check and not args.so_audio:
        r = subprocess.run([str(HF_BIN), "check", "--safe-zone", "reels"], cwd=hf, env=env, capture_output=True, text=True)
        tail = "\n".join((r.stdout + r.stderr).splitlines()[-25:])
        if r.returncode != 0 or "Check passed" not in r.stdout + r.stderr:
            print(tail)
            sys.exit("hyperframes check falhou — corrija antes de renderizar")
        print("check: ok")

    if not args.so_audio:
        print(f"renderizando HyperFrames ({args.quality})...", flush=True)
        r = subprocess.run([str(HF_BIN), "render", "--quality", args.quality, "-o", str(raw)],
                           cwd=hf, env=env, capture_output=True, text=True)
        summary = [ln for ln in (r.stdout + r.stderr).splitlines() if re.search(r"rendered in|capture ·|✗|Fix:", ln)]
        print("\n".join(summary))
        if r.returncode != 0 or not raw.exists():
            sys.exit("render falhou")

    # áudio: remontado da fonte com precisão de amostra (fallback: o do corte do video-use)
    wav = edit / "audio_final.wav"
    try:
        build_exact_audio(edit, wav)
        music = None if args.sem_musica else find_music(edit)
        if music:
            print(f"  música: {music.name} ({args.musica_db:.0f} dB abaixo da voz, ducking {args.ducking_db:.0f} dB)")
            mixed = edit / "audio_mix.wav"
            mix_music(wav, music, mixed, args.musica_db, args.ducking_db)
            mixed.replace(wav)
        a_in, a_codec = str(wav), ["-c:a", "aac", "-b:a", "192k"]
    except Exception as e:  # noqa: BLE001
        print(f"  aviso: áudio exato falhou ({e}); usando o áudio do cortado.mp4")
        a_in, a_codec = str(audio_src), ["-c:a", "copy"]
    subprocess.run(["ffmpeg", "-y", "-i", str(raw), "-i", a_in, "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", *a_codec, "-shortest", "-movflags", "+faststart", str(out)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    raw.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)

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
