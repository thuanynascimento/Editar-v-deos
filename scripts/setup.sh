#!/usr/bin/env bash
# Instala tudo que o pipeline precisa. Idempotente.
set -euo pipefail
cd "$(dirname "$0")/.."
git submodule update --init --recursive
pip install -q -r requirements.txt
npm ci --no-audit --no-fund
npx --no-install hyperframes telemetry disable >/dev/null 2>&1 || true
command -v ffmpeg >/dev/null || { echo "ffmpeg não encontrado"; exit 1; }
echo "setup ok"
