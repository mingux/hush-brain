# HUSH BRAIN

```
  _   _  _   _  ___  _  _    ___  ___    _    ___  _  _
 | |_| || | | |/ __|| || |  | _ )| _ \  /_\  |_ _|| \| |
 |  _  || |_| |\__ \|  _  | | _ \|   / / _ \  | | | .` |
 |_| |_| \___/ |___/|_||_|  |___/|_|_\/_/ \_\|___||_|\_|
```

**Local-first AI agent orchestrator & monitor with a persistent markdown brain.**
Styled after the Matrix. Runs entirely on your machine — no API key required.

One process gives you:

- 🕶️ **The Construct** — a Matrix-styled dashboard (digital rain included) streaming every agent event live over WebSocket
- 🤖 **The Orchestrator** — spawns and supervises agents in three modes: on-demand, scheduled, continuous
- 🧠 **The Brain** — a plain-markdown memory vault with two-tier recall (`hot.md` → `index.md` → memory pages), citations included
- 🔌 **The Bridge** — an HTTP endpoint that ingests [Claude Code](https://claude.com/claude-code) hook events, so your coding agents show up in the same monitor

## Quickstart

```bash
git clone https://github.com/mingux/hush-brain
cd hush-brain
uv run hush serve
```

Open **http://localhost:8199** and jack in.

No `uv`? `pip install -e . && hush serve` works too.
On Windows you can also just double-click `start.bat`.

To get a global `hush` command usable from any folder:

```bash
uv tool install .
hush serve
```

### Troubleshooting

- **`error: Failed to spawn: hush — program not found`** — you ran `uv run hush serve` outside the repo folder. Either `cd` into it first, run `uv run --project <path-to-hush-brain> hush serve`, or install globally with `uv tool install <path-to-hush-brain>`.
- **Port already in use** — something else is on 8199; run `hush serve --port 8200`.
- **Blank page / no rain** — hard-refresh (Ctrl+F5); the dashboard is served from `/static`.

## Providers (local-first)

Hush Brain picks the best available LLM automatically and degrades gracefully:

| Priority | Provider | When |
|---|---|---|
| 1 | `HUSH_PROVIDER` env | explicit override: `echo`, `ollama`, `anthropic` |
| 2 | **Anthropic** | `ANTHROPIC_API_KEY` is set (default model `claude-opus-4-8`) |
| 3 | **Ollama** | reachable at `localhost:11434` (default model `llama3.1:8b`) |
| 4 | **Echo** | deterministic offline stub — the demo always works |

Config knobs: `HUSH_OLLAMA_URL`, `HUSH_OLLAMA_MODEL`, `HUSH_ANTHROPIC_MODEL`, `HUSH_HOME` (data dir, default `~/.hush-brain`).

## The programs (built-in agents)

| Agent | Mode | What it does |
|---|---|---|
| **Oracle** | on-demand | Answers a question grounded in the brain, citing `[[memories]]` |
| **Seeker** | on-demand | Multi-round research loop; writes each finding into the brain |
| **Sentinel** | continuous | Watches a directory; reports anomalies (file changes) to the feed |
| **Architect** | on-demand | Decomposes a goal into subtasks and dispatches Oracles/Seekers |

Spawn from the dashboard, the API, or the CLI:

```bash
hush ask "what do you know about the red pill?"
hush remember "Deploy ritual" "Always run the smoke tests before shipping."
hush recall "deploy"
```

## The brain

Plain markdown, zero lock-in (inspired by [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian)):

```
~/.hush-brain/brain/
├── hot.md        # rolling recent-context cache (~500 words)
├── index.md      # master catalog — one line per memory
└── memories/     # one fact per file, with frontmatter
```

Recall reads hot → index → targeted pages, and answers cite `[[slug]]` so every claim is traceable.

## Claude Code bridge

Add a hook to your Claude Code `settings.json` and your coding sessions appear in the feed:

```json
{
  "hooks": {
    "PostToolUse": [{
      "hooks": [{
        "type": "command",
        "command": "curl -s -X POST http://localhost:8199/api/hooks/claude -H \"Content-Type: application/json\" -d @-"
      }]
    }]
  }
}
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | provider, event count, token totals, brain stats |
| GET/POST | `/api/agents` | list / spawn agents (`{"kind": "oracle", "params": {"question": "..."}}`) |
| POST | `/api/agents/{id}/stop` | stop a running agent |
| GET | `/api/events?limit&agent&kind` | query the event log (SQLite) |
| GET | `/api/brain/recall?q=` | search the brain |
| POST | `/api/brain/remember` | write a memory |
| POST | `/api/hooks/claude` | ingest Claude Code hook events |
| WS | `/ws` | live event stream (snapshot + events) |

## Development

```bash
uv sync
uv run pytest
```

## Lineage

Built by absorbing the best ideas from:
[OpenJarvis](https://github.com/open-jarvis/OpenJarvis) (local-first agent modes, provider fallback) ·
[claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) (markdown brain, two-tier index, citation grounding) ·
[Octogent](https://github.com/hesamsheikh/octogent) (Claude Code hooks → live monitor) ·
[Mission Control](https://github.com/builderz-labs/mission-control) (SQLite-only persistence, activity feed, token tracking).

## License

MIT. *There is no spoon.*
