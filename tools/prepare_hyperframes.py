"""Ponte video-use → HyperFrames.

Depois que o video-use renderizou o corte (edit/cortado.mp4 a partir de edit/edl.json),
este script monta um projeto HyperFrames em edit/hyperframes/ com:

  assets/video.mp4         o corte, re-encodado com keyframe a cada 1 s (seek preciso no render)
  assets/words.json        palavras na timeline do VÍDEO CORTADO (não da fonte)
  transcricao_saida.md     frases com tempos da saída — é daqui que planejo as animações
  index.html               composição raiz: vídeo em tela cheia + espaço para as cenas de overlay
  compositions/            onde entram as animações (uma cena por arquivo)

Uso:
    python tools/prepare_hyperframes.py videos/proj/edit
    python tools/prepare_hyperframes.py videos/proj/edit --video edit/cortado.mp4 --force
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HF_BIN = ROOT / "node_modules" / ".bin" / "hyperframes"
TEMPLATES = ROOT / "templates" / "hyperframes"


def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,duration:format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    )
    d = json.loads(out.stdout)
    st = d["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return {"w": st["width"], "h": st["height"], "fps": round(int(num) / int(den)),
            # duração do VÍDEO (o áudio AAC pode passar alguns ms; o root não pode passar do vídeo)
            "dur": float(st.get("duration") or d["format"]["duration"])}


def segment_durations(edl: dict, edit_dir: Path, fps: int) -> list[float]:
    """Duração REAL de cada segmento no corte. O render.py arredonda cada segmento para
    cima até um frame inteiro; usar o comprimento do EDL acumula erro de até 1 frame por corte."""
    import math
    segs = sorted((edit_dir / "clips_graded").glob("seg_*.mp4"))
    if len(segs) == len(edl["ranges"]):
        out = []
        for f in segs:
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=duration", "-of", "csv=p=0", str(f)], capture_output=True, text=True)
            out.append(float(r.stdout.strip()))
        return out
    return [math.ceil(round((r["end"] - r["start"]) * fps, 6)) / fps for r in edl["ranges"]]


def remap_words(edl: dict, edit_dir: Path, seg_durs: list[float]) -> list[dict]:
    """Palavras da fonte → timeline de saída: t_out = t_src - range.start + offset."""
    cache: dict[str, list[dict]] = {}
    out: list[dict] = []
    offset = 0.0
    for r, seg_dur in zip(edl["ranges"], seg_durs):
        src = r["source"]
        if src not in cache:
            tj = edit_dir / "transcripts" / f"{src}.json"
            cache[src] = [w for w in json.loads(tj.read_text())["words"] if w.get("type") == "word"]
        a, b = r["start"], r["end"]
        for w in cache[src]:
            if w["end"] <= a or w["start"] >= b:
                continue
            # o Whisper estica as bordas das palavras: uma palavra que encosta em DOIS trechos
            # entra só naquele em que mais aparece — evita "e e", "falo falo" nas emendas
            ov = min(w["end"], b) - max(w["start"], a)
            if any(min(w["end"], r2["end"]) - max(w["start"], r2["start"]) > ov
                   for r2 in edl["ranges"] if r2 is not r and r2["source"] == src):
                continue
            s = max(w["start"], a) - a + offset
            e = min(w["end"], b) - a + offset
            out.append({"id": f"w{len(out)}", "text": w["text"].strip(),
                        "start": round(s, 3), "end": round(e, 3)})
        offset += seg_dur
    return out


def phrases(words: list[dict], gap: float = 0.35) -> list[tuple[float, float, str]]:
    res: list[tuple[float, float, str]] = []
    cur: list[dict] = []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] > gap or cur[-1]["text"][-1:] in ".?!"):
            res.append((cur[0]["start"], cur[-1]["end"], " ".join(x["text"] for x in cur)))
            cur = []
        cur.append(w)
    if cur:
        res.append((cur[0]["start"], cur[-1]["end"], " ".join(x["text"] for x in cur)))
    return res


INDEX_TEMPLATE = """<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={w}, height={h}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {w}px; height: {h}px; overflow: hidden; background: #000; }}
      #root {{ width: 100%; height: 100%; position: relative; }}
      #base {{ position: absolute; left: 0; top: 0; width: {w}px; height: {h}px; object-fit: cover; z-index: 1; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{dur}"
         data-width="{w}" data-height="{h}" data-fps="{fps}">
      <!-- Vídeo cortado pelo video-use. Áudio vem daqui. -->
      <video id="base" class="clip" src="assets/video.mp4" data-start="0" data-duration="{dur}"
             data-track-index="0" data-has-audio="true" playsinline></video>

      <!-- OVERLAYS: uma cena por animação, todas com root transparente.
           Exemplo:
      <div id="ov-1" data-composition-id="ov-1" data-composition-src="compositions/ov-1.html"
           data-start="2.1" data-duration="4" data-track-index="1" data-track-kind="graphics"
           data-width="{w}" data-height="{h}" style="z-index: 2"></div>
      -->
    </div>
    <script>
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit_dir", type=Path)
    ap.add_argument("--video", type=Path, default=None, help="corte renderizado (padrão: edit/cortado.mp4)")
    ap.add_argument("--force", action="store_true", help="recria index.html mesmo se já existir")
    args = ap.parse_args()

    edit_dir = args.edit_dir.resolve()
    video = (args.video or edit_dir / "cortado.mp4").resolve()
    edl = json.loads((edit_dir / "edl.json").read_text())
    hf = edit_dir / "hyperframes"

    if not (hf / "hyperframes.json").exists():
        hf.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(HF_BIN), "init", ".", "--skip-skills", "--non-interactive"],
                       cwd=hf, check=True, stdout=subprocess.DEVNULL)
        (hf / "index.html").unlink(missing_ok=True)  # trocamos pelo nosso
    (hf / "assets").mkdir(exist_ok=True)
    (hf / "compositions").mkdir(exist_ok=True)

    info = probe(video)
    print(f"corte: {info['w']}x{info['h']} @ {info['fps']}fps, {info['dur']:.2f}s")

    # keyframe a cada segundo: seek frame-exato no render (overlays.md: GOP > 1 s congela)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-c:v", "libx264", "-preset", "fast", "-crf", "16",
         "-g", str(info["fps"]), "-keyint_min", str(info["fps"]), "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart", str(hf / "assets" / "video.mp4")],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    words = remap_words(edl, edit_dir, segment_durations(edl, edit_dir, info["fps"]))
    (hf / "assets" / "words.json").write_text(json.dumps(words, indent=1, ensure_ascii=False))
    lines = [f"# Transcrição na timeline do vídeo cortado ({info['dur']:.2f}s)", ""]
    lines += [f"[{s:06.2f}-{e:06.2f}] {t}" for s, e, t in phrases(words)]
    (hf / "transcricao_saida.md").write_text("\n".join(lines) + "\n")

    dur = round(info["dur"], 3)
    # o render usa a taxa da fonte (sem isso o HyperFrames renderiza a 30 e repete frames de 24 fps)
    idx = hf / "index.html"
    if idx.exists() and not args.force and "data-fps=" not in idx.read_text():
        idx.write_text(idx.read_text().replace('data-composition-id="main"', f'data-composition-id="main" data-fps="{info["fps"]}"', 1))
    if args.force or not (hf / "index.html").exists():
        (hf / "index.html").write_text(INDEX_TEMPLATE.format(w=info["w"], h=info["h"], dur=dur, fps=info["fps"]))
    if TEMPLATES.exists():
        dst = hf / "modelos"
        shutil.copytree(TEMPLATES, dst, dirs_exist_ok=True)

    print(f"projeto HyperFrames: {hf}")
    print(f"  {len(words)} palavras remapeadas → assets/words.json")
    print(f"  frases → {hf / 'transcricao_saida.md'}")


if __name__ == "__main__":
    main()
