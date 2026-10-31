"""RCT3 Game Session Manager, coordinate mapping, and tool action executor."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from rct3_control.backend.protocol import PlatformBackend
from rct3_control.safety import SafetyManager
from rct3_control.types import (
    ErrorCode,
    FrameMetadata,
    MouseButton,
    RCT3ControlError,
    StatusResult,
    WindowGeometry,
    WindowInfo,
)


class GameSession:
    """Manages the active game window, coordinate transformations, and bounded input."""

    def __init__(self, backend: PlatformBackend, target_title: str = "RollerCoaster Tycoon 3"):
        self.backend = backend
        self.target_title = target_title
        self.safety = SafetyManager(backend)

        self.selected_window_id: int | None = None
        self.selected_window_pid: int | None = None

        # Current frame state
        self.current_frame_id: str | None = None
        self.current_geometry: WindowGeometry | None = None
        self.current_metadata: FrameMetadata | None = None
        self.current_png_bytes: bytes | None = None

    def find_target_window(self) -> WindowInfo:
        """Locate the target game window narrowly or report actionable errors."""
        windows = self.backend.list_windows()
        candidates: list[WindowInfo] = []

        target_lower = self.target_title.lower()
        for w in windows:
            title_match = target_lower in w.title.lower()
            owner_match = target_lower in w.owner_name.lower() or "rct3" in w.owner_name.lower()
            if title_match or owner_match:
                candidates.append(w)

        if not candidates:
            raise RCT3ControlError(
                ErrorCode.WINDOW_NOT_FOUND,
                f"No window found matching '{self.target_title}'.",
                "Ensure RCT3 Complete Edition is launched and in windowed mode.",
            )

        if len(candidates) > 1:
            # Check if one is already selected
            if self.selected_window_id is not None:
                for c in candidates:
                    if c.window_id == self.selected_window_id:
                        return c
            c_desc = [
                f"id={c.window_id} title='{c.title}' owner='{c.owner_name}'" for c in candidates
            ]
            raise RCT3ControlError(
                ErrorCode.WINDOW_AMBIGUOUS,
                f"Multiple plausible game windows found: {'; '.join(c_desc)}",
                "Close extra instances or specify exact window ID.",
            )

        win = candidates[0]
        self.selected_window_id = win.window_id
        self.selected_window_pid = win.owner_pid
        return win

    def get_status(self) -> StatusResult:
        """Report permissions, selected window, geometry, focus, stop state, and problems."""
        perms = self.backend.check_permissions()
        problems: list[str] = []

        if not perms.screen_recording:
            problems.append("Screen Recording permission is missing.")
        if not perms.accessibility:
            problems.append("Accessibility permission is missing.")

        selected_win: WindowInfo | None = None
        geometry: WindowGeometry | None = None
        is_focused = False

        try:
            selected_win = self.find_target_window()
            geometry = self.backend.get_window_geometry(selected_win.window_id)
            is_focused = self.backend.is_window_focused(selected_win.owner_pid)
            if not is_focused:
                problems.append("Game window is not currently focused.")
        except RCT3ControlError as e:
            problems.append(f"{e.code.value}: {e.message}")

        if self.safety.is_stopped:
            problems.append("Human stop latch is ACTIVE. Call reset_stop to resume.")

        return StatusResult(
            permissions=perms,
            selected_window=selected_win,
            geometry=geometry,
            focus=is_focused,
            stopped=self.safety.is_stopped,
            active_action=self.safety.active_action,
            actionable_problems=problems,
        )

    def observe(self) -> tuple[bytes, FrameMetadata]:
        """Capture screenshot of the game window and establish a new frame."""
        self.safety.check_stopped()

        perms = self.backend.check_permissions()
        if not perms.screen_recording:
            raise RCT3ControlError(
                ErrorCode.PERMISSION_MISSING,
                "Screen Recording permission is required for observe.",
                "Enable Screen Recording permission in macOS System Settings.",
            )

        win = self.find_target_window()
        png_bytes, geo = self.backend.capture_window(win.window_id)

        meta = FrameMetadata(
            width=int(geo.width * geo.scale),
            height=int(geo.height * geo.scale),
            content_rect=geo.content_rect,
            scale=geo.scale,
        )

        self.current_frame_id = meta.frame_id
        self.current_geometry = geo
        self.current_metadata = meta
        self.current_png_bytes = png_bytes

        return png_bytes, meta

    def _validate_and_map_point(self, frame_id: str, x: int, y: int) -> tuple[int, int]:
        """Validate frame ID, re-query window, check content bounds, and return screen coordinates."""
        self.safety.check_stopped()

        if self.current_frame_id is None or frame_id != self.current_frame_id:
            raise RCT3ControlError(
                ErrorCode.OBSERVATION_REQUIRED,
                f"Supplied frame_id '{frame_id}' does not match current observation frame.",
                "Call observe to obtain a fresh frame before acting.",
            )

        if self.current_geometry is None or self.selected_window_id is None:
            raise RCT3ControlError(
                ErrorCode.OBSERVATION_REQUIRED,
                "No valid observation frame established.",
                "Call observe first.",
            )

        # Content rectangle bounds check (in image pixel space)
        content_rect = self.current_geometry.content_rect
        if not content_rect.contains(x, y):
            raise RCT3ControlError(
                ErrorCode.OUT_OF_BOUNDS,
                f"Coordinates ({x}, {y}) fall outside game content rectangle (x={content_rect.x}, y={content_rect.y}, w={content_rect.width}, h={content_rect.height}).",
                "Ensure coordinates refer to the game content area inside the observation image.",
            )

        # Re-query selected window state
        current_geo = self.backend.get_window_geometry(self.selected_window_id)
        if current_geo is None:
            raise RCT3ControlError(
                ErrorCode.WINDOW_UNAVAILABLE,
                "Selected game window is no longer available.",
                "Ensure RCT3 has not been closed or minimized.",
            )

        # Check for window resize or scale change
        if (
            current_geo.width != self.current_geometry.width
            or current_geo.height != self.current_geometry.height
            or current_geo.scale != self.current_geometry.scale
        ):
            self.current_frame_id = None  # Invalidate frame
            raise RCT3ControlError(
                ErrorCode.OBSERVATION_REQUIRED,
                "Game window dimensions or scale changed since observation.",
                "Call observe to get an updated view and geometry.",
            )

        # Verify / restore focus
        if self.selected_window_pid is not None and not self.backend.is_window_focused(
            self.selected_window_pid
        ):
            self.backend.focus_window(self.selected_window_pid)
            # Brief settle for focus
            time.sleep(0.05)
            if not self.backend.is_window_focused(self.selected_window_pid):
                raise RCT3ControlError(
                    ErrorCode.FOCUS_LOST,
                    "Game window could not be focused.",
                    "Click the game window or ensure no modal dialog is blocking focus.",
                )

        # Map image coordinates to screen coordinates
        # Screen point = current_window_origin + (image_pixel / scale)
        scale = current_geo.scale if current_geo.scale > 0 else 1.0
        screen_x = int(current_geo.origin_x + (x / scale))
        screen_y = int(current_geo.origin_y + (y / scale))

        return screen_x, screen_y

    async def move(self, frame_id: str, x: int, y: int) -> dict[str, Any]:
        """Move pointer within game content."""
        async with self.safety.serialize("move"):
            screen_x, screen_y = self._validate_and_map_point(frame_id, x, y)
            self.backend.post_mouse_move(screen_x, screen_y)
            return {"action": "move", "x": x, "y": y, "screen_x": screen_x, "screen_y": screen_y}

    async def click(
        self,
        frame_id: str,
        x: int,
        y: int,
        button: MouseButton = "left",
        count: int = 1,
    ) -> dict[str, Any]:
        """Click at point in game content (left/right/middle, count 1 or 2)."""
        if button not in ("left", "right", "middle"):
            raise RCT3ControlError(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid button '{button}'. Allowed: 'left', 'right', 'middle'.",
            )
        if count not in (1, 2):
            raise RCT3ControlError(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid count {count}. Allowed: 1 or 2.",
            )

        async with self.safety.serialize("click"):
            screen_x, screen_y = self._validate_and_map_point(frame_id, x, y)
            self.backend.post_mouse_move(screen_x, screen_y)
            await asyncio.sleep(0.04)
            self.safety.check_stopped()
            self.backend.post_mouse_click(screen_x, screen_y, button=button, count=count)
            return {
                "action": "click",
                "x": x,
                "y": y,
                "button": button,
                "count": count,
                "screen_x": screen_x,
                "screen_y": screen_y,
            }

    async def drag(
        self,
        frame_id: str,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: MouseButton = "left",
        duration_ms: int = 400,
        modifiers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute smooth bounded drag from start to end coordinates."""
        if not (50 <= duration_ms <= 5000):
            raise RCT3ControlError(
                ErrorCode.INVALID_ARGUMENT,
                f"Duration {duration_ms}ms out of range (50-5000ms allowed).",
            )

        async with self.safety.serialize("drag"):
            # Validate start and end before any action
            start_sx, start_sy = self._validate_and_map_point(frame_id, start_x, start_y)
            end_sx, end_sy = self._validate_and_map_point(frame_id, end_x, end_y)

            # Move to start
            self.backend.post_mouse_move(start_sx, start_sy)
            await asyncio.sleep(0.04)
            self.safety.check_stopped()

            # Mouse down
            self.safety.record_button_down(button)
            self.backend.post_mouse_down(start_sx, start_sy, button=button)

            try:
                # Interpolate steps (every ~20ms)
                step_interval_s = 0.02
                num_steps = max(2, int((duration_ms / 1000.0) / step_interval_s))

                for i in range(1, num_steps + 1):
                    t = i / float(num_steps)
                    cur_x = int(start_sx + (end_sx - start_sx) * t)
                    cur_y = int(start_sy + (end_sy - start_sy) * t)

                    self.safety.check_stopped()
                    self.safety.check_fail_safe_corner()
                    self.backend.post_mouse_drag_move(cur_x, cur_y, button=button)
                    await asyncio.sleep(step_interval_s)

            finally:
                # Release mouse button
                self.backend.post_mouse_up(end_sx, end_sy, button=button)
                self.safety.record_button_up(button)

            return {
                "action": "drag",
                "start": (start_x, start_y),
                "end": (end_x, end_y),
                "button": button,
                "duration_ms": duration_ms,
            }

    async def scroll(self, frame_id: str, x: int, y: int, steps: int) -> dict[str, Any]:
        """Scroll vertical wheel at (x, y). Range -20 to 20."""
        if not (-20 <= steps <= 20):
            raise RCT3ControlError(
                ErrorCode.INVALID_ARGUMENT,
                f"Scroll steps {steps} out of range (-20 to 20 allowed).",
            )

        async with self.safety.serialize("scroll"):
            screen_x, screen_y = self._validate_and_map_point(frame_id, x, y)
            self.backend.post_scroll(screen_x, screen_y, steps)
            return {"action": "scroll", "x": x, "y": y, "steps": steps}

    async def press_key(
        self,
        frame_id: str,
        key: str,
        modifiers: list[str] | None = None,
        hold_ms: int = 80,
    ) -> dict[str, Any]:
        """Press and hold a key/chord for bounded time, then release."""
        if not (20 <= hold_ms <= 5000):
            raise RCT3ControlError(
                ErrorCode.INVALID_ARGUMENT,
                f"Key hold_ms {hold_ms} out of range (20-5000ms allowed).",
            )

        # Validate frame ID
        if self.current_frame_id is None or frame_id != self.current_frame_id:
            raise RCT3ControlError(
                ErrorCode.OBSERVATION_REQUIRED,
                f"Supplied frame_id '{frame_id}' does not match current observation frame.",
                "Call observe before sending input.",
            )

        async with self.safety.serialize("press_key"):
            # Check window focus
            if self.selected_window_pid is not None and not self.backend.is_window_focused(
                self.selected_window_pid
            ):
                self.backend.focus_window(self.selected_window_pid)
                await asyncio.sleep(0.04)

            self.safety.record_key_down(key, modifiers)
            self.backend.post_key_down(key, modifiers)

            try:
                # Sleep in short increments to allow rapid interruption
                hold_s = hold_ms / 1000.0
                elapsed = 0.0
                slice_s = 0.02
                while elapsed < hold_s:
                    self.safety.check_stopped()
                    cur_slice = min(slice_s, hold_s - elapsed)
                    await asyncio.sleep(cur_slice)
                    elapsed += cur_slice
            finally:
                self.backend.post_key_up(key, modifiers)
                self.safety.record_key_up(key, modifiers)

            return {"action": "press_key", "key": key, "modifiers": modifiers, "hold_ms": hold_ms}

    async def wait(self, seconds: float) -> dict[str, Any]:
        """Wait for bounded wall-clock seconds checking interruption."""
        if not (0.0 <= seconds <= 30.0):
            raise RCT3ControlError(
                ErrorCode.INVALID_ARGUMENT,
                f"Wait duration {seconds}s out of range (0-30s allowed).",
            )

        async with self.safety.serialize("wait"):
            elapsed = 0.0
            slice_s = 0.05
            while elapsed < seconds:
                self.safety.check_stopped()
                self.safety.check_fail_safe_corner()
                cur_slice = min(slice_s, seconds - elapsed)
                await asyncio.sleep(cur_slice)
                elapsed += cur_slice

            return {"action": "wait", "seconds": seconds}

    def stop(self) -> dict[str, Any]:
        """Immediately latch stop state and release any held inputs."""
        self.safety.trigger_stop("Agent/Host stop tool call")
        return {"action": "stop", "status": "stopped", "held_inputs_released": True}

    def reset_stop(self) -> dict[str, Any]:
        """Clear stop latch and invalidate current frame."""
        self.safety.reset_stop()
        self.current_frame_id = None
        self.current_metadata = None
        self.current_png_bytes = None
        return {
            "action": "reset_stop",
            "status": "ready",
            "observation_required": True,
            "message": "Stop cleared. New observation required before input.",
        }
