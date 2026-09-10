---
name: code-writer
description: "Delegate boilerplate code generation to OpenCode GLM in Codex, or AiKA in Claude Code. Use for tests, config, docstrings, type stubs, or any generation where >80% is predictable from reference files."
---

In **Codex**, use OpenCode with `zai-coding-plan/glm-5.3-flash` at `max`.
Resolve `SHUNT_ROOT` as the absolute plugin root, two directories above this
skill directory. Keep planning, decisions, and review in Codex. The worker has
no tools; the script writes the returned code only when `--target` is supplied.
Use a new scratch target first, review the result, then apply it to the project.

```bash
SHUNT_BACKEND=opencode "${SHUNT_ROOT}/scripts/code-write" --spec "<what to generate>" --reference <reference-file> --target <scratch-output-path>
```

OpenCode needs network access and its own local log/state directories. If the
host sandbox blocks those (for example `FileSystem.open (.../opencode.log)`),
retry the same script through the host's normal command-escalation flow. Keep
the spec, reference, and scratch target unchanged. Do not disable the sandbox
globally or substitute another model. Report provider/auth/quota errors without retries.

In **Claude Code**, keep the existing AiKA route:

```bash
# Generate and write directly to target file
${CLAUDE_PLUGIN_ROOT}/scripts/code-write --spec "<what to generate>" --reference <reference-file> --target <output-path>

# Output to stdout instead (omit --target)
${CLAUDE_PLUGIN_ROOT}/scripts/code-write --spec "<what to generate>" --reference <reference-file>
```

Each call is independent. To build on what was just generated, pass that file as the
`--reference` for the next call.

Review the output, make the necessary edits, and run the relevant checks before
accepting the generated code. Do not treat worker output as verified evidence.
