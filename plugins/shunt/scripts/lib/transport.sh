#!/bin/bash
# Keep AiKA as the direct-call default; Codex skills preserve worker selection.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/aika.sh"

case "${SHUNT_BACKEND:-aika}" in
  aika) ;;
  opencode|codex)
    SHUNT_WORKER_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/worker.py"
    shunt_preflight() {
      command -v python3 >/dev/null && command -v "$SHUNT_BACKEND" >/dev/null || {
        echo "Error: $SHUNT_BACKEND delegation requires python3 and $SHUNT_BACKEND." >&2
        return 1
      }
    }
    shunt_cancel_worker() {
      trap '' INT TERM
      local pid="${SHUNT_WORKER_PID:-$!}"
      if [ -n "$pid" ]; then
        kill -TERM "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
      fi
      exit "$1"
    }
    shunt_invoke() {
      local SHUNT_WORKER_PID="" rc
      trap 'shunt_cancel_worker 130' INT
      trap 'shunt_cancel_worker 143' TERM
      # Waiting on a background child lets Bash handle a shell-only signal
      # immediately, forward it to Python, and wait for worker-tree cleanup.
      python3 "$SHUNT_WORKER_SCRIPT" "$SHUNT_BACKEND" "$1" "$2" &
      SHUNT_WORKER_PID=$!
      wait "$SHUNT_WORKER_PID"
      rc=$?
      trap - INT TERM
      return "$rc"
    }
    ;;
  *) echo "Error: SHUNT_BACKEND must be aika, opencode, or codex." >&2; exit 1 ;;
esac
