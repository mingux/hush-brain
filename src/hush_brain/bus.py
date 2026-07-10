"""Async event bus: every event is persisted to SQLite and fanned out to WebSocket subscribers."""

from __future__ import annotations

import asyncio
import time

from .db import EventStore


class EventBus:
    def __init__(self, store: EventStore):
        self.store = store
        self._subscribers: set[asyncio.Queue] = set()

    async def publish(self, agent: str, kind: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        ts = time.time()
        # SQLite commit is blocking I/O — keep it off the event loop
        event_id = await asyncio.to_thread(self.store.insert, ts, agent, kind, payload)
        event = {"id": event_id, "ts": ts, "agent": agent, "kind": kind, "payload": payload}
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow consumer: drop rather than block the agents
        return event

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)
