"""Agent lifecycle: spawn, supervise, stop. An agent crash never takes down the orchestrator."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from .agents import AGENT_KINDS, AgentContext


@dataclass
class AgentRun:
    id: int
    name: str
    kind: str
    mode: str
    params: dict
    status: str = "spawning"
    started: float = field(default_factory=time.time)
    finished: float | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "mode": self.mode,
            "status": self.status,
            "started": self.started,
            "finished": self.finished,
            "error": self.error,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "params": self.params,
        }


class Orchestrator:
    def __init__(self, bus, brain, provider):
        self.bus = bus
        self.brain = brain
        self.provider = provider
        self.runs: dict[int, AgentRun] = {}
        self.tasks: dict[int, asyncio.Task] = {}
        self._next_id = 1
        self._kind_counters: dict[str, int] = {}

    async def spawn(self, kind: str, params: dict | None = None) -> AgentRun:
        if kind not in AGENT_KINDS:
            raise ValueError(f"unknown agent kind: {kind!r} (known: {sorted(AGENT_KINDS)})")
        params = params or {}
        agent_cls = AGENT_KINDS[kind]
        self._kind_counters[kind] = self._kind_counters.get(kind, 0) + 1
        run = AgentRun(
            id=self._next_id,
            name=f"{kind}-{self._kind_counters[kind]}",
            kind=kind,
            mode=agent_cls.mode,
            params=params,
        )
        self._next_id += 1
        self.runs[run.id] = run
        self.tasks[run.id] = asyncio.create_task(self._supervise(run, agent_cls()))
        return run

    async def _supervise(self, run: AgentRun, agent) -> None:
        ctx = AgentContext(
            name=run.name,
            bus=self.bus,
            brain=self.brain,
            provider=self.provider,
            orchestrator=self,
            params=run.params,
        )
        await self.bus.publish(run.name, "agent.spawned", {"kind": run.kind, "mode": run.mode, "params": run.params})
        run.status = "running"
        await self.bus.publish(run.name, "agent.status", {"status": "running"})
        try:
            await agent.run(ctx)
        except asyncio.CancelledError:
            run.status = "stopped"
            run.finished = time.time()
            await self.bus.publish(run.name, "agent.status", {"status": "stopped"})
            raise
        except Exception as exc:  # agent crash -> failed, orchestrator lives on
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            run.finished = time.time()
            await self.bus.publish(run.name, "agent.error", {"error": run.error})
        else:
            run.status = "done"
            run.finished = time.time()
            await self.bus.publish(run.name, "agent.done", {})

    async def stop(self, run_id: int) -> bool:
        task = self.tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    def list(self) -> list[dict]:
        return [run.to_dict() for run in sorted(self.runs.values(), key=lambda r: r.id, reverse=True)]

    def add_tokens(self, name: str, input_tokens: int, output_tokens: int) -> None:
        for run in self.runs.values():
            if run.name == name:
                run.input_tokens += input_tokens
                run.output_tokens += output_tokens
                return

    async def shutdown(self) -> None:
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
