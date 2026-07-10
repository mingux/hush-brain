"""FastAPI server: REST API, WebSocket event stream, and the Matrix dashboard.

Security model:
- Operator token generated at first boot (persisted in <data_dir>/token.txt,
  override with HUSH_TOKEN). Required on every /api/* route and the WebSocket.
- Host header validated against localhost (+ HUSH_ALLOWED_HOSTS) to block DNS
  rebinding.
- WebSocket handshakes from browsers must present a localhost/allowed Origin;
  cross-site pages cannot subscribe to the event stream.
- Loopback browser visits to / receive the token as a SameSite=Strict cookie,
  so the local dashboard works with zero setup; remote/API clients send
  `Authorization: Bearer <token>`.
"""

from __future__ import annotations

import ipaddress
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
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
TOKEN_COOKIE = "hush_token"


def default_data_dir() -> Path:
    return Path(os.environ.get("HUSH_HOME", Path.home() / ".hush-brain"))


def load_or_create_token(data_dir: Path) -> str:
    env_token = os.environ.get("HUSH_TOKEN")
    if env_token:
        return env_token
    token_path = data_dir / "token.txt"
    if token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    data_dir.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token, encoding="utf-8")
    return token


def allowed_hosts() -> set[str]:
    hosts = {"localhost", "127.0.0.1", "::1", "testserver"}
    extra = os.environ.get("HUSH_ALLOWED_HOSTS", "")
    hosts.update(h.strip().lower() for h in extra.split(",") if h.strip())
    return hosts


def host_only(header: str) -> str:
    """Strip the port from a Host header, IPv6-safe: '[::1]:8199' -> '::1'."""
    header = header.strip().lower()
    if header.startswith("["):
        return header[1 : header.index("]")] if "]" in header else header
    return header.rsplit(":", 1)[0] if ":" in header else header


def is_loopback(client_host: str | None) -> bool:
    try:
        return ipaddress.ip_address(client_host or "").is_loopback
    except ValueError:
        return False


class SpawnRequest(BaseModel):
    kind: str
    params: dict = {}


class RememberRequest(BaseModel):
    title: str
    content: str
    tags: list[str] = []


def create_app(data_dir: Path | str | None = None) -> FastAPI:
    data_dir = Path(data_dir) if data_dir else default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    token = load_or_create_token(data_dir)
    hosts = allowed_hosts()

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
        print(f"\n  operator token: {token}")
        print("  local browser needs nothing; API clients send: Authorization: Bearer <token>\n")
        yield
        await orchestrator.shutdown()
        store.close()

    app = FastAPI(title="Hush Brain", version=__version__, lifespan=lifespan)
    app.state.token = token

    def authorized(request: Request) -> bool:
        if request.headers.get("authorization") == f"Bearer {token}":
            return True
        if request.headers.get("x-hush-token") == token:
            return True
        if request.query_params.get("token") == token:
            return True
        return request.cookies.get(TOKEN_COOKIE) == token

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # DNS-rebinding defence: the browser always sends the attacker's Host.
        if host_only(request.headers.get("host", "")) not in hosts:
            return JSONResponse({"detail": "host not allowed"}, status_code=403)
        if request.url.path.startswith("/api/") and not authorized(request):
            return JSONResponse({"detail": "missing or bad operator token"}, status_code=401)
        return await call_next(request)

    app.include_router(hooks_router)

    @app.get("/")
    async def index(request: Request):
        response = FileResponse(STATIC_DIR / "index.html")
        # Hand the token to loopback browsers only; SameSite=Strict keeps it
        # out of cross-site requests, the Host check above blocks rebinding.
        if is_loopback(request.client.host if request.client else None):
            response.set_cookie(TOKEN_COOKIE, token, samesite="strict", httponly=True)
        return response

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
        return app.state.store.recent(limit=max(1, min(limit, 500)), agent=agent, kind=kind)

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

    def ws_allowed(websocket: WebSocket) -> bool:
        if host_only(websocket.headers.get("host", "")) not in hosts:
            return False
        origin = websocket.headers.get("origin")
        if origin:  # browsers send Origin; non-browser clients usually don't
            parsed = urlsplit(origin)
            if parsed.scheme not in ("http", "https") or host_only(parsed.netloc) not in hosts:
                return False
        supplied = (
            websocket.query_params.get("token")
            or websocket.cookies.get(TOKEN_COOKIE)
            or websocket.headers.get("x-hush-token")
        )
        return supplied == token

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        if not ws_allowed(websocket):
            await websocket.close(code=4403)
            return
        await websocket.accept()
        queue = app.state.bus.subscribe()
        try:
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "version": __version__,
                    "agents": app.state.orchestrator.list(),
                    "events": app.state.store.recent(50),
                    "event_count": app.state.store.count(),
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
