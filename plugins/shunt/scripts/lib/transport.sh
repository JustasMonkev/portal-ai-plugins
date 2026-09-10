#!/bin/bash
# Keep AiKA as the default; Codex skills explicitly select OpenCode.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/aika.sh"

case "${SHUNT_BACKEND:-aika}" in
  aika) ;;
  opencode)
    SHUNT_OPENCODE_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/opencode.py"
    shunt_preflight() {
      command -v python3 >/dev/null && command -v opencode >/dev/null || {
        echo "Error: OpenCode delegation requires python3 and opencode." >&2
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
      python3 "$SHUNT_OPENCODE_SCRIPT" "$1" "$2" &
      SHUNT_WORKER_PID=$!
      wait "$SHUNT_WORKER_PID"
      rc=$?
      trap - INT TERM
      return "$rc"
    }
    ;;
  *) echo "Error: SHUNT_BACKEND must be aika or opencode." >&2; exit 1 ;;
esac
