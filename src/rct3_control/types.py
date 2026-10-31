"""Core data types, exceptions, and models for RCT3 control."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """Stable error codes specified in SPEC Section 8."""

    PERMISSION_MISSING = "permission_missing"
    WINDOW_NOT_FOUND = "window_not_found"
    WINDOW_AMBIGUOUS = "window_ambiguous"
    WINDOW_UNAVAILABLE = "window_unavailable"
    FOCUS_LOST = "focus_lost"
    OBSERVATION_REQUIRED = "observation_required"
    INVALID_ARGUMENT = "invalid_argument"
    OUT_OF_BOUNDS = "out_of_bounds"
    UNSUPPORTED_KEY_OR_TEXT = "unsupported_key_or_text"
    STOPPED = "stopped"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    CAPTURE_FAILED = "capture_failed"
    INPUT_FAILED = "input_failed"
    INTERNAL_ERROR = "internal_error"


class RCT3ControlError(Exception):
    """Base exception for RCT3 control errors with code and actionable hint."""

    def __init__(self, code: ErrorCode | str, message: str, recovery_hint: str = ""):
        self.code = code if isinstance(code, ErrorCode) else ErrorCode(code)
        self.message = message
        self.recovery_hint = recovery_hint
        super().__init__(
            f"[{self.code.value}] {message}"
            + (f" (Hint: {recovery_hint})" if recovery_hint else "")
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "error_code": self.code.value,
            "message": self.message,
            "recovery_hint": self.recovery_hint,
        }


class Rect(BaseModel):
    """Rectangle in coordinates."""

    x: int
    y: int
    width: int
    height: int

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < (self.x + self.width) and self.y <= py < (self.y + self.height)


class WindowGeometry(BaseModel):
    """Window position and content geometry in screen points / image pixels."""

    origin_x: int
    origin_y: int
    width: int
    height: int
    scale: float = 1.0
    content_rect: Rect
    has_title_bar: bool = False
    title_bar_height: int = 0


class WindowInfo(BaseModel):
    """Discovered window details."""

    window_id: int
    owner_name: str
    owner_pid: int
    title: str
    bounds: Rect
    is_focused: bool = False
    layer: int = 0


class FrameMetadata(BaseModel):
    """Metadata describing a specific captured observation frame."""

    frame_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    width: int
    height: int
    content_rect: Rect
    capture_time: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    scale: float = 1.0


class PermissionStatus(BaseModel):
    """OS permission status for screen capture and accessibility input."""

    screen_recording: bool
    accessibility: bool
    details: str = ""


class StatusResult(BaseModel):
    """Report returned by the `status` tool."""

    permissions: PermissionStatus
    selected_window: WindowInfo | None = None
    geometry: WindowGeometry | None = None
    focus: bool = False
    stopped: bool = False
    active_action: str | None = None
    actionable_problems: list[str] = Field(default_factory=list)


MouseButton = Literal["left", "right", "middle"]
KeyModifier = Literal["shift", "control", "option", "command"]
