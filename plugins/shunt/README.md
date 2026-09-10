# shunt

A plugin that delegates bulk file reads and boilerplate generation. In Codex,
the lead is Astra at medium effort and the worker is OpenCode
`zai-coding-plan/glm-5.3-flash` at `max`, using the Z.AI Coding Plan.
Claude Code keeps the existing AiKA route and read hooks.

## Codex + OpenCode

Requires Codex, Python 3, and OpenCode with Z.AI Coding Plan authentication
already configured (`opencode auth login`). No Portal instance is needed.

From this repository root:

```bash
codex plugin marketplace add "$PWD"
codex plugin add shunt@portal
plugins/shunt/scripts/codex-shunt -C /path/to/project 'Use shunt for bulk reading and boilerplate generation.'
```

The launcher selects `gpt-6-astra` and `model_reasoning_effort="medium"` for
that session without changing global settings. Start a new thread after plugin
installation. In the Codex app, select Astra / Medium and invoke the installed
bulk-reader or code-writer skill. The skills explicitly select OpenCode; direct
script calls still default to AiKA unless `SHUNT_BACKEND=opencode` is set.

```bash
SHUNT_BACKEND=opencode plugins/shunt/scripts/bulk-read \
  --question 'Explain validation and name its boundary tests.' \
  --paths /path/to/project/src/domain.rs

SHUNT_BACKEND=opencode plugins/shunt/scripts/code-write \
  --spec 'Generate tests matching this reference.' \
  --reference /path/to/project/tests/existing.rs --target /tmp/generated-tests.rs
```

Codex keeps planning, decisions, review, and final verification. OpenCode gets
the selected files through stdin in a fresh temporary working directory, with
external plugins disabled, tool permissions denied, and sharing disabled.
It cannot edit the project itself; `code-write --target` writes its completed
answer. Review a scratch output before applying it to an existing project file.
OpenCode still loads global configuration and stores local sessions, but shunt
does not resume them or copy credentials. Each call consumes subscription quota.
When Codex's sandbox blocks OpenCode's local log/state writes or network access,
use the normal command approval/escalation flow for the script; do not disable
the sandbox globally. Provider/auth/quota errors are returned without retries.

The transport rejects errors, incomplete/empty responses, oversized input, and
responses over 4 MB. `SHUNT_TIMEOUT_SECONDS` bounds each call (default 180);
`SHUNT_MAX_PAYLOAD_BYTES` applies to both transports. Timeout/interruption kills
the worker process group. There is no automatic fallback to AiKA or another model.

Codex delegation is skill-driven; the bundled Read/Bash hooks are Claude Code
hooks, not Codex enforcement. The token-savings figures below measure AiKA,
not GLM. Verify worker claims against source before relying on them.

