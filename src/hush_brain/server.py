"""FastAPI server: REST API, WebSocket event stream, and the Matrix dashboard."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .brain import Brain
from .bus import EventBus
from .db import EventStore
from .hooks import router as hooks_router
from .orchestrator import Orchestrator
from .providers import resolve_provider

STATIC_DIR = Path(__file__).parent / "static"


def default_data_dir() -> Path:
    return Path(os.environ.get("HUSH_HOME", Path.home() / ".hush-brain"))


class SpawnRequest(BaseModel):
    kind: str
    params: dict = {}


class RememberRequest(BaseModel):
    title: str
    content: str
    tags: list[str] = []


def create_app(data_dir: Path | str | None = None) -> FastAPI:
    data_dir = Path(data_dir) if data_dir else default_data_dir()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = EventStore(data_dir / "hush.db")
        bus = EventBus(store)
        brain = Brain(data_dir / "brain")
        provider = await resolve_provider()
        orchestrator = Orchestrator(bus, brain, provider)
        app.state.store = store
        app.state.bus = bus
        app.state.brain = brain
        app.state.provider = provider
        app.state.orchestrator = orchestrator
        await bus.publish("system", "system.boot", {"provider": provider.name, "version": __version__})
        yield
        await orchestrator.shutdown()
        store.close()

    app = FastAPI(title="Hush Brain", version=__version__, lifespan=lifespan)
    app.include_router(hooks_router)

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    async def status():
        return {
            "version": __version__,
            "provider": app.state.provider.name,
            "events": app.state.store.count(),
            "tokens": app.state.store.token_totals(),
            "brain": app.state.brain.stats(),
            "agents": len(app.state.orchestrator.runs),
        }

    @app.get("/api/agents")
    async def list_agents():
        return app.state.orchestrator.list()

    @app.post("/api/agents")
    async def spawn_agent(body: SpawnRequest):
        try:
            run = await app.state.orchestrator.spawn(body.kind, body.params)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return run.to_dict()

    @app.post("/api/agents/{run_id}/stop")
    async def stop_agent(run_id: int):
        stopped = await app.state.orchestrator.stop(run_id)
        if not stopped:
            raise HTTPException(status_code=404, detail="no running agent with that id")
        return {"ok": True}

    @app.get("/api/events")
    async def events(limit: int = 100, agent: str | None = None, kind: str | None = None):
        return app.state.store.recent(limit=min(limit, 500), agent=agent, kind=kind)

    @app.get("/api/brain/hot")
    async def brain_hot():
        return {"hot": app.state.brain.hot(), "stats": app.state.brain.stats()}

    @app.get("/api/brain/recall")
    async def brain_recall(q: str):
        hits = app.state.brain.recall(q)
        await app.state.bus.publish("operator", "brain.recall", {"query": q, "hits": [h["slug"] for h in hits]})
        return hits

    @app.post("/api/brain/remember")
    async def brain_remember(body: RememberRequest):
        memory = app.state.brain.remember(body.title, body.content, tags=body.tags)
        await app.state.bus.publish("operator", "brain.write", {"slug": memory["slug"], "title": memory["title"]})
        return memory

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        queue = app.state.bus.subscribe()
        try:
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "agents": app.state.orchestrator.list(),
                    "events": app.state.store.recent(50),
                    "brain": app.state.brain.stats(),
                    "provider": app.state.provider.name,
                    "tokens": app.state.store.token_totals(),
                }
            )
            while True:
                event = await queue.get()
                await websocket.send_json({"type": "event", "event": event})
        except WebSocketDisconnect:
            pass
        finally:
            app.state.bus.unsubscribe(queue)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
