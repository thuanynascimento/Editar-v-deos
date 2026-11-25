# Editar-v-deos — edição de vídeo pelo chat

A usuária manda um vídeo bruto (geralmente falado, em português) e eu devolvo o vídeo editado.
Pipeline em duas fases, sempre nesta ordem:

1. **video-use** (`vendor/video-use`, submódulo) — corta silêncios, hesitações e repetições.
2. **HyperFrames** (`node_modules/hyperframes`, npm) — adiciona animações e visualizações
   sincronizadas com o que está sendo dito, por cima do vídeo já cortado.

Fale sempre em português com a usuária. Ela não é técnica: explique o que vai fazer em linguagem
simples, sem nomes de arquivos internos, a não ser que ela pergunte.

## Preparação (sessão nova)

```bash
bash scripts/setup.sh          # submódulo, pip, npm — idempotente
```

Referências que devo ler conforme a necessidade:
- `vendor/video-use/SKILL.md` — regras de corte (as 12 Hard Rules valem aqui).
- `.claude/skills/hyperframes/SKILL.md` e `references/overlays.md`, `motion.md`, `captions.md` —
  contrato de composição do HyperFrames.

## Onde ficam os arquivos

```
videos/<projeto>/            ← fora do git (.gitignore)
├── bruto.mp4                ← original, nunca alterado
└── edit/
    ├── transcripts/bruto.json   transcrição palavra-a-palavra (formato Scribe), cacheada
    ├── takes_packed.md          frases com tempos da FONTE (leitura principal para cortar)
    ├── edl.json                 decisões de corte
    ├── cortado.mp4              saída do video-use (fase 1)
    ├── hyperframes/             projeto HyperFrames (fase 2)
    │   ├── transcricao_saida.md frases com tempos do vídeo CORTADO (para planejar animações)
    │   ├── assets/words.json    palavras na timeline cortada
    │   ├── index.html           vídeo + cenas de overlay
    │   └── compositions/*.html  uma animação por arquivo
    ├── final.mp4                entrega
    └── project.md               memória da sessão (anexar ao final)
```

Como o vídeo chega: anexo no chat (procure o arquivo enviado e copie para `videos/<projeto>/bruto.mp4`),
link direto baixável (curl / yt-dlp — se o host for bloqueado pela rede, peça para liberar), ou
commit no repositório para arquivos pequenos. O conector do Google Drive devolve base64 pelo
contexto: não serve para vídeo.

## Fase 1 — cortes (video-use)

```bash
P=videos/<projeto>
python tools/transcribe.py $P/bruto.mp4                     # local (faster-whisper, pt) ou Scribe se houver ELEVENLABS_API_KEY
python vendor/video-use/helpers/pack_transcripts.py --edit-dir $P/edit
python tools/auto_edl.py $P/bruto.mp4 --auto-repeats        # rascunho do EDL + relatório
```

Depois **eu reviso o rascunho lendo `takes_packed.md` e o relatório**:
- Repetições que o detector não pegou (frase recomeçada com palavras diferentes, falso começo,
  "não, pera, deixa eu falar de novo"): remover com `--drop ini-fim` (tempos da fonte) e rodar
  de novo. Na dúvida sobre um ponto, olhar `vendor/video-use/helpers/timeline_view.py <video> ini fim`.
- Sempre manter a ÚLTIMA tentativa de uma frase repetida (costuma ser a boa).
- Nunca cortar no meio de palavra; padding 30–200 ms (já no auto_edl).
- O auto_edl corta "hum/ahn/éé" puros; "né", "tipo", "então" ficam — julgar caso a caso.
- Ritmo: `--max-gap` 0.45 s é o padrão (dinâmico). Mais calmo: 0.7. Mais acelerado: 0.3.

Renderizar o corte:
```bash
python vendor/video-use/helpers/render.py $P/edit/edl.json -o $P/edit/cortado.mp4 --fps 24   # use a taxa da fonte
```
Vídeo de celular: a taxa média vem quebrada (23,998) — sempre passe `--fps` com o valor inteiro.
Conferir duração com ffprobe e, nos pontos de corte duvidosos, `timeline_view.py` no `cortado.mp4`.

