# Hush Brain — The Operator's Guide

> *"Unfortunately, no one can be told what the Matrix is. You have to see it for yourself."*
> This guide is the next best thing.

- [1. What Hush Brain is (mental model)](#1-what-hush-brain-is-mental-model)
- [2. Getting in](#2-getting-in)
- [3. The dashboard, panel by panel](#3-the-dashboard-panel-by-panel)
- [4. The programs (agents) and when to use each](#4-the-programs-agents-and-when-to-use-each)
- [5. The brain: building a memory that compounds](#5-the-brain-building-a-memory-that-compounds)
- [6. The Claude Code bridge](#6-the-claude-code-bridge)
- [7. The CLI](#7-the-cli)
- [8. The API (build your own programs)](#8-the-api-build-your-own-programs)
- [9. Playbooks: what to actually use this for](#9-playbooks-what-to-actually-use-this-for)
- [10. How it compares to similar tools](#10-how-it-compares-to-similar-tools)
- [11. Known gaps & roadmap](#11-known-gaps--roadmap)

---

## 1. What Hush Brain is (mental model)

Hush Brain is **three tools sharing one event stream**:

```
                    ┌─────────────────────────────┐
   spawn/stop ────► │        ORCHESTRATOR         │
                    │  oracle seeker sentinel     │
                    │  architect                  │
                    └──────────┬──────────────────┘
                               │ every action = an event
   Claude Code hooks ────────► │
                    ┌──────────▼──────────────────┐
                    │   EVENT BUS  (SQLite + WS)  │ ────► dashboard feed
                    └──────────┬──────────────────┘
                               │ agents read & write
                    ┌──────────▼──────────────────┐
                    │   BRAIN  (markdown vault)   │
                    │  hot.md → index.md → pages  │
                    └─────────────────────────────┘
```

- The **orchestrator** runs small autonomous programs (agents).
- The **event bus** records everything anything does — agent lifecycles, LLM calls with token counts, memory writes, and events pushed in from outside (Claude Code).
- The **brain** is where knowledge accumulates as plain markdown you own forever.

The core loop that makes it compound: **agents write what they learn into the brain, and every later agent answers grounded in it, with citations.** The more you feed it, the smarter your Oracle gets — without any model training, vector DB, or cloud service.

Everything is local. If Ollama is installed, inference is local too. Nothing leaves your machine.

## 2. Getting in

```bash
git clone https://github.com/mingux/hush-brain
cd hush-brain
uv run hush serve          # or: uv tool install .  →  `hush serve` from anywhere
```

Open **http://localhost:8199**. You'll see the boot sequence, then the Construct. The header tells you three things at a glance:

- **provider** — which LLM you're on (`anthropic:*`, `ollama:*`, or `echo`)
- **link** — `JACKED IN` means the live WebSocket feed is connected
- **tokens** — cumulative LLM tokens spent this database's lifetime

Provider selection is automatic: `ANTHROPIC_API_KEY` set → Anthropic; else Ollama at `localhost:11434` → local model; else the deterministic `echo` stub (everything still works, answers are canned). Force one with `HUSH_PROVIDER=ollama|anthropic|echo`.

Data lives in `~/.hush-brain/` (override with `HUSH_HOME` or `--data-dir`): `hush.db` is the event log, `brain/` is your vault. **Back up `brain/` — that's the part that appreciates in value.** Delete `hush.db` any time to reset the feed.

## 3. The dashboard, panel by panel

**› PROGRAMS (left)** — spawn agents and watch their lifecycle. Pick a kind, type its argument, hit SPAWN. Each card shows status (`running` pulses, `done`, `failed` with the error, `stopped`), mode, and per-agent token spend. Continuous agents (Sentinel) get a `stop` button.

**› THE FEED (center)** — the event stream, newest first. Color coding: green edge = agent output, amber = brain activity, red = errors, cyan = Claude Code hook events. The filter box matches agent names *and* event kinds — type `oracle-1` to follow one agent, `llm.call` to audit every model call, `brain.` to watch memory activity, `hook` to see only Claude Code traffic.

**› THE BRAIN (right)** — memory count, the hot cache (your most recent context at a glance), a recall search box, and a remember form for writing memories by hand.

## 4. The programs (agents) and when to use each

### Oracle — `on-demand` — *ask the brain*

Recalls relevant memories, sends them plus your question to the LLM, and answers **citing `[[slugs]]`** so you can verify every claim. Recall happens even before the LLM call, so you see `brain.recall` → `llm.call` → `agent.output` in the feed.

Use when: you want an answer grounded in *your* accumulated knowledge, not the model's general training. "What did I decide about X?", "How does my deploy process work?", "What do I know about this client?"

### Seeker — `on-demand` — *grow the brain*

Runs N rounds (param `rounds`, 1–5); each round asks the LLM for one *new* insight on the topic (fed the previous rounds so it doesn't repeat), and writes it into the brain as a memory. This is the cheapest way to seed the vault on a subject.

Use when: starting a new topic ("competitor analysis for X"), brainstorming ("failure modes of my backup strategy"), or pre-loading context before a working session.

### Sentinel — `continuous` — *watch something*

Snapshots a directory tree (param `path`, poll every `interval` seconds), and reports added/modified/removed files to the feed. Runs until you stop it. Skips `.git`, `node_modules`, `__pycache__`, virtualenvs.

Use when: you've let a coding agent loose on a repo and want an independent record of what it touched; watching a downloads/inbox folder; keeping an eye on a build output directory.

### Scheduling any on-demand agent — *new in v0.2*

Add `every` to any oracle/seeker/architect spawn (`45s`, `30m`, `2h`, `1d`, or seconds) and it becomes a **scheduled** agent: run → sleep → run again until stopped. The card shows the cycle count and next run time; the feed logs a `sleeping` status between cycles. A Seeker on `every: 1d` is a morning digest that feeds your brain while you sleep.

### Architect — `on-demand` — *delegate*

Asks the LLM to decompose a goal into up to 3 subtasks, then spawns Oracles/Seekers for them. Watch the fan-out live in the feed. If the plan doesn't parse, it falls back to a single Oracle.

Use when: the task is bigger than one question. "Prepare me for the Playproof investor call" → it might spawn a Seeker on pitch objections and Oracles over what the brain already knows.

## 5. The brain: building a memory that compounds

The vault structure (all plain markdown, Obsidian-compatible — you can literally open `~/.hush-brain/brain` as an Obsidian vault):

```
brain/
├── hot.md      # rolling cache of the ~500 most recent words of context
├── index.md    # one line per memory: [[slug]] — title — hook
└── memories/   # one fact per file, YAML frontmatter + body
```

Recall is two-tier: hot cache first (recency), then a scored search across titles (weighted 3×) and bodies. No embeddings, no database — grep-able, diff-able, yours.

**Habits that make it work** (borrowed from how people run Obsidian + Claude Code second brains):

- **Capture at decision time.** Made a choice? `hush remember "Chose FastAPI over Flask" "async-first, pydantic built in, we need WebSockets"`. Ten seconds now, permanent recall forever.
- **One fact per memory.** Small memories rank and cite better than essays.
- **Front-load titles with keywords** — recall weights titles 3×. "Playproof pricing decision" beats "Notes from Tuesday".
- **Weekly review:** spawn an Oracle with "what are the most important things I learned this week?" and prune junk from `memories/` by just deleting files (rebuild `index.md` lines to match).
- **Seed with Seekers** when entering new territory, then correct/extend by hand.

## 6. The Claude Code bridge

This turns Hush Brain into a **mission control for your coding agents**. Claude Code fires hooks on every lifecycle event; a one-line hook forwards them to Hush Brain, and each session shows up in the feed as its own `claude:<session>` agent.

In `~/.claude/settings.json` (all sessions) or a project's `.claude/settings.json`:

The endpoint requires the operator token (printed at `hush serve` startup; stored in `~/.hush-brain/token.txt`; pin a stable one with `HUSH_TOKEN`). Replace `YOUR-TOKEN` below:

```json
{
  "hooks": {
    "PostToolUse": [{
      "hooks": [{
        "type": "command",
        "command": "curl -s -X POST http://localhost:8199/api/hooks/claude -H \"Content-Type: application/json\" -H \"Authorization: Bearer YOUR-TOKEN\" -d @-"
      }]
    }],
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "curl -s -X POST http://localhost:8199/api/hooks/claude -H \"Content-Type: application/json\" -H \"Authorization: Bearer YOUR-TOKEN\" -d @-"
      }]
    }],
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "curl -s -X POST http://localhost:8199/api/hooks/claude -H \"Content-Type: application/json\" -H \"Authorization: Bearer YOUR-TOKEN\" -d @-"
      }]
    }]
  }
}
```

Add any events you care about — `PreToolUse`, `SubagentStart`/`SubagentStop`, `PermissionRequest`, `SessionEnd` all work; the endpoint accepts whatever Claude Code sends. Then filter the feed by `hook` or by the session's `claude:` name.

Pair it with a **Sentinel watching the same repo** and you get two independent views of an agent run: what the agent *said* it did (hooks) and what actually *changed on disk* (sentinel).

## 7. The CLI

```bash
hush serve [--host 127.0.0.1] [--port 8199]   # start the construct
hush ask "what do I know about zion?"          # one-shot Oracle, prints answer + citations
hush remember "Title" "The fact to store."     # write a memory
hush recall "search terms"                     # search the vault
hush status                                    # event/token/brain stats as JSON
hush --data-dir D:\vaults\work serve           # separate vault per context
```

`hush ask` works without the server running — it spins the stack up in-process, so it's scriptable: pipe it, cron it, alias it.

## 8. The API (build your own programs)

Everything the dashboard does goes through the same REST/WS API, so you can drive Hush Brain from scripts, other tools, or your own UIs:

All `/api/*` routes need the operator token — add `-H "Authorization: Bearer YOUR-TOKEN"` to each call below (token printed at startup / `~/.hush-brain/token.txt`):

```bash
# spawn agents
curl -X POST localhost:8199/api/agents -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR-TOKEN" \
  -d '{"kind":"sentinel","params":{"path":"C:/Dev/myrepo","interval":5}}'

# stop one
curl -X POST localhost:8199/api/agents/3/stop

# query the event log (your audit trail)
curl "localhost:8199/api/events?kind=llm.call&limit=200"
curl "localhost:8199/api/events?agent=oracle-1"

# brain
curl "localhost:8199/api/brain/recall?q=deploy"
curl -X POST localhost:8199/api/brain/remember -H "Content-Type: application/json" \
  -d '{"title":"Fact","content":"...","tags":["ops"]}'

# push any external event into the feed
curl -X POST localhost:8199/api/hooks/claude -H "Content-Type: application/json" \
  -d '{"session_id":"my-cron-job","hook_event_name":"BackupFinished"}'
```

The WebSocket at `/ws` sends one `snapshot` message on connect, then every event live — trivially consumable from any language.

Adding a new agent kind is ~20 lines of Python: subclass the pattern in [`agents.py`](../src/hush_brain/agents.py) (a class with `kind`, `mode`, and `async run(ctx)`), register it in `AGENT_KINDS`, and it appears in the API immediately. `ctx` gives you `llm()`, `brain`, `emit()`, and the orchestrator for spawning sub-agents.

## 9. Playbooks: what to actually use this for

**A. Coding-agent mission control** (the #1 use for tools like this). Wire the Claude Code bridge + a Sentinel on your repo. Kick off long agent runs and watch from one place: every tool call, every file change, timestamped in SQLite. When something goes wrong you have an audit trail instead of a scrolled-away terminal.

**B. A second brain that answers back.** Capture decisions, client facts, config gotchas, and lessons as memories (CLI or dashboard). Ask the Oracle instead of re-reading notes. Because it cites `[[memories]]`, you can trust-but-verify. Open the same folder in Obsidian when you want to browse or graph it.

**C. Project research bootstrap.** New domain? Fire 2–3 Seekers on different angles, let them populate the vault, then interrogate with Oracles and correct by hand. You end up with a curated, cited knowledge base instead of a chat transcript you'll never reopen.

**D. Token/cost audit for local + cloud LLM usage.** Every `llm.call` event records provider and token counts. `GET /api/events?kind=llm.call` is your usage ledger; per-agent totals are on the agent cards.

**E. Change detection beyond code.** Sentinel any folder that matters: the downloads dir, a shared drive folder, `node_modules` after an install, a config directory in production-adjacent boxes.

**F. Event hub for personal automation.** Anything that can `curl` can post into the feed (cron jobs, CI, other scripts via the hooks endpoint), giving you one Matrix-green pane of glass for everything happening on your machine.

## 10. How it compares to similar tools

| Tool | What it is | Where Hush Brain differs |
|---|---|---|
| [disler/claude-code-hooks-multi-agent-observability](https://github.com/disler/claude-code-hooks-multi-agent-observability) | Real-time Claude Code hook monitor (Vue, pulse charts, 12 hook types) | Hush Brain monitors *and* runs its own agents *and* has memory; disler's has richer hook visualization |
| [Octogent](https://github.com/hesamsheikh/octogent) | Orchestrates multiple Claude Code terminals (PTY, worktrees) | Octogent manages coding sessions; Hush Brain is agent-framework-agnostic with a knowledge layer |
| [Mission Control](https://github.com/builderz-labs/mission-control) | Self-hosted agent fleet dashboard (tasks, costs, RBAC) | Much bigger surface (Kanban, evals, webhooks); Hush Brain is one `uv run` and local-first |
| [Langfuse](https://langfuse.com) / AgentOps | Production LLM observability (traces, evals, SaaS/self-host) | Enterprise-grade tracing; heavier, cloud-oriented, no agents or memory of their own |
| [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) | Self-organizing Obsidian second brain via Claude Code | Deeper PKM (15 skills, lint, modes); no orchestrator/monitor. Hush Brain's vault is compatible — you can point Obsidian at it |
| [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) | Local-first personal-AI research framework (Stanford) | Bigger agent runtime + skills ecosystem; no Matrix dashboard, heavier install |

The niche Hush Brain occupies: **the only one of these that combines orchestrator + monitor + memory in a single zero-config local process** — a personal-scale mission control rather than a team platform.

## 11. Known gaps & roadmap

Honest list, informed by what the tools above do well and what users ask them for:

1. ~~**Scheduled agents**~~ — ✅ shipped in v0.2: pass `every` (`45s`/`30m`/`2h`/`1d`) on spawn.
2. **Session detail view** — the feed is a stream; there's no click-into-an-agent transcript view (disler's chat-transcript viewer is the model here).
3. **Richer Claude Code hook rendering** — hook events land as generic feed lines; grouping by session with tool-level detail (like disler's swim lanes) would make playbook A stronger.
4. **Brain maintenance agent** — claude-obsidian's `wiki-lint` (orphaned pages, stale claims) has no equivalent; memories only accumulate. A `curator` agent kind is planned.
5. **Streaming agent output** — output arrives when an agent finishes a step; token-by-token streaming into the feed would improve the feel on slow local models.
6. **Cost in currency** — tokens are tracked but not priced; a per-provider price table would turn the ledger into a bill.
7. **Auth** — the server binds to localhost only, which is the security model. Exposing it beyond localhost (e.g. monitoring from your phone) needs at least a token gate first.
8. **Embeddings-optional recall** — keyword recall is transparent and fast, but semantic recall via local Ollama embeddings (as claude-obsidian offers) would catch paraphrases; should stay optional to preserve the zero-dependency default.
9. **A `hush spawn` CLI verb** — spawn/stop agents from the terminal without curl.

PRs welcome. *There is no roadmap, only choices.*
