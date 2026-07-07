"""Built-in agents. Matrix-named, OpenJarvis-mode-inspired.

| Agent     | Mode       | Role                                                        |
|-----------|------------|-------------------------------------------------------------|
| Oracle    | on-demand  | Answers questions grounded in the brain, cites memories     |
| Seeker    | on-demand  | Multi-round research loop; writes findings into the brain   |
| Sentinel  | continuous | Watches a directory for changes; reports to the feed        |
| Architect | on-demand  | Decomposes a goal into subtasks, dispatches other agents    |
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Any

SYSTEM_PROMPT = (
    "You are a program running inside Hush Brain, a local agent orchestrator. "
    "Be precise and concise. Answer in plain text."
)


@dataclass
class AgentContext:
    name: str
    bus: Any
    brain: Any
    provider: Any
    orchestrator: Any
    params: dict = field(default_factory=dict)

    async def emit(self, kind: str, payload: dict | None = None) -> None:
        await self.bus.publish(self.name, kind, payload)

    async def llm(self, prompt: str, system: str = SYSTEM_PROMPT) -> str:
        result = await self.provider.complete(prompt, system=system)
        await self.emit(
            "llm.call",
            {
                "provider": self.provider.name,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
        )
        self.orchestrator.add_tokens(self.name, result.input_tokens, result.output_tokens)
        return result.text


class OracleAgent:
    kind = "oracle"
    mode = "on-demand"
    description = "Answers a question grounded in the brain, with memory citations."

    async def run(self, ctx: AgentContext) -> None:
        question = ctx.params.get("question", "What do you know?")
        hits = ctx.brain.recall(question)
        await ctx.emit("brain.recall", {"query": question, "hits": [h["slug"] for h in hits]})
        context = "\n".join(f"[[{h['slug']}]] {h['title']}: {h['excerpt']}" for h in hits)
        prompt = (
            f"Question: {question}\n\n"
            f"Relevant memories (cite them as [[slug]] when used):\n{context or '(none)'}\n\n"
            "Answer the question. If memories are relevant, ground your answer in them."
        )
        answer = await ctx.llm(prompt)
        await ctx.emit("agent.output", {"text": answer, "citations": [h["slug"] for h in hits]})


class SeekerAgent:
    kind = "seeker"
    mode = "on-demand"
    description = "Multi-round research loop; writes each finding into the brain."

    async def run(self, ctx: AgentContext) -> None:
        topic = ctx.params.get("topic", "the nature of the Matrix")
        rounds = max(1, min(int(ctx.params.get("rounds", 2)), 5))
        notes = ""
        for i in range(1, rounds + 1):
            prompt = (
                f"Research topic: {topic}\n"
                f"Round {i} of {rounds}. Previous notes:\n{notes or '(none)'}\n\n"
                "State ONE new key insight about the topic, in 2-3 sentences. "
                "Do not repeat previous notes."
            )
            finding = await ctx.llm(prompt)
            notes += f"\n- {finding}"
            memory = ctx.brain.remember(f"{topic} — insight {i}", finding, tags=["seeker", "research"])
            await ctx.emit("brain.write", {"slug": memory["slug"], "title": memory["title"]})
            await ctx.emit("agent.output", {"text": finding, "round": i})


class SentinelAgent:
    kind = "sentinel"
    mode = "continuous"
    description = "Watches a directory for file changes and reports them to the feed."

    MAX_FILES = 5000
    SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}

    def _snapshot(self, root: str) -> dict[str, float]:
        snap: dict[str, float] = {}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]
            for name in filenames:
                path = os.path.join(dirpath, name)
                try:
                    snap[path] = os.path.getmtime(path)
                except OSError:
                    continue
                if len(snap) >= self.MAX_FILES:
                    return snap
        return snap

    async def run(self, ctx: AgentContext) -> None:
        root = ctx.params.get("path", ".")
        interval = max(1.0, float(ctx.params.get("interval", 5)))
        previous = await asyncio.to_thread(self._snapshot, root)
        await ctx.emit("agent.output", {"text": f"Sentinel online. Watching {root} ({len(previous)} files)."})
        while True:
            await asyncio.sleep(interval)
            current = await asyncio.to_thread(self._snapshot, root)
            added = sorted(set(current) - set(previous))
            removed = sorted(set(previous) - set(current))
            modified = sorted(p for p in current if p in previous and current[p] != previous[p])
            if added or removed or modified:
                await ctx.emit(
                    "agent.output",
                    {
                        "text": f"Anomaly detected in {root}: "
                        f"{len(added)} added, {len(modified)} modified, {len(removed)} removed.",
                        "added": added[:20],
                        "modified": modified[:20],
                        "removed": removed[:20],
                    },
                )
            previous = current


class ArchitectAgent:
    kind = "architect"
    mode = "on-demand"
    description = "Decomposes a goal into subtasks and dispatches Oracle/Seeker agents."

    async def run(self, ctx: AgentContext) -> None:
        goal = ctx.params.get("goal", "understand this system")
        prompt = (
            f"Goal: {goal}\n\n"
            "Decompose this goal into 1-3 subtasks for worker agents. "
            "Reply with one subtask per line, using exactly this format:\n"
            "oracle: <a question to answer>\n"
            "seeker: <a topic to research>\n"
            "Output only the subtask lines, nothing else."
        )
        plan = await ctx.llm(prompt)
        dispatched = []
        for line in plan.splitlines():
            match = re.match(r"^\s*(oracle|seeker)\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
            if not match or len(dispatched) >= 3:
                continue
            kind, arg = match.group(1).lower(), match.group(2).strip()
            params = {"question": arg} if kind == "oracle" else {"topic": arg, "rounds": 1}
            run = await ctx.orchestrator.spawn(kind, params)
            dispatched.append({"agent": run.name, "kind": kind, "task": arg})
        if not dispatched:  # plan didn't parse — fall back to a single oracle
            run = await ctx.orchestrator.spawn("oracle", {"question": goal})
            dispatched.append({"agent": run.name, "kind": "oracle", "task": goal})
        await ctx.emit("agent.output", {"text": f"Dispatched {len(dispatched)} agents for: {goal}", "dispatched": dispatched})


AGENT_KINDS = {
    agent.kind: agent for agent in (OracleAgent, SeekerAgent, SentinelAgent, ArchitectAgent)
}
