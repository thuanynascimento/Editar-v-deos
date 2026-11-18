# Editar vídeos pelo chat

Mande um vídeo falado e peça a edição. O Claude:

1. **Corta silêncios, "éé"/"hum" e repetições** com o [video-use](https://github.com/browser-use/video-use).
2. **Adiciona animações ligadas ao que está sendo dito** com o [HyperFrames](https://github.com/heygen-com/hyperframes):
   títulos de tema, números animados, chamadas para inscrição e cenas sob medida.
3. Devolve o `final.mp4` com o áudio normalizado para redes sociais (-14 LUFS).

## Como usar

1. Envie o vídeo no chat (ou um link para download direto).
2. Diga o que quer, por exemplo:
   - "Edita esse vídeo: corta os silêncios e as repetições e coloca animações."
   - "Quero um ritmo mais calmo, sem cortar tanto."
   - "Coloca o número 50% animado quando eu falo do crescimento."
3. Peça ajustes à vontade: "tira a animação do começo", "muda a cor para azul".

## Estrutura

| Pasta | O que tem |
|---|---|
| `vendor/video-use` | video-use (submódulo git) |
| `tools/` | scripts que ligam as duas ferramentas |
| `templates/hyperframes/` | modelos de animação (título, número, inscreva-se) |
| `videos/` | seus vídeos e as saídas (fora do git) |
| `CLAUDE.md` | o passo a passo que o Claude segue |

## Instalação (feita automaticamente nas sessões)

```bash
bash scripts/setup.sh
```

Requisitos: Python 3.10+, Node.js 22+ e ffmpeg. A transcrição roda localmente (Whisper) e não
precisa de chave. Se quiser a transcrição da ElevenLabs, que é melhor para detectar hesitações,
coloque `ELEVENLABS_API_KEY=...` em um arquivo `.env`.
