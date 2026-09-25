"""Bounded local state. Restoring a snapshot never restores delivery authority."""
import json
import os
import tempfile
import time
from pathlib import Path
from server.models import SessionState, QueueItem, MonitorEvent

MAX_SESSIONS = 100
MAX_QUEUE_ITEMS = 500
STALE_AFTER = 15


class StateManager:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.sessions: dict[str, SessionState] = {}
        self.queue: list[QueueItem] = []
        self.full_outputs: dict[str, str] = {}
        if path and path.exists():
            try:
                data = json.loads(path.read_text())
                if data.get("version") != 1:
                    raise ValueError("Unsupported version")
                self.sessions = {sid: SessionState(**s) for sid, s in data["sessions"].items()}
                self.queue = [QueueItem(**q) for q in data["queue"]]
                self.full_outputs = data.get("full_outputs", {})
                for session in self.sessions.values():
                    session.available = False
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"Cannot read snapshot {path}; preserve or move it before restarting") from exc

    def save(self):
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Replace on the same filesystem; a partial write cannot destroy the last snapshot.
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".snapshot-")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump({"version": 1, **self.get_snapshot(), "full_outputs": self.full_outputs}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def process_event(self, event: MonitorEvent) -> QueueItem | None:
        sid = event.session_id
        previous = self.sessions.get(sid)
        self.sessions[sid] = SessionState(
            session_id=sid, tab_name=event.tab_name, status=event.event_type,
            tail_output=event.tail_output, summary=event.summary,
            last_event_time=time.time(), last_seen=time.time(), available=True,
            revision=(previous.revision if previous else 0) + 1,
        )
        self.full_outputs[sid] = event.full_output
        item = None
        if event.event_type == "working":
            self.resolve_session(sid, save=False)
        elif event.event_type in ("ready", "needs_input", "permission_prompt"):
            pending = next((q for q in self.queue if q.session_id == sid and q.status == "pending"), None)
            if pending:
                pending.event_type, pending.tail_output = event.event_type, event.tail_output
            else:
                item = QueueItem(session_id=sid, event_type=event.event_type, tail_output=event.tail_output)
                self.queue.append(item)
        self.queue = self.queue[-MAX_QUEUE_ITEMS:]
        while len(self.sessions) > MAX_SESSIONS:
            oldest = min(self.sessions, key=lambda key: self.sessions[key].last_seen)
            del self.sessions[oldest]
            self.full_outputs.pop(oldest, None)
            self.queue = [q for q in self.queue if q.session_id != oldest]
        self.save()
        return item

    def reconcile(self, active_ids: list[str]):
        now = time.time()
        changed = False
        for sid, session in self.sessions.items():
            # An inventory only renews freshness; an event must establish availability.
            if sid in active_ids:
                session.last_seen = now
            elif session.available:
                session.available = False
                changed = True
        if changed:
            self.save()
        return changed

    def expire(self):
        changed = False
        for session in self.sessions.values():
            if session.available and time.time() - session.last_seen > STALE_AFTER:
                session.available = False
                changed = True
        if changed:
            self.save()
        return changed

    def resolve_session(self, sid, save=True):
        for item in self.queue:
            if item.session_id == sid and item.status == "pending":
                item.status = "resolved"
        if save:
            self.save()

    def resolve_queue_item(self, item_id: str) -> bool:
        for item in self.queue:
            if item.id == item_id:
                item.status = "resolved"
                self.save()
                return True
        return False

    def get_grouped_sessions(self):
        groups = {"attention": [], "working": [], "idle": []}
        for session in self.sessions.values():
            group = "attention" if session.status in ("ready", "needs_input", "permission_prompt") else "working" if session.status == "working" else "idle"
            groups[group].append(session)
        return groups

    def get_full_output(self, session_id: str) -> str:
        return self.full_outputs.get(session_id, "")

    def get_snapshot(self) -> dict:
        return {"sessions": {sid: s.model_dump() for sid, s in self.sessions.items()}, "queue": [q.model_dump() for q in self.queue]}
