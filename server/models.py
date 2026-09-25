"""Validated wire protocol shared by the relay and monitor."""
import time
import uuid
from typing import Literal
from pydantic import BaseModel, Field, model_validator

Status = Literal["working", "ready", "needs_input", "permission_prompt", "idle"]


class SessionState(BaseModel):
    session_id: str
    tab_name: str
    status: Status = "working"
    tail_output: str = ""
    summary: str = ""
    last_event_time: float = Field(default_factory=time.time)
    last_seen: float = Field(default_factory=time.time)
    available: bool = False
    revision: int = 0


class QueueItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    event_type: str
    tail_output: str
    status: Literal["pending", "seen", "resolved"] = "pending"
    created_at: float = Field(default_factory=time.time)


class MonitorEvent(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    tab_name: str = Field(max_length=200)
    event_type: Status
    tail_output: str = Field(default="", max_length=100_000)
    summary: str = Field(default="", max_length=1000)
    full_output: str = Field(default="", max_length=100_000)
    timestamp: float = Field(default_factory=time.time, allow_inf_nan=False)


class Command(BaseModel):
    command: Literal["send_text", "focus_tab", "get_history", "rename_tab"]
    session_id: str = Field(min_length=1, max_length=200)
    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=100)
    expected_revision: int | None = None
    payload: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self):
        key = {"send_text": "text", "rename_tab": "name"}.get(self.command)
        if key:
            value = self.payload.get(key, "")
            limit = 4000 if key == "text" else 100
            # A terminal treats newlines and escape bytes as actions, not plain text.
            if not value.strip() or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError(f"{key} must be a single line of 1–{limit} printable characters")
            if set(self.payload) != {key}:
                raise ValueError("Unexpected command payload")
        elif self.payload:
            raise ValueError("This command does not accept a payload")
        return self
