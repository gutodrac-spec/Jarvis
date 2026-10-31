#!/usr/bin/env bash
# Sobe o bot em segundo plano quando o Codespace liga.
cd "$(dirname "$0")"
pkill -f "python duet.py" 2>/dev/null || true
setsid nohup python duet.py > /tmp/duet.log 2>&1 < /dev/null &
echo "Duet iniciado (log em /tmp/duet.log)"
