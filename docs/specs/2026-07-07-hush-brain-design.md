# Hush Brain — Design Spec

**Date:** 2026-07-07
**Status:** v0.1 scope, approved for autonomous build (user directive: "absorb this info, dig deep for other high reviewed examples, and build it")

## What it is

Hush Brain is a **local-first AI agent orchestrator and monitor with a persistent markdown "brain"**, wrapped in a Matrix-movie aesthetic. One process gives you:

- an **orchestrator** that spawns and supervises AI agents (on-demand, scheduled, continuous),
- a **monitor** — a real-time dashboard streaming every agent event over WebSocket,
- a **brain** — a plain-markdown memory vault with two-tier recall (hot cache → index → pages),
- a **bridge** — an HTTP endpoint that ingests Claude Code hook events so external coding agents show up in the same monitor.

## Research inputs and what was borrowed

| Source | Borrowed |
|---|---|
| [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) (Stanford Hazy Research) | Local-first via Ollama with cloud fallback; agent execution modes (on-demand / scheduled / continuous); trace logging of every run; preset agents |
| [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) | Markdown-file brain, zero lock-in; two-tier index (`hot.md` ~500-word recent cache + `index.md` master catalog); citation grounding — answers cite memory files |
| [Octogent](https://github.com/hesamsheikh/octogent) (472★) | Claude Code hooks feeding a local API so a dashboard shows more than raw terminal output; WebSocket transport; agent lifecycle states |
| [Mission Control](https://github.com/builderz-labs/mission-control) | Zero-external-dependency SQLite persistence; activity feed filterable by agent/type; token usage tracking per agent |

Also surveyed: RuFlo (claude-flow), Claude Squad, Claude-Code-Agent-Monitor, CrewAI, LangGraph, n8n — these confirmed the common shape (event stream + agent registry + SQLite + web dashboard) but are either too heavy or not local-first.

## Approaches considered

- **A. Python + FastAPI + vanilla-JS dashboard (chosen).** No build step, runs with `uv run`. The user's machine already has uv and a local Ollama (llama3.1:8b), so the default install works fully offline with zero API keys.
- **B. Node/TypeScript + React** (Octogent/Mission Control style). Prettier component model but adds a build pipeline and heavier maintenance for a v0.1.
- **C. Claude Code plugin only** (hooks + skills, no server). Narrower than the request — user asked for an orchestrator *and* monitor *and* brain, not just a CC add-on.

## Architecture

```
hush-brain/
├── src/hush_brain/
│   ├── server.py        # FastAPI app: dashboard, REST API, /ws WebSocket
│   ├── bus.py           # async event bus → SQLite persist + WS broadcast
│   ├── db.py            # SQLite (WAL): events, runs, token metrics
│   ├── orchestrator.py  # agent registry, lifecycle, asyncio supervision
│   ├── providers.py     # LLM providers: Ollama (default), Anthropic, Echo
│   ├── brain.py         # markdown vault: hot.md, index.md, memories/*.md
│   ├── hooks.py         # POST /api/hooks/claude — Claude Code bridge
│   ├── agents.py        # built-in agents (see below)
│   └── cli.py           # `hush` CLI: serve / ask / remember / recall
├── src/hush_brain/static/   # Matrix dashboard (vanilla HTML/CSS/JS)
├── tests/
└── docs/specs/
```

### Agents (Matrix-named, OpenJarvis-mode-inspired)

| Agent | Mode | Role |
|---|---|---|
| **Oracle** | on-demand | Answers questions grounded in the brain, with memory citations |
| **Seeker** | on-demand | Multi-step research loop; writes findings into the brain |
| **Sentinel** | continuous | Watches a directory for changes; reports anomalies to the feed |
| **Architect** | on-demand | Decomposes a goal into subtasks and dispatches them to other agents |

All agents run as asyncio tasks supervised by the orchestrator. Every state change and LLM call emits an event on the bus.

### Brain (memory vault)

- `brain/hot.md` — rolling recent-context cache (capped ~500 words).
- `brain/index.md` — one line per memory: title, path, hook.
- `brain/memories/<slug>.md` — one fact/finding per file with frontmatter.
- Recall = hot → index → targeted pages; answers cite `[[slug]]`.

### Providers

- **Ollama** (default, `llama3.1:8b`) — fully local.
- **Anthropic** — used when `ANTHROPIC_API_KEY` is set.
- **Echo** — deterministic offline stub; powers tests and keyless demo mode.

Provider selection: explicit config > Anthropic if key present > Ollama if reachable > Echo.

### Event model

Single `Event` shape: `{id, ts, agent, kind, payload}` where kind ∈ `agent.spawned|agent.status|agent.output|agent.done|agent.error|brain.write|brain.recall|llm.call|hook.claude`. Persisted to SQLite, broadcast to all WS clients, rendered in the feed.

### Dashboard (the Construct)

Matrix aesthetic, no framework: katakana digital-rain canvas background, phosphor-green-on-black mono type, scanline/glow effects, boot sequence. Panels:

1. **Agents grid** — cards with status pill, mode, tokens, uptime; spawn/stop controls.
2. **The Feed** — live event stream (WS), filterable by agent/kind.
3. **Brain panel** — hot cache preview, memory count, recall query box.
4. **System line** — provider in use, event count, uptime, token totals.

### Error handling

- Agent crash → `agent.error` event, status `failed`; orchestrator never dies with an agent.
- Provider unreachable → graceful degradation down the provider chain, surfaced in the feed.
- WS clients drop → server keeps running; dashboard auto-reconnects with backoff.

### Testing

pytest + httpx against the Echo provider: brain vault round-trip and index integrity, bus persist/broadcast, orchestrator lifecycle (spawn→run→done, crash→failed), REST endpoints, Claude-hook ingestion.

## Out of scope for v0.1 (YAGNI)

PTY terminal embedding, git worktree isolation, RBAC/auth, cron natural-language scheduling, cost dashboards beyond token counts, skill marketplaces, vector embeddings.

## Deliverable

Public GitHub repo `mingux/hush-brain`, MIT license, README with quickstart (`uvx`/`uv run hush serve`), this spec committed.
