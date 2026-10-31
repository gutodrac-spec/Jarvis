#!/usr/bin/env bash
# Sobe o servidor e o agente (roda toda vez que o Codespace liga)
cd "$(dirname "$0")/.."
mkdir -p server/data
if [ -z "$JARVIS_TOKEN" ]; then
  [ -s server/data/token ] || (head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24 > server/data/token)
  export JARVIS_TOKEN="$(cat server/data/token)"
fi

pkill -f "node server.js" 2>/dev/null
pkill -f "jarvis_agent.py" 2>/dev/null
(cd server && nohup node server.js > /tmp/jarvis-server.log 2>&1 &)
sleep 2
# Agente de demonstração: controla o DESKTOP VIRTUAL do Codespace (porta 6080).
# Para controlar o seu PC de verdade, rode o agente no PC (veja o README).
(cd agent && DISPLAY="${DISPLAY:-:1}" JARVIS_SERVER="ws://localhost:8787/ws" nohup python jarvis_agent.py > /tmp/jarvis-agent.log 2>&1 &)

# deixa a porta pública para o celular e o PC conseguirem acessar (o token protege)
gh codespace ports visibility 8787:public -c "$CODESPACE_NAME" >/dev/null 2>&1 || true

if [ -n "$CODESPACE_NAME" ]; then
  BASE="https://${CODESPACE_NAME}-8787.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  DESK="https://${CODESPACE_NAME}-6080.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
else
  BASE="http://localhost:8787"; DESK="http://localhost:6080"
fi
WSS="${BASE/https:/wss:}/ws"
cat > JARVIS-LINK.txt <<TXT
==================== J.A.R.V.I.S. ====================

📱 ABRA NO CELULAR (já entra com o token):
$BASE/#token=$JARVIS_TOKEN

Token: $JARVIS_TOKEN

🖥️ Desktop virtual que o Jarvis controla aqui no Codespace (senha: jarvis):
$DESK

💻 Para o Jarvis controlar o SEU PC, no PC rode o agente com:
   JARVIS_SERVER=$WSS
   JARVIS_TOKEN=$JARVIS_TOKEN

Logs: tail -f /tmp/jarvis-server.log /tmp/jarvis-agent.log
======================================================
TXT
cat JARVIS-LINK.txt
