"""Single-process localhost relay. Terminal side effects require monitor acknowledgement."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from server.state import StateManager
from server.models import MonitorEvent, Command

state = StateManager(Path(os.environ["AGENT_QUEUE_STATE"]) if os.environ.get("AGENT_QUEUE_STATE") else None)
monitor_ws: WebSocket | None = None
dashboard_clients: list[WebSocket] = []
pending_commands: dict[str, asyncio.Future] = {}
busy_sessions: set[str] = set()
COMMAND_TIMEOUT = 5


def snapshot():
    return {"type": "snapshot", **state.get_snapshot(), "monitor_connected": monitor_ws is not None}


async def broadcast_to_dashboards(message: dict):
    for ws in list(dashboard_clients):
        try:
            await ws.send_json(message)
        except Exception:
            if ws in dashboard_clients:
                dashboard_clients.remove(ws)


async def expire_sessions():
    while True:
        await asyncio.sleep(3)
        if state.expire():
            await broadcast_to_dashboards(snapshot())


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(expire_sessions())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="Agent Queue", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])


def origin_allowed(headers):
    origin = headers.get("origin")
    if not origin:  # Local CLI/monitor clients do not send a browser Origin.
        return True
    parsed = urlsplit(origin)
    return parsed.scheme in ("http", "https") and parsed.netloc == headers.get("host")


@app.middleware("http")
async def require_same_origin(request: Request, call_next):
    if not origin_allowed(request.headers):
        return JSONResponse(status_code=403, content={"error": "Cross-origin requests are not allowed"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


async def accept_local(ws):
    if not origin_allowed(ws.headers):
        await ws.close(code=1008)
        return False
    await ws.accept()
    return True


async def deliver_command(command: Command):
    result = {"type": "command_result", "command_id": command.command_id, "session_id": command.session_id, "ok": False}
    session = state.sessions.get(command.session_id)
    if not session:
        return {**result, "error": "Session not found", "code": 404}
    if monitor_ws is None:
        return {**result, "error": "Monitor disconnected. Nothing was sent.", "code": 503}
    state.expire()
    if not session.available:
        return {**result, "error": "Session is unavailable. Wait for a fresh monitor update.", "code": 409}
    if command.command_id in pending_commands:
        return {**result, "error": "Command ID is already in use.", "code": 409}
    if command.session_id in busy_sessions:
        return {**result, "error": "A command is already pending for this session.", "code": 409}
    if command.command == "send_text":
        if command.expected_revision != session.revision:
            return {**result, "error": "Session changed. Review its latest output before sending.", "code": 409}
        if session.status not in ("ready", "needs_input"):
            return {**result, "error": "Open iTerm2 to interact with this session safely.", "code": 409}
    future = asyncio.get_running_loop().create_future()
    pending_commands[command.command_id] = future
    busy_sessions.add(command.session_id)
    try:
        await monitor_ws.send_json({**command.model_dump(), "expected_output": state.get_full_output(command.session_id)})
        ack = await asyncio.wait_for(future, COMMAND_TIMEOUT)
        if ack.get("ok") is not True:
            return {**result, "error": ack.get("error", "Monitor could not deliver command"), "code": 409}
        if command.command == "send_text":
            state.resolve_session(command.session_id)
            # Invalidate this screen revision before another browser can reuse it.
            # process_event replaces objects while we await the monitor. Invalidate
            # the current record, not the pre-await reference.
            current = state.sessions.get(command.session_id)
            if current:
                current.status = "working"
                current.revision += 1
            state.save()
            await broadcast_to_dashboards(snapshot())
        return {**result, "ok": True, "message": "Accepted by iTerm2. Agent completion is not confirmed."}
    except (TimeoutError, ConnectionError, RuntimeError, WebSocketDisconnect, OSError):
        return {**result, "error": "Delivery unknown. Check iTerm2 before retrying; commands are never replayed.", "code": 504}
    finally:
        pending_commands.pop(command.command_id, None)
        busy_sessions.discard(command.session_id)


@app.websocket("/ws/monitor")
async def monitor_websocket(ws: WebSocket):
    global monitor_ws
    if not await accept_local(ws):
        return
    if monitor_ws is not None:
        await ws.close(code=1008, reason="Only one monitor may connect")
        return
    monitor_ws = ws
    await broadcast_to_dashboards(snapshot())
    try:
        while True:
            data = await ws.receive_json()
            try:
                if not isinstance(data, dict):
                    raise ValueError("Monitor message must be an object")
                if data.get("type") == "command_ack":
                    future = pending_commands.get(data.get("command_id"))
                    if future and not future.done():
                        future.set_result(data)
                elif data.get("type") == "inventory":
                    ids = data.get("session_ids")
                    if not isinstance(ids, list) or len(ids) > 1000 or not all(isinstance(sid, str) for sid in ids):
                        raise ValueError("Invalid session inventory")
                    if state.reconcile(ids):
                        await broadcast_to_dashboards(snapshot())
                else:
                    event = MonitorEvent(**data)
                    item = state.process_event(event)
                    await broadcast_to_dashboards({"type": "event", "event": event.model_dump(), "session": state.sessions[event.session_id].model_dump(), "queue_item": item.model_dump() if item else None})
            except (ValidationError, ValueError, TypeError):
                await ws.send_json({"type": "error", "error": "Invalid monitor message"})
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass
    finally:
        if monitor_ws is ws:
            monitor_ws = None
            state.reconcile([])
            for future in list(pending_commands.values()):
                if not future.done():
                    future.set_exception(ConnectionError("Monitor disconnected"))
            await broadcast_to_dashboards(snapshot())


@app.websocket("/ws/dashboard")
async def dashboard_websocket(ws: WebSocket):
    if not await accept_local(ws):
        return
    dashboard_clients.append(ws)
    await ws.send_json(snapshot())
    try:
        while True:
            data = await ws.receive_json()
            try:
                command = Command(**data)
            except (ValidationError, TypeError):
                await ws.send_json({"type": "command_result", "ok": False, "error": "Invalid command", "command_id": data.get("command_id", "") if isinstance(data, dict) else ""})
                continue
            await ws.send_json(await deliver_command(command))
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass
    finally:
        if ws in dashboard_clients:
            dashboard_clients.remove(ws)


class RespondRequest(BaseModel):
    text: str
    expected_revision: int | None = None


@app.get("/api/health")
async def health():
    return {"ok": True, "monitor_connected": monitor_ws is not None, "persistence": state.path is not None}


@app.get("/api/sessions")
async def get_sessions():
    return snapshot()


@app.get("/api/sessions/{session_id}/history")
async def get_session_history(session_id: str):
    if session_id not in state.sessions:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    return {"session_id": session_id, "output": state.get_full_output(session_id)}


@app.post("/api/sessions/{session_id}/respond")
async def respond_to_session(session_id: str, req: RespondRequest):
    try:
        command = Command(command="send_text", session_id=session_id, payload={"text": req.text}, expected_revision=req.expected_revision)
    except ValidationError:
        return JSONResponse(status_code=422, content={"error": "Reply must be a single line of printable text (up to 4000 characters)"})
    result = await deliver_command(command)
    return JSONResponse(status_code=result.pop("code", 200), content=result)


dashboard_dist = Path(__file__).parent.parent / "dashboard" / "dist"
if (dashboard_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=dashboard_dist / "assets"), name="assets")


@app.get("/")
async def serve_dashboard():
    if not (dashboard_dist / "index.html").exists():
        return JSONResponse(status_code=503, content={"error": "Build the dashboard first: cd dashboard && npm ci && npm run build"})
    return FileResponse(dashboard_dist / "index.html")


@app.get("/favicon.svg")
async def favicon():
    return FileResponse(dashboard_dist / "favicon.svg")
