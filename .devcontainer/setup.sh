#!/usr/bin/env bash
# Instala tudo (roda uma vez, quando o Codespace é criado)
set -e
cd "$(dirname "$0")/.."
(cd server && npm install --no-fund --no-audit)
sudo apt-get update -y && sudo apt-get install -y --no-install-recommends xclip scrot firefox-esr || true
pip install --no-cache-dir -r agent/requirements.txt
npm install -g @anthropic-ai/claude-code
