"""Claude Code bridge (Octogent-inspired): ingest Claude Code hook events over HTTP
so external coding-agent sessions show up in the same monitor.

Wire it up in Claude Code settings.json, e.g.:

    "hooks": {
      "PostToolUse": [{
        "hooks": [{
          "type": "command",
          "command": "curl -s -X POST http://localhost:8199/api/hooks/claude -H \"Content-Type: application/json\" -H \"Authorization: Bearer YOUR-TOKEN\" -d @-"
        }]
      }]
    }

Claude Code pipes the hook JSON on stdin; curl forwards it here. The token is
printed at `hush serve` startup and stored in <data_dir>/token.txt (pin a
stable one with HUSH_TOKEN). Auth is enforced by the /api/* middleware; this
handler additionally requires a real JSON body so text/plain form posts from
web pages are rejected.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.post("/api/hooks/claude")
async def claude_hook(request: Request):
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="Content-Type must be application/json")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="body is not valid JSON")
    if not isinstance(body, dict):
        body = {"data": body}
    session = str(body.get("session_id", "unknown"))[:12]
    payload = {
        "hook_event": body.get("hook_event_name", "unknown"),
        "tool_name": body.get("tool_name"),
        "session_id": session,
        "cwd": body.get("cwd"),
    }
    await request.app.state.bus.publish(f"claude:{session}", "hook.claude", payload)
    return {"ok": True}
