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
    shunt_invoke() {
      python3 "$SHUNT_OPENCODE_SCRIPT" "$1" "$2"
    }
    ;;
  *) echo "Error: SHUNT_BACKEND must be aika or opencode." >&2; exit 1 ;;
esac