Antes de renderizar a primeira vez, mostrar à usuária em 3–5 linhas o que vai sair (quanto tempo
cai, quais repetições saem) — Hard Rule 11 do video-use. Se ela pediu "pode fazer direto", siga.

## Fase 2 — animações (HyperFrames)

```bash
python tools/prepare_hyperframes.py $P/edit                 # cria edit/hyperframes com o corte + words.json
```

Ler `edit/hyperframes/transcricao_saida.md` e planejar as animações **pelo conteúdo falado**:
- Tema/assunto apresentado → `titulo` (lower third).
- Número, porcentagem, valor, ano marcante → `numero` (contagem animada que termina NA palavra).
- Pedido de inscrição/like/seguir → `cta`.
- Lista ("três coisas", "primeiro… segundo…"), comparação, processo, antes/depois, conceito
  abstrato → animação sob medida em `compositions/<id>.html` (seguindo o contrato do HyperFrames;
  antes de escrever do zero, `npx hyperframes catalog` para ver blocos prontos).
- Densidade: 1 animação a cada 6–10 s em vídeos curtos; nunca duas aparecendo juntas.
- Sincronia: a animação "pousa" no momento da palavra-chave → comece ~0.5–0.9 s antes.

```bash
H=$P/edit/hyperframes
python tools/add_overlay.py $H --list
python tools/add_overlay.py $H titulo ov-tema 1.0 3.5 --var kicker=Hoje --var "title=Inteligência Artificial"
python tools/add_overlay.py $H numero ov-stat 4.6 5 --var value=50 --var prefix=+ --var suffix=% --var "label=em 2025"
python tools/add_overlay.py $H cta ov-cta 13.5 2.5
python tools/add_overlay.py $H minha-cena ov-x 6 4 --custom      # composição escrita à mão
```

Legendas (sempre por cima das animações):
```bash
python tools/make_captions.py $H --emphasis "palavra,expressão de ênfase" --accent "#5CE1E6" --y 58 \
    --break "do que,uma renda"     # quebra antes de expressões, para cada linha ser uma ideia
```
Padrão: Montserrat branca sem contorno (sombra suave), centralizada, `--y` = centro vertical em %
da altura, `--width 72–78` para não invadir os botões do Reels. Grupos de até 4 palavras/22
caracteres. Reels: `check --safe-zone reels` (a área do TikTok é mais estreita à direita).

Estilo "Reels de autoridade" (referência da cliente em videos/reels-01/referencia):
```bash
python tools/make_titles.py $H titulos.json --accent "#5CE1E6"   # PALAVRA neon + manuscrito; "fim"
node_modules/.bin/hyperframes remove-background $P/edit/cortado.mp4 -o $P/edit/recorte/pessoa.webm --quality best
```
Sobre a pessoa, NUNCA manuscrito no rosto: meça o topo da cabeça no alpha do recorte e use
`"script_pos": "above"` (manuscrito curto entre o topo da tela e a cabeça), `size` ~150, `y` ~24.
Entrega: mandar também cópia leve (CRF 20, ~13 MB) com SendUserFile `display: "attach"` — o player
do chat não oferece salvar em alguns celulares.
Recorte da pessoa (z 50) por cima dos títulos neon → título ATRÁS dela; o manuscrito vai numa camada
`-esc` NA FRENTE (z 55). Fontes em `assets/fonts/` (npm pack @fontsource/yellowtail @fontsource/montserrat).
remove-background: se falhar instalando onnxruntime-node, rode
`npm install onnxruntime-node@1.21.1 --ignore-scripts --prefix ~/.cache/hyperframes/optional/onnxruntime-node@1.21.1`.
Estilo "academia/jiu-jitsu" (referência em videos/reels-02/referencia): `make_titles.py` com
`"style": "bloco"` (Anton branco + sombra sólida azul, `"count"` para contagem), `"etiqueta"` (cartão
branco texto azul), `"pilula"` (azul com ícone pin/link/cal), `--accent "#0B3D6E"`; legendas com
`--accent "#FFFFFF" --emph-bg "#0B3D6E"` (destaque marca-texto). Fontes: @fontsource/anton e caveat.
Filtro "laranja verde" CapCut ~30%: campo `grade` do edl.json =
`colorbalance=rs=-0.045:gs=0.015:bs=0.03:rm=0.015:gm=0.006:bm=-0.015:rh=0.036:gh=0.012:bh=-0.036,eq=saturation=1.05:contrast=1.03`.

