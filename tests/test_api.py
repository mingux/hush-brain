import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hush_brain.server import create_app

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUSH_PROVIDER", "echo")
    monkeypatch.setenv("HUSH_TOKEN", TOKEN)
    app = create_app(tmp_path)
    with TestClient(app, headers=AUTH) as test_client:
        yield test_client


def test_status(client):
    data = client.get("/api/status").json()
    assert data["provider"] == "echo"
    assert data["events"] >= 1  # system.boot


def test_api_requires_token(tmp_path, monkeypatch):
    monkeypatch.setenv("HUSH_PROVIDER", "echo")
    monkeypatch.setenv("HUSH_TOKEN", TOKEN)
    app = create_app(tmp_path)
    with TestClient(app) as bare:
        assert bare.get("/").status_code == 200  # dashboard page itself is public
        assert bare.get("/api/status").status_code == 401
        assert bare.post("/api/agents", json={"kind": "oracle"}).status_code == 401
        assert bare.post("/api/brain/remember", json={"title": "x", "content": "y"}).status_code == 401
        # query-param and X-Hush-Token forms also accepted
        assert bare.get("/api/status", params={"token": TOKEN}).status_code == 200
        assert bare.get("/api/status", headers={"X-Hush-Token": TOKEN}).status_code == 200


def test_host_header_validated(client):
    res = client.get("/api/status", headers={"Host": "evil.example.com"})
    assert res.status_code == 403


def test_ws_rejects_bad_origin_and_missing_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"X-Hush-Token": TOKEN, "Origin": "http://evil.example"}):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws"):
            pass


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


def test_events_limit_clamped(client):
    assert len(client.get("/api/events", params={"limit": -1}).json()) == 1
    assert client.get("/api/events", params={"limit": 99999}).status_code == 200


def test_claude_hook_ingest(client):
    res = client.post(
        "/api/hooks/claude",
        json={"session_id": "abc123def456xyz", "hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": "C:/Dev"},
    )
    assert res.json() == {"ok": True}
    events = client.get("/api/events", params={"kind": "hook.claude"}).json()
    assert events[0]["agent"] == "claude:abc123def456"
    assert events[0]["payload"]["tool_name"] == "Bash"


def test_claude_hook_rejects_non_json(client):
    res = client.post("/api/hooks/claude", content="a=1", headers={"Content-Type": "text/plain"})
    assert res.status_code == 415
    res = client.post("/api/hooks/claude", content="not json", headers={"Content-Type": "application/json"})
    assert res.status_code == 400


def test_websocket_snapshot_and_event(client):
    with client.websocket_connect("/ws", headers={"X-Hush-Token": TOKEN}) as ws:
        snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["provider"] == "echo"
        assert snapshot["event_count"] >= 1
        assert snapshot["version"]
        client.post("/api/brain/remember", json={"title": "Trinity", "content": "She knows."})
        message = ws.receive_json()
        assert message["type"] == "event"
        assert message["event"]["kind"] == "brain.write"


def test_dashboard_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "HUSH BRAIN" in res.text
