"""Transcreve um vídeo para o formato JSON do ElevenLabs Scribe (o que o video-use lê).

Dois motores:
  * scribe  — ElevenLabs Scribe (melhor para fillers "éé", "hum"; precisa de ELEVENLABS_API_KEY).
              Delega para vendor/video-use/helpers/transcribe.py.
  * local   — faster-whisper rodando na CPU, grátis. Gera o MESMO formato (words com
              type=word/spacing, start/end, speaker_id), então pack_transcripts.py,
              timeline_view.py e render.py funcionam sem mudança.

Padrão: "auto" → scribe se houver chave, senão local.

Uso:
    python tools/transcribe.py videos/meu-video/bruto.mp4
    python tools/transcribe.py videos/meu-video/bruto.mp4 --engine local --model small
    python tools/transcribe.py videos/meu-video/bruto.mp4 --language pt

Saída: <pasta do vídeo>/edit/transcripts/<nome>.json  (cacheado: não refaz se já existir)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEO_USE_HELPERS = ROOT / "vendor" / "video-use" / "helpers"

# Prompt inicial que "ensina" o Whisper a NÃO limpar hesitações. Sem isso ele
# normaliza a fala e some com os "é...", "hum", "tipo", que são justamente o
# que queremos cortar.
FILLER_PROMPT = (
    "Hum, é... então, tipo, né? Ahn, eu, eu acho que, hã, a gente, a gente vai... "
    "Uhm, bom, enfim."
)


def has_scribe_key() -> bool:
    if os.environ.get("ELEVENLABS_API_KEY"):
        return True
    for env in (ROOT / ".env", ROOT / "vendor" / "video-use" / ".env"):
        if env.exists() and any(
            ln.strip().startswith("ELEVENLABS_API_KEY=") and len(ln.strip()) > 20
            for ln in env.read_text().splitlines()
        ):
            return True
    return False


def extract_audio(video: Path, dest: Path, track: int) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-map", f"0:a:{track}", "-vn",
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def transcribe_local(video: Path, out_path: Path, model_name: str, language: str | None,
                     track: int) -> None:
    from faster_whisper import WhisperModel  # import tardio: pesado

    print(f"  [local] carregando modelo whisper '{model_name}' (CPU, int8)...", flush=True)
    model = WhisperModel(model_name, device="cpu", compute_type="int8")

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        extract_audio(video, wav, track)
        t0 = time.time()
        # Lê o wav direto em numpy: evita depender do PyAV (versões quebram a API).
        import wave
        import numpy as np
        with wave.open(str(wav), "rb") as wf:
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        audio = audio.astype(np.float32) / 32768.0
        segments, info = model.transcribe(
            audio,
            language=language,
            word_timestamps=True,
            initial_prompt=FILLER_PROMPT,
            condition_on_previous_text=False,  # evita alucinação em loop
            vad_filter=False,                  # queremos ver os silêncios, não escondê-los
            beam_size=5,
        )
        words: list[dict] = []
        for seg in segments:
            for w in seg.words or []:
                text = w.word.strip()
                if not text:
                    continue
                words.append({
                    "text": text,
                    "start": round(float(w.start), 3),
                    "end": round(float(w.end), 3),
                    "type": "word",
                    "speaker_id": "speaker_0",
                    "logprob": round(float(w.probability), 3),
                })
            print(f"    {seg.end:7.1f}s  {seg.text.strip()[:70]}", flush=True)

    # Intercala entradas "spacing" como o Scribe faz (pack_transcripts usa os gaps).
    full: list[dict] = []
    for i, w in enumerate(words):
        if i > 0:
            prev = words[i - 1]
            if w["start"] < prev["end"]:  # whisper às vezes sobrepõe
                w["start"] = prev["end"]
                w["end"] = max(w["end"], w["start"] + 0.02)
            full.append({"text": " ", "start": prev["end"], "end": w["start"],
                         "type": "spacing", "speaker_id": "speaker_0"})
        full.append(w)

    payload = {
        "language_code": info.language,
        "language_probability": round(float(info.language_probability), 3),
        "text": " ".join(w["text"] for w in words),
        "words": full,
        "_engine": f"faster-whisper/{model_name}",
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"  salvo: {out_path} ({len(words)} palavras, {time.time() - t0:.1f}s)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--edit-dir", type=Path, default=None)
    ap.add_argument("--engine", choices=["auto", "scribe", "local"], default="auto")
    ap.add_argument("--model", default="small",
                    help="modelo faster-whisper (tiny, base, small, medium, large-v3). Padrão: small")
    ap.add_argument("--language", default="pt", help="código ISO (padrão: pt). 'auto' para detectar")
    ap.add_argument("--audio-track", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="refaz mesmo se houver cache")
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"vídeo não encontrado: {video}")
    edit_dir = (args.edit_dir or video.parent / "edit").resolve()
    (edit_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    suffix = "" if args.audio_track == 0 else f".track{args.audio_track}"
    out_path = edit_dir / "transcripts" / f"{video.stem}{suffix}.json"
    language = None if args.language == "auto" else args.language

    if out_path.exists() and not args.force:
        print(f"cache: {out_path}")
        return
    if args.force:
        out_path.unlink(missing_ok=True)

    engine = args.engine
    if engine == "auto":
        engine = "scribe" if has_scribe_key() else "local"
    print(f"transcrevendo {video.name} com motor '{engine}'")

    if engine == "scribe":
        cmd = [sys.executable, str(VIDEO_USE_HELPERS / "transcribe.py"), str(video),
               "--edit-dir", str(edit_dir), "--audio-track", str(args.audio_track)]
        if language:
            cmd += ["--language", language]
        subprocess.run(cmd, check=True)
    else:
        transcribe_local(video, out_path, args.model, language, args.audio_track)


if __name__ == "__main__":
    main()
