---
name: bulk-reader
description: "Delegate bulk file reading to OpenCode GLM in Codex, or AiKA in Claude Code. Use when you need to read files >350 lines, answer questions across 3+ files, or summarize large diffs."
---

In **Codex**, use OpenCode with `zai-coding-plan/glm-5.3-flash` at `max`.
Resolve `SHUNT_ROOT` as the absolute plugin root, two directories above this
skill directory. Keep planning, decisions, and verification in Codex; the worker
receives only the selected files and cannot use tools.

```bash
SHUNT_BACKEND=opencode "${SHUNT_ROOT}/scripts/bulk-read" --question "<question>" --paths <file1> [<file2> ...]
```

OpenCode needs network access and its own local log/state directories. If the
host sandbox blocks those (for example `FileSystem.open (.../opencode.log)`),
retry the same script through the host's normal command-escalation flow. Keep
the selected files and question unchanged. Do not disable the sandbox globally
or substitute another model. Report provider/auth/quota errors without retries.

In **Claude Code**, keep the existing AiKA route:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/bulk-read --question "<question>" --paths <file1> [<file2> ...]
```

Each call is independent. To ask a follow-up, ask again with the same `--paths` — the files
go to the worker, not into your context. Re-sending them still consumes worker
quota. OpenCode stores a local session but shunt never resumes it.

Verify specific line numbers or exact values before using them in edits.