Verificar e olhar antes de renderizar:
```bash
cd $H && npx hyperframes check && npx hyperframes snapshot --at 2.5,7.5,14.9
```
Ler o `contact-sheet.jpg` gerado em `.hyperframes/artifacts/snapshots/<id>/`: texto legível,
nada cobrindo o rosto, animação no momento certo.

Áudio — ruído e música (opcionais, antes do render final):
```bash
python tools/denoise.py $P/bruto.mov --ruido 1.5-3.9        # trecho SÓ de ruído, sem toque/bip
python tools/gerar_musica.py $P/edit --duracao 20 --opcao leve "warm acoustic ..., no vocals"
python tools/gerar_musica.py $P/edit --escolher leve         # vira edit/musica.wav
python tools/render_final.py $P/edit --so-audio             # troca só o áudio (sem re-render do vídeo)
```
Ruído: cadeia passa-altas → RNNoise (`models/sh.rnnn`) → perfil estacionário. Medir pausas vs
fala antes/depois; nunca o modo adaptativo do noisereduce (afina a voz). Música: MusicGen local
(sem direitos autorais), normalizada 18 dB abaixo da voz (`--musica-db`) + ducking na fala.
Lembrar a usuária: música do próprio Instagram (biblioteca do app) também é opção.

Render final (HyperFrames + áudio original do video-use, -14 LUFS):
```bash
python tools/render_final.py $P/edit                        # --quality draft para rascunho
```
Velocidade: ~3× o tempo do vídeo (vídeo de 1 min ≈ 3 min). Vídeos > 2 min: rodar em background.

## Entrega

- Mandar `final.mp4` para a usuária com SendUserFile e um resumo curto: duração antes/depois,
  o que foi cortado, quais animações entraram e em que momento.
- Anexar uma seção em `edit/project.md` (formato do SKILL.md do video-use).
- Pedidos de ajuste ("tira a animação do começo", "corta menos", "muda a cor"): editar
  `edl.json`/`index.html`/templates e re-renderizar só a fase necessária. Nunca re-transcrever.

## Personalização visual

Templates em `templates/hyperframes/` usam `--accent` (amarelo `#FFD43B`) e fonte Montserrat
(embutida no HyperFrames). Se a usuária tiver cores/fonte da marca, trocar nos templates e
registrar aqui.

## Ferramentas (`tools/`)

| Script | Fase | O que faz |
|---|---|---|
| `transcribe.py` | 1 | Whisper local (pt) ou Scribe → JSON formato Scribe |
| `auto_edl.py` | 1 | EDL cortando silêncios (palavras + silencedetect), fillers e repetições |
| `prepare_hyperframes.py` | 2 | Monta projeto HyperFrames com o corte e palavras remapeadas |
| `add_overlay.py` | 2 | Insere/lista/remove animações a partir dos templates |
| `make_captions.py` | 2 | Legendas palavra a palavra com ênfase, posição e quebras ajustáveis |
| `denoise.py` | 1½ | Redução de ruído de fundo (RNNoise + perfil) → audio_limpo.wav |
| `gerar_musica.py` | 2 | Música de fundo instrumental gerada localmente (MusicGen) |
| `make_titles.py` | 2 | Títulos de palavra-chave neon (atrás da pessoa) + manuscrito + encerramento |
| `render_final.py` | 2 | check → render (chrome-headless-shell) → áudio do video-use → final.mp4 |
