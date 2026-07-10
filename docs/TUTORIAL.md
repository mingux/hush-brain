# Tutorial: Your First 15 Minutes

A literal, step-by-step walkthrough. Type exactly what's shown; each step says what you should see. For the deeper "why" behind each piece, read the [Operator's Guide](GUIDE.md) afterwards.

## Step 0 — Start the server (1 min)

Open a terminal (PowerShell is fine) and run:

```
cd C:\Dev\hush-brain
uv run hush serve
```

**You should see:** the HUSH BRAIN ascii banner, then `Uvicorn running on http://127.0.0.1:8199`.

> Installed it globally with `uv tool install .`? Then just `hush serve` from anywhere.
> Windows shortcut: double-click `start.bat` in the repo folder.

Leave this terminal open — it's the server. Everything else happens in the browser or a **second** terminal.

## Step 1 — Open the dashboard (30 sec)

Go to **http://localhost:8199** in your browser.

**You should see:** a "wake up..." boot sequence, then the dashboard with green digital rain. Check the top-right corner:

- `link JACKED IN` — the live feed is connected. (If it says OFFLINE, refresh.)
- `provider ollama:llama3.1:8b` (or `anthropic:...` if you have a key set, or `echo` if neither — everything below still works on echo, the answers are just canned).

## Step 2 — Teach it something (1 min)

In the right panel (**› THE BRAIN**), find the two boxes at the bottom:

1. In **memory title**, type: `My deploy ritual`
2. In the box below, type: `Always run the test suite and check the staging site before pushing to main.`
3. Click **REMEMBER**.

**You should see:** the memory counter go to 1, your memory appear at the top of the **hot cache**, and a `brain.write` line appear in the center feed.

## Step 3 — Ask it something (2 min)

In the left panel (**› PROGRAMS**):

1. Leave the dropdown on **oracle — answer a question**.
2. In the text box, type: `what should I do before pushing to main?`
3. Click **SPAWN**.

**You should see, in order** (watch the center feed):

1. An `oracle-1` card appears in the left panel with a pulsing `RUNNING` badge.
2. `brain.recall` in the feed — it found `[[my-deploy-ritual]]` *before* calling the LLM.
3. `llm.call` — the model call, with exact token counts. (On local Ollama this step can take 1–3 minutes; on Anthropic it's seconds. The dashboard stays live while you wait.)
4. `agent.output` — the answer, grounded in your memory.
5. The card flips to `DONE`.

That's the whole core loop: **remember → recall → grounded answer with citations.** Everything else is variations.

## Step 4 — Grow the brain automatically (2 min)

1. Change the dropdown to **seeker — research a topic**.
2. Type a topic you care about, e.g.: `common mistakes when launching a SaaS`
3. Click **SPAWN**.

**You should see:** `seeker-1` run two rounds; after each round a `brain.write` appears and the memory counter climbs. When it's `DONE`, click **RECALL** in the right panel with the word `saas` — your new memories come back, scored.

Seekers write, Oracles read. Alternate them and the vault compounds.

## Step 5 — Watch a folder (1 min)

1. Dropdown → **sentinel — watch a directory**.
2. Type a path, e.g.: `C:\Dev`
3. Click **SPAWN**.

**You should see:** `sentinel-1` report how many files it's watching, and stay `RUNNING` (it's a continuous agent). Now create or save any file under that folder — within ~5 seconds the feed shows `Anomaly detected... 1 added` (or modified). Click **stop** on its card when you're done.

## Step 6 — Put an agent on a schedule (1 min) — *new in v0.2*

1. Dropdown → **seeker**, topic: `productivity techniques`
2. In the **every** box, type: `4h`
3. Click **SPAWN**.

**You should see:** the card shows mode `scheduled · cycle 0`. It runs immediately, then flips to a `SLEEPING` badge showing when the next run is. Every 4 hours it wakes and adds fresh insights to the brain — a morning-digest pattern. It keeps its **stop** button the whole time.

Accepted intervals: `45s`, `30m`, `2h`, `1d`, or a plain number of seconds. Works for oracle, seeker, and architect (not sentinel — that one already runs forever).

## Step 7 — Delegate a goal (2 min)

1. Dropdown → **architect — decompose a goal**.
2. Type: `prepare me to explain this project to a friend`
3. Click **SPAWN**.

**You should see:** the architect makes one LLM call to plan, then **spawns other agents** — new oracle/seeker cards appear on their own. This is the fan-out: one goal, several workers, all visible in one feed.

## Step 8 — Use it from the terminal (1 min)

In a **second** terminal:

```
hush remember "Coffee rule" "No coffee after 3pm or sleep suffers."
hush recall "coffee"
hush ask "what are my rules about coffee?"
hush status
```

**You should see:** `recall` prints the memory with a score; `ask` runs a full Oracle (recall → LLM → cited answer) right in the terminal; `status` prints event/token/brain counts as JSON. (If `hush` isn't found, run these from the repo folder with `uv run hush ...`.)

## Step 9 — Wire in Claude Code (optional, 3 min)

Make your Claude Code sessions visible in the feed. First grab your operator token — it's printed when `hush serve` starts, and also lives in `~/.hush-brain/token.txt`. Then open `~/.claude/settings.json` (create it if missing) and merge in, replacing `YOUR-TOKEN`:

```json
{
  "hooks": {
    "PostToolUse": [{
      "hooks": [{
        "type": "command",
        "command": "curl -s -X POST http://localhost:8199/api/hooks/claude -H \"Content-Type: application/json\" -H \"Authorization: Bearer YOUR-TOKEN\" -d @-"
      }]
    }]
  }
}
```

Start any Claude Code session and do something.

**You should see:** cyan-edged `hook.claude` lines in the feed, one per tool call, under an agent named `claude:<session-id>`. Type `hook` in the feed filter to see only those. Pair with a Sentinel on the same repo to see the file changes the session actually made.

## Step 10 — Make it a habit

The whole system is only as good as what you feed it:

- **When you decide something** → `hush remember "..." "..."` (ten seconds).
- **When you start something new** → spawn a Seeker on it.
- **When you forget something** → ask the Oracle, not your scrollback.
- **Once a week** → ask `what are the most important things in my brain right now?` and delete stale files from `~/.hush-brain/brain/memories/`.

Your data: `~/.hush-brain/brain/` is plain markdown (open it as an Obsidian vault if you like). Back it up; it's the valuable part.

## If something breaks

| Symptom | Fix |
|---|---|
| `Failed to spawn: hush — program not found` | You're outside the repo folder. `cd C:\Dev\hush-brain` first, or `uv tool install .` once to get a global `hush`. |
| Port 8199 in use | `hush serve --port 8200` |
| `provider echo` but you have Ollama | Is Ollama running? `ollama list` should answer. Then restart `hush serve`. |
| Oracle takes forever | Local 8B models are slow (1–3 min per call is normal on CPU). Set `ANTHROPIC_API_KEY` for fast cloud answers, or use a smaller Ollama model via `HUSH_OLLAMA_MODEL`. |
| Dashboard looks stale after an update | Hard refresh: Ctrl+F5. |
