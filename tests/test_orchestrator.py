import asyncio

import pytest

from hush_brain.brain import Brain
from hush_brain.bus import EventBus
from hush_brain.db import EventStore
from hush_brain.orchestrator import Orchestrator
from hush_brain.providers import EchoProvider


def make_stack(tmp_path):
    store = EventStore(tmp_path / "hush.db")
    bus = EventBus(store)
    brain = Brain(tmp_path / "brain")
    orch = Orchestrator(bus, brain, EchoProvider())
    return store, bus, brain, orch


def test_oracle_runs_to_done(tmp_path):
    async def scenario():
        store, bus, brain, orch = make_stack(tmp_path)
        brain.remember("The spoon", "There is no spoon.")
        run = await orch.spawn("oracle", {"question": "what about the spoon?"})
        await orch.tasks[run.id]
        assert run.status == "done"
        assert run.output_tokens > 0
        kinds = {e["kind"] for e in store.recent(50)}
        assert {"agent.spawned", "llm.call", "agent.output", "agent.done"} <= kinds
        store.close()

    asyncio.run(scenario())


def test_seeker_writes_to_brain(tmp_path):
    async def scenario():
        store, bus, brain, orch = make_stack(tmp_path)
        run = await orch.spawn("seeker", {"topic": "zion", "rounds": 2})
        await orch.tasks[run.id]
        assert run.status == "done"
        assert brain.stats()["memories"] == 2
        store.close()

    asyncio.run(scenario())


def test_unknown_kind_raises(tmp_path):
    async def scenario():
        _, _, _, orch = make_stack(tmp_path)
        with pytest.raises(ValueError):
            await orch.spawn("smith")

    asyncio.run(scenario())


def test_sentinel_is_continuous_and_stoppable(tmp_path):
    async def scenario():
        store, bus, brain, orch = make_stack(tmp_path)
        watched = tmp_path / "watched"
        watched.mkdir()
        run = await orch.spawn("sentinel", {"path": str(watched), "interval": 1})
        await asyncio.sleep(0.3)
        assert run.status == "running"
        stopped = await orch.stop(run.id)
        assert stopped
        assert run.status == "stopped"
        store.close()

    asyncio.run(scenario())


def test_parse_every():
    from hush_brain.orchestrator import parse_every

    assert parse_every(90) == 90.0
    assert parse_every("45s") == 45.0
    assert parse_every("30m") == 1800.0
    assert parse_every("2h") == 7200.0
    assert parse_every("1d") == 86400.0
    assert parse_every(0.1) == 1.0  # clamped to 1s floor
    with pytest.raises(ValueError):
        parse_every("soon")


def test_scheduled_agent_repeats_until_stopped(tmp_path):
    async def scenario():
        store, bus, brain, orch = make_stack(tmp_path)
        run = await orch.spawn("oracle", {"question": "tick", "every": 1})
        assert run.mode == "scheduled"
        await asyncio.sleep(2.6)  # enough for 2+ cycles at 1s
        assert run.cycles >= 2
        assert run.status in ("running", "sleeping")
        stopped = await orch.stop(run.id)
        assert stopped and run.status == "stopped"
        outputs = [e for e in store.recent(100) if e["kind"] == "agent.output" and e["agent"] == run.name]
        assert len(outputs) >= 2
        store.close()

    asyncio.run(scenario())


def test_continuous_agent_rejects_every(tmp_path):
    async def scenario():
        _, _, _, orch = make_stack(tmp_path)
        with pytest.raises(ValueError):
            await orch.spawn("sentinel", {"path": ".", "every": "5m"})

    asyncio.run(scenario())


def test_sentinel_nonexistent_path_fails_fast(tmp_path):
    async def scenario():
        store, bus, brain, orch = make_stack(tmp_path)
        run = await orch.spawn("sentinel", {"path": str(tmp_path / "does-not-exist")})
        await orch.tasks[run.id]
        assert run.status == "failed"
        assert "not a directory" in run.error
        store.close()

    asyncio.run(scenario())


def test_sentinel_respects_roots_allowlist(tmp_path, monkeypatch):
    async def scenario():
        store, bus, brain, orch = make_stack(tmp_path)
        allowed = tmp_path / "allowed"
        outside = tmp_path / "outside"
        allowed.mkdir()
        outside.mkdir()
        monkeypatch.setenv("HUSH_SENTINEL_ROOTS", str(allowed))
        run = await orch.spawn("sentinel", {"path": str(outside)})
        await orch.tasks[run.id]
        assert run.status == "failed"
        assert "HUSH_SENTINEL_ROOTS" in run.error
        store.close()

    asyncio.run(scenario())


def test_provider_config_errors(monkeypatch):
    from hush_brain.providers import resolve_provider

    monkeypatch.setenv("HUSH_PROVIDER", "skynet")
    with pytest.raises(ValueError):
        asyncio.run(resolve_provider())

    monkeypatch.setenv("HUSH_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        asyncio.run(resolve_provider())


def test_agent_crash_marks_failed_not_fatal(tmp_path):
    async def scenario():
        store, bus, brain, orch = make_stack(tmp_path)

        class Bomb:
            kind = "bomb"
            mode = "on-demand"

            async def run(self, ctx):
                raise RuntimeError("boom")

        import hush_brain.agents as agents_mod

        agents_mod.AGENT_KINDS["bomb"] = Bomb
        try:
            run = await orch.spawn("bomb")
            await orch.tasks[run.id]
            assert run.status == "failed"
            assert "boom" in run.error
            # orchestrator still works after a crash
            run2 = await orch.spawn("oracle", {"question": "still alive?"})
            await orch.tasks[run2.id]
            assert run2.status == "done"
        finally:
            del agents_mod.AGENT_KINDS["bomb"]
        store.close()

    asyncio.run(scenario())
