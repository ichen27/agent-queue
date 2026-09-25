#!/usr/bin/env bash
# Foreground lifecycle: only processes started by this invocation are stopped.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"
if [ ! -x .venv/bin/python ] || [ ! -f dashboard/dist/index.html ]; then
  echo "Run the setup steps in README.md first." >&2
  exit 1
fi
export AGENT_QUEUE_STATE="${AGENT_QUEUE_STATE:-$DIR/.agent-queue/state.json}"
export AGENT_QUEUE_MONITOR_URL="ws://127.0.0.1:7890/ws/monitor"
# Refuse an occupied port before launching either process.
.venv/bin/python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 7890)); s.close()'
server_pid=""
monitor_pid=""
cleanup() {
  [ -z "$monitor_pid" ] || kill "$monitor_pid" 2>/dev/null || true
  [ -z "$server_pid" ] || kill "$server_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM
.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 7890 &
server_pid=$!
ready=0
for attempt in {1..30}; do
  kill -0 "$server_pid" 2>/dev/null || { echo "Backend failed to start." >&2; exit 1; }
  if .venv/bin/python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:7890/api/health", timeout=1)' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.2
done
[ "$ready" -eq 1 ] || { echo "Backend did not become ready." >&2; exit 1; }
kill -0 "$server_pid"
.venv/bin/python monitor/claude_monitor.py &
monitor_pid=$!
echo "Agent Queue: http://127.0.0.1:7890 — Ctrl-C stops both processes."
# Exit if either process dies instead of leaving an unnoticed half-running service.
while kill -0 "$server_pid" 2>/dev/null && kill -0 "$monitor_pid" 2>/dev/null; do sleep 1; done
exit 1