Model/effort options follow the [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
and [OpenCode CLI](https://opencode.ai/docs/cli/). OpenCode's installed catalog
must expose `zai-coding-plan/glm-5.3-flash` with the `max` variant.

## Claude Code + AiKA: how it works

Three layers, from hard gate to soft suggestion:

1. **Hooks** block Claude from reading large files and redirect to the bulk-reader skill
2. **Scripts** handle the AiKA invocation and output cleanup
3. **Skills** tell Claude when and how to call the scripts

Claude never assembles bash pipelines from prose. It calls a script with named arguments. The scripts handle everything internally.

Delegation goes through the Portal CLI actions registry — one `aika:invoke-chat` call per delegation — so the plugin works against any Portal instance with AiKA enabled. Modes are addressed by name and resolved server-side: case-insensitive, preferring your own mode, then your groups', then public ones; a name matching nothing or several modes equally fails with the candidate ids.

## Prerequisites

- [`jq`](https://jqlang.org) — `brew install jq`
- The **portal** plugin from this marketplace, which provides the Portal CLI that shunt delegates through:

```bash
claude plugin install portal@portal
```

Then, in a new session, set up and authenticate the CLI against your Portal instance:

```text
/portal:setup
```

Check whether the two AiKA modes (`bulk-reader` and `code-writer`) already exist on your instance — many instances ship them as public modes:

```bash
portal-cli actions aika:list-modes --json --input '{"search": "bulk-reader"}'
```

If they exist, no mode creation is needed — just install the plugin and go. If not, or to create your own customized versions (e.g. different model or instructions):

```bash
portal-cli actions aika:create-mode --input '{
  "name": "bulk-reader",
  "description": "Bulk file reader for code analysis",
  "instructions": "You are a precise code analyst. Read the provided files and answer the question concisely. Output structured bullets only. No greetings, no prose, no preambles, no summaries. Lead every bullet with the exact name, type, or line number. Use nested bullets for details. Skip anything the caller did not ask for.",
  "tags": ["coding", "delegation"],
  "resource_limits": { "temperature": 0.2 }
}'

portal-cli actions aika:create-mode --input '{
  "name": "code-writer",
  "description": "Boilerplate code generator",
  "instructions": "You generate code files based on a spec and reference files. Match the existing patterns, conventions, naming, and style exactly. Output only the code — no explanations, no markdown fences unless asked. If the spec is ambiguous, make reasonable choices that match the patterns in the reference code.",
  "tags": ["coding", "delegation"],
  "resource_limits": { "temperature": 0.2 }
}'
```

A mode you create is private and owned by you, and name resolution prefers your own modes — so your customized `bulk-reader` automatically shadows the public one, no configuration needed.

## Plugin structure

```
shunt/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest (name, description, version)
├── hooks/
│   ├── hooks.json           # Hook registration (PreToolUse matchers)
│   ├── check-file-size      # Blocks Read on files > 350 lines
│   └── check-bash-read      # Blocks cat/head/tail on large files
├── scripts/
│   ├── lib/
│   │   └── aika.sh          # Shared aika:invoke-chat plumbing
│   ├── bulk-read            # Invokes the bulk-reader mode
│   └── code-write           # Invokes the code-writer mode
├── skills/
│   ├── bulk-reader/
│   │   └── SKILL.md         # When/how to call bulk-read
│   └── code-writer/
│       └── SKILL.md         # When/how to call code-write
└── evals/
    ├── run.sh                # Runs hook + transport evals
    ├── opencode-evals.py     # OpenCode routing, errors, timeout, target preservation
    ├── hook-evals.json       # Read hook test cases (17)
    ├── bash-hook-evals.json  # Bash hook test cases (17)
    ├── transport-evals.sh    # scripts/lib/aika.sh against a stubbed CLI (17)
    ├── evals.json            # End-to-end skill test cases (3)
    ├── benchmarks.json       # Token savings scenarios (4)
    └── fixtures/             # Test fixture files
```

## Scripts

### bulk-read

Delegates file reading to AiKA. Files are wrapped in XML tags (`<file path="...">`) for clear boundaries.

```bash
bulk-read --question "What does this service do?" --paths src/Service.java src/Handler.java

# Follow-up: ask again with the same paths
bulk-read --question "Which methods call the database?" --paths src/Service.java src/Handler.java
```

### code-write

Delegates boilerplate generation to AiKA. Strips markdown fences from output. Can write directly to disk via `--target`. `--reference` is required — without a file to match patterns against, the worker would generate context-free code that fits nothing in the project.

```bash
# Generate and write to file
code-write --spec "Write tests for UserService" --reference tests/OrderTest.java --target tests/UserTest.java

# Build on what was just generated by referencing it
code-write --spec "Now add edge case tests" --reference tests/UserTest.java --target tests/UserEdgeCases.java

# Output to stdout
code-write --spec "Generate a config stub" --reference config/existing.yaml
```

### One shot per call

`aika:invoke-chat` is ephemeral: nothing is stored server-side, and the action's own follow-up
mechanism is for the caller to replay prior turns. Replaying a file corpus is the exact cost this
plugin exists to avoid, so shunt does not do it — every call stands alone. Re-sending files is
free where it matters, because the corpus goes to the worker model and never enters Claude's
context.

## Hooks

### check-file-size (Read hook)

Fires on every `Read` tool call. Blocks full-file reads on files exceeding `MIN_LINES` (default: 350, configurable via `SHUNT_MIN_LINES` env var). Allows through:
- Targeted reads (offset or limit set)
- Files under the threshold
- Nonexistent files (let Read handle the error)

### check-bash-read (Bash hook)

Fires on every `Bash` tool call. Catches `cat`, `head`, `tail`, `less`, `more` on large files. Allows through:
- Piped commands (`cat file | grep`) — targeted reads
- Redirections (`cat file > out`) — not reading into context
- Commands with flags that indicate targeted reads
- Non-read commands (`git status`, `grep`, etc.)

## Configuration

All settings are environment variables — for Claude Code, add them to the `env` block in `.claude/settings.json`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `SHUNT_BACKEND` | `aika` | `opencode` selects GLM-5.3-Flash/max on the Z.AI Coding Plan |
| `SHUNT_MIN_LINES` | `350` | Line count above which the Read hook blocks and redirects |
| `SHUNT_PORTAL_INSTANCE` | CLI default | Portal instance name or URL to invoke against |
| `PORTAL_CLI_BIN` | `portal-cli`, else `npx` | Override how portal-cli is launched |
| `SHUNT_MAX_PAYLOAD_BYTES` | `400000` (`120000` on Linux) | Request ceiling, since input travels through argv |
| `SHUNT_TIMEOUT_SECONDS` | `180` | Timeout for one action invocation |
| `SHUNT_BULK_READER_MODE_ID` | — | Pin a specific mode id if the name is ambiguous |
| `SHUNT_CODE_WRITER_MODE_ID` | — | Pin a specific mode id if the name is ambiguous |

## What doesn't get delegated

The plugin is designed to know when NOT to delegate:
- **Debugging** — requires Claude's reasoning, not a summary
- **Editing** — Claude needs exact content in context; use targeted reads (offset/limit)
- **Small files** — delegation overhead exceeds savings under 350 lines
- **Architectural decisions** — judgment calls stay on Claude

## Evals

```bash
# Hook routing + transport plumbing — needs no Portal access
bash evals/run.sh

# Also re-measure token savings against the real modes — needs portal-cli auth
bash evals/run.sh --benchmark
```

## Benchmarks

Tested against a 162K-line Java monorepo:

| Scenario | Lines | Without shunt | With shunt | Savings |
|----------|-------|--------------|------------|---------|
| Single large file | 4,014 | 33,684 tokens | 5,737 tokens | 82% |
| Source + test pair | 7,408 | 75,990 tokens | 4,148 tokens | 94% |
| Multi-file cross-service | 1,281 | 16,221 tokens | 821 tokens | 94% |
| Code-write | 3,667 | 40,614 tokens + generation | 833 lines to disk | - |

Mean bulk-read savings: **90%**

## Known limitations

- **No enforcement for code-writer** — only bulk-reader has hook enforcement. Code-writer relies on Claude recognizing when to use it via the skill description.
- **Request size** — `aika:invoke-chat` input is passed on the command line, so a request must fit in `ARG_MAX` (1 MB on macOS, shared with the environment; Linux additionally caps a single argument at 128 KiB). shunt refuses anything over `SHUNT_MAX_PAYLOAD_BYTES` with a clear error rather than failing with `E2BIG`. Split into smaller batches.
- **Invocation timeout** — shunt caps one action invocation at `SHUNT_TIMEOUT_SECONDS` (default 180). Very large generations can exceed it; raise the timeout or split the spec into smaller calls.
