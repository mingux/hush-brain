import pytest
from fastapi.testclient import TestClient

from hush_brain.server import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUSH_PROVIDER", "echo")
    app = create_app(tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def test_status(client):
    data = client.get("/api/status").json()
    assert data["provider"] == "echo"
    assert data["events"] >= 1  # system.boot


def test_spawn_and_list_agents(client):
    res = client.post("/api/agents", json={"kind": "oracle", "params": {"question": "red or blue pill?"}})
    assert res.status_code == 200
    name = res.json()["name"]
    agents = client.get("/api/agents").json()
    assert any(a["name"] == name for a in agents)


def test_spawn_unknown_kind_is_400(client):
    res = client.post("/api/agents", json={"kind": "smith"})
    assert res.status_code == 400


def test_brain_endpoints(client):
    res = client.post("/api/brain/remember", json={"title": "White rabbit", "content": "Follow it."})
    assert res.status_code == 200
    slug = res.json()["slug"]
    hits = client.get("/api/brain/recall", params={"q": "white rabbit"}).json()
    assert any(h["slug"] == slug for h in hits)
    hot = client.get("/api/brain/hot").json()
    assert slug in hot["hot"]


def test_events_endpoint_and_filter(client):
    client.post("/api/brain/remember", json={"title": "A", "content": "B"})
    events = client.get("/api/events", params={"kind": "brain.write"}).json()
    assert events and all(e["kind"] == "brain.write" for e in events)


def test_claude_hook_ingest(client):
    res = client.post(
        "/api/hooks/claude",
        json={"session_id": "abc123def456xyz", "hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": "C:/Dev"},
    )
    assert res.json() == {"ok": True}
    events = client.get("/api/events", params={"kind": "hook.claude"}).json()
    assert events[0]["agent"] == "claude:abc123def456"
    assert events[0]["payload"]["tool_name"] == "Bash"


def test_websocket_snapshot_and_event(client):
    with client.websocket_connect("/ws") as ws:
        snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["provider"] == "echo"
        client.post("/api/brain/remember", json={"title": "Trinity", "content": "She knows."})
        message = ws.receive_json()
        assert message["type"] == "event"
        assert message["event"]["kind"] == "brain.write"


def test_dashboard_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "HUSH BRAIN" in res.text
