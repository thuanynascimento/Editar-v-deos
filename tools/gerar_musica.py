"""Gera música de fundo instrumental, livre de direitos, com MusicGen (Meta) rodando na CPU.

A música é feita aqui mesmo: não há problema de direitos autorais nem bloqueio por
"música protegida" no Instagram/TikTok. Gera várias opções para a usuária escolher.

Uso:
    python tools/gerar_musica.py videos/proj/edit --duracao 20 \\
        --opcao leve "warm uplifting acoustic guitar and soft piano, gentle, real estate ad, no vocals" \\
        --opcao moderna "modern chill lofi beat, soft keys, mellow, positive, no vocals"

Saída: <edit>/musicas/<nome>.wav  — para usar uma: copie para <edit>/musica.wav
(ou rode com --escolher <nome>). O render_final.py mistura <edit>/musica.* automaticamente.
"""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit_dir", type=Path)
    ap.add_argument("--opcao", nargs=2, action="append", metavar=("NOME", "DESCRICAO"), default=[],
                    help="nome curto e descrição em inglês do estilo (pode repetir)")
    ap.add_argument("--duracao", type=float, default=20.0, help="segundos (máx. ~30 por geração)")
    ap.add_argument("--modelo", default="facebook/musicgen-small")
    ap.add_argument("--semente", type=int, default=7)
    ap.add_argument("--escolher", default=None, help="copia musicas/<nome>.wav para musica.wav")
    args = ap.parse_args()

    edit = args.edit_dir.resolve()
    pasta = edit / "musicas"
    if args.escolher:
        src = pasta / f"{args.escolher}.wav"
        shutil.copy(src, edit / "musica.wav")
        print(f"música escolhida: {src.name} → musica.wav")
        return
    if not args.opcao:
        ap.error("informe ao menos uma --opcao")

    import numpy as np
    import scipy.io.wavfile as wavfile
    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    torch.manual_seed(args.semente)
    torch.set_num_threads(max(1, (torch.get_num_threads())))
    print(f"carregando {args.modelo}...", flush=True)
    proc = AutoProcessor.from_pretrained(args.modelo)
    model = MusicgenForConditionalGeneration.from_pretrained(args.modelo)
    sr = model.config.audio_encoder.sampling_rate
    tokens = int(args.duracao * model.config.audio_encoder.frame_rate) + 4
    pasta.mkdir(parents=True, exist_ok=True)

    for nome, desc in args.opcao:
        t0 = time.time()
        inputs = proc(text=[desc], padding=True, return_tensors="pt")
        with torch.no_grad():
            audio = model.generate(**inputs, do_sample=True, guidance_scale=3.0, max_new_tokens=tokens)
        x = audio[0, 0].cpu().numpy().astype(np.float32)
        x = x / (np.abs(x).max() + 1e-9) * 0.89
        out = pasta / f"{nome}.wav"
        wavfile.write(out, sr, x)
        print(f"  {nome}: {len(x) / sr:.1f}s em {time.time() - t0:.0f}s → {out}", flush=True)


if __name__ == "__main__":
    main()
