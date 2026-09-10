# Spotify Portal AI Plugins

Bring [Spotify Portal](https://portal.spotify.com) into Claude Code, Codex, and Cursor.

This plugin provides focused workflows for the
[Portal CLI](https://www.npmjs.com/package/@spotify/portal-cli): set up
authentication, search your software catalog, build service briefings, run
diagnostics, and invoke Portal actions.

## Highlights

- Set up the Portal CLI for your current coding-agent environment.
- Run read-only diagnostics to verify plugin, CLI, authentication, and action readiness.
- Search the software catalog and technical documentation using natural language queries.
- Generate concise service briefings with available ownership, health, incident, and documentation details.
- Discover and safely invoke Portal actions with built-in help, dry-run, and confirmation safeguards.

## Choose a plugin

| Plugin | Use it for | Hosts | Requirements |
| --- | --- | --- | --- |
| **portal** | Catalog search, service briefings, diagnostics, and Portal actions | Claude Code, Codex, Cursor | Portal CLI and access to a Portal instance |
| **shunt** | Delegating bulk reads and predictable code generation | Codex, Claude Code | Codex: OpenCode + Z.AI Coding Plan; Claude Code: Portal + AiKA |

The plugins have separate jobs. **portal** connects your coding agent to Spotify
Portal. **shunt** delegates selected work to a worker model while the main agent
keeps planning, decisions, and review. Shunt's Codex/OpenCode route does **not**
require a Portal account or installation of the portal plugin.

## Installation

### Claude Code

```bash
claude plugin marketplace add spotify/portal-ai-plugins
claude plugin install portal@portal
claude plugin install shunt@portal   # optional: token-saving AiKA delegation
```

Start a new session and run:

```text
/portal:setup
```

### Codex

```bash
codex plugin marketplace add spotify/portal-ai-plugins
codex
```

Open `/plugins`, install Spotify Portal, start a new task, and ask:

```text
Set up Spotify Portal for me.
```

### Cursor

Register the [spotify/portal-ai-plugins](https://github.com/spotify/portal-ai-plugins)
repository in your Cursor team marketplace, then install Spotify Portal from
**Cursor Settings → Plugins**.

## Workflows

### Portal workflows

| Workflow | Purpose |
| --- | --- |
| `setup` | Configure Portal CLI authentication |
| `doctor` | Run read-only readiness diagnostics |
| `search` | Search the software catalog and technical documentation |
| `service` | Produce a concise operational service briefing |
| `actions` | Discover, inspect, preview, and safely invoke Portal actions |
| `feedback` | Submit feedback about the Portal CLI to the Portal team |

### Shunt workflows

| Workflow | Delegate | Keep with the lead |
| --- | --- | --- |
| `bulk-reader` | Summarize large files or answer a focused question across selected files | Verify exact values and source references before making changes |
| `code-writer` | Generate tests, configuration, or boilerplate from an existing reference | Review the generated file, apply changes, and run checks |

With Codex, shunt uses **Astra / medium** as the lead through its launcher and
**OpenCode GLM-5.3-Flash / max** as the worker. With Claude Code, it keeps the
existing AiKA route. OpenCode is a one-shot reader/generator here, not an
autonomous editor with access to your entire project.

## Quick start: Codex with an OpenCode worker

Use a local checkout containing the Codex shunt implementation. The commands
below run from the repository root; installation of the upstream Portal plugin
alone does not install shunt.

### 1. Check OpenCode authentication and the model

Install Codex, OpenCode, and Python 3 first. Then check your existing setup:

```bash
codex --version
opencode --version
python3 --version
opencode auth list
opencode models zai-coding-plan --verbose
```

The catalog must include `zai-coding-plan/glm-5.3-flash` with a `max` variant.
If Z.AI Coding Plan is not authenticated, run `opencode auth login` and select
that provider. Shunt uses OpenCode's existing credentials and subscription;
you do not put a key in this repository.

### 2. Install shunt and start the lead

```bash
codex plugin marketplace add "$PWD"
codex plugin add shunt@portal

plugins/shunt/scripts/codex-shunt -C /absolute/path/to/your/project \
  'Use shunt for bulk reading and boilerplate generation. Verify worker output before applying changes.'
```

Replace the project path with your own. The launcher selects `gpt-6-astra` at
`medium` effort for that session; it does not rewrite your global Codex settings.
Start a new session after installation so Codex discovers the skills.

For the **Codex app**, open your project in a new thread, select **Astra / Medium**,
and ask: **“Use shunt to explain this module, then verify the worker's summary.”**
Installing shunt does not change the model in an already-running thread.

### 3. Try a read-only delegation

From this repository root, select a source file in your project:

```bash
SHUNT_BACKEND=opencode plugins/shunt/scripts/bulk-read \
  --question 'Explain this module in four bullets and cite its key functions.' \
  --paths /absolute/path/to/your/project/src/example.rs
```

The answer goes to stdout. A successful call reports the worker model, `max`
variant, and local session ID on stderr. This call consumes Z.AI subscription
quota but does not edit the selected file. Direct script calls need
`SHUNT_BACKEND=opencode`; the Codex skills set it explicitly.

See the [shunt guide](plugins/shunt/README.md) for code-generation examples,
the delegation flow, configuration, and troubleshooting. Claude Code users can
follow the [AiKA setup](plugins/shunt/README.md#claude-code--aika-how-it-works).

## Portal CLI

The workflows invoke the upstream CLI through `npx`. To inspect its commands:

```bash
npx @spotify/portal-cli --help
```

Setup verifies the required `auth`, `actions`, `owner`, `search`, and `service`
commands before proceeding.
