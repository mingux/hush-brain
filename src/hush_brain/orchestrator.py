"""Agent lifecycle: spawn, supervise, stop. An agent crash never takes down the orchestrator."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

from .agents import AGENT_KINDS, AgentContext


def parse_every(value) -> float:
    """Parse a schedule interval: 90, "90", "45s", "30m", "2h", "1d" -> seconds."""
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*$", str(value).lower())
        if not match:
            raise ValueError(f"bad interval {value!r} — use e.g. 45s, 30m, 2h, 1d")
        seconds = float(match.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]
    return max(1.0, seconds)


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
    cycles: int = 0
    next_run: float | None = None

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
            "cycles": self.cycles,
            "next_run": self.next_run,
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
        interval = None
        if params.get("every") is not None:
            if agent_cls.mode == "continuous":
                raise ValueError(f"{kind} is continuous — it runs until stopped; 'every' does not apply")
            interval = parse_every(params["every"])
        self._kind_counters[kind] = self._kind_counters.get(kind, 0) + 1
        run = AgentRun(
            id=self._next_id,
            name=f"{kind}-{self._kind_counters[kind]}",
            kind=kind,
            mode="scheduled" if interval else agent_cls.mode,
            params=params,
        )
        self._next_id += 1
        self.runs[run.id] = run
        self.tasks[run.id] = asyncio.create_task(self._supervise(run, agent_cls(), interval))
        return run

    async def _supervise(self, run: AgentRun, agent, interval: float | None = None) -> None:
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
            if interval is None:
                await agent.run(ctx)
            else:  # scheduled: run, sleep, repeat until stopped
                while True:
                    await agent.run(ctx)
                    run.cycles += 1
                    run.status = "sleeping"
                    run.next_run = time.time() + interval
                    await self.bus.publish(
                        run.name, "agent.status",
                        {"status": "sleeping", "cycle": run.cycles, "next_run": run.next_run},
                    )
                    await asyncio.sleep(interval)
                    run.status = "running"
                    run.next_run = None
                    await self.bus.publish(run.name, "agent.status", {"status": "running", "cycle": run.cycles + 1})
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
