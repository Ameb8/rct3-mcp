"""Mock capture and input backend for testing and headless environments."""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw

from rct3_control.backend.protocol import PlatformBackend
from rct3_control.types import (
    MouseButton,
    PermissionStatus,
    Rect,
    WindowGeometry,
    WindowInfo,
)


class MockBackend(PlatformBackend):
    """Controllable backend for tests without native OS/GUI requirements."""

    def __init__(
        self,
        window_id: int = 1001,
        owner_name: str = "RollerCoaster Tycoon 3",
        owner_pid: int = 12345,
        title: str = "RollerCoaster Tycoon 3",
        origin_x: int = 100,
        origin_y: int = 100,
        width: int = 1280,
        height: int = 720,
        title_bar_height: int = 28,
        screen_recording_perm: bool = True,
        accessibility_perm: bool = True,
    ):
        self.window_id = window_id
        self.owner_name = owner_name
        self.owner_pid = owner_pid
        self.title = title
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.width = width
        self.height = height
        self.title_bar_height = title_bar_height

        self.screen_recording_perm = screen_recording_perm
        self.accessibility_perm = accessibility_perm
        self.is_focused = True
        self.pointer_x = origin_x + 500
        self.pointer_y = origin_y + 300

        self.events: list[tuple[str, dict[str, Any]]] = []
        self.held_buttons: set[str] = set()
        self.held_keys: set[str] = set()
        self.window_available = True

    def check_permissions(self) -> PermissionStatus:
        details = ""
        if not self.screen_recording_perm:
            details += "Screen Recording permission missing. "
        if not self.accessibility_perm:
            details += "Accessibility permission missing."
        return PermissionStatus(
            screen_recording=self.screen_recording_perm,
            accessibility=self.accessibility_perm,
            details=details.strip(),
        )

    def list_windows(self) -> list[WindowInfo]:
        if not self.window_available:
            return []
        return [
            WindowInfo(
                window_id=self.window_id,
                owner_name=self.owner_name,
                owner_pid=self.owner_pid,
                title=self.title,
                bounds=Rect(
                    x=self.origin_x,
                    y=self.origin_y,
                    width=self.width,
                    height=self.height,
                ),
                is_focused=self.is_focused,
            )
        ]

    def get_window_geometry(self, window_id: int) -> WindowGeometry | None:
        if not self.window_available or window_id != self.window_id:
            return None
        content_rect = Rect(
            x=0,
            y=self.title_bar_height,
            width=self.width,
            height=self.height - self.title_bar_height,
        )
        return WindowGeometry(
            origin_x=self.origin_x,
            origin_y=self.origin_y,
            width=self.width,
            height=self.height,
            scale=1.0,
            content_rect=content_rect,
            has_title_bar=self.title_bar_height > 0,
            title_bar_height=self.title_bar_height,
        )

    def capture_window(self, window_id: int) -> tuple[bytes, WindowGeometry]:
        geo = self.get_window_geometry(window_id)
        if geo is None:
            raise RuntimeError(f"Window {window_id} not available for capture")

        img = Image.new("RGB", (geo.width, geo.height), color=(28, 44, 76))
        draw = ImageDraw.Draw(img)

        # Title bar decoration if present
        if geo.has_title_bar and geo.title_bar_height > 0:
            draw.rectangle(
                [(0, 0), (geo.width, geo.title_bar_height)],
                fill=(60, 60, 60),
                outline=(80, 80, 80),
            )

        # Game content area
        cr = geo.content_rect
        draw.rectangle(
            [(cr.x, cr.y), (cr.x + cr.width - 1, cr.y + cr.height - 1)],
            fill=(40, 120, 60),
            outline=(200, 200, 200),
        )

        # Draw a simulated game UI icon/button in bottom left
        draw.rectangle([(20, cr.y + 20), (120, cr.y + 60)], fill=(220, 180, 50))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), geo

    def focus_window(self, pid: int) -> bool:
        if pid == self.owner_pid:
            self.is_focused = True
            self.events.append(("focus", {"pid": pid, "success": True}))
            return True
        return False

    def is_window_focused(self, pid: int) -> bool:
        return self.is_focused and (pid == self.owner_pid)

    def get_pointer_position(self) -> tuple[int, int]:
        return (self.pointer_x, self.pointer_y)

    def post_mouse_move(self, x: int, y: int) -> None:
        self.pointer_x = x
        self.pointer_y = y
        self.events.append(("mouse_move", {"x": x, "y": y}))

    def post_mouse_down(self, x: int, y: int, button: MouseButton = "left") -> None:
        self.pointer_x = x
        self.pointer_y = y
        self.held_buttons.add(button)
        self.events.append(("mouse_down", {"x": x, "y": y, "button": button}))

    def post_mouse_up(self, x: int, y: int, button: MouseButton = "left") -> None:
        self.pointer_x = x
        self.pointer_y = y
        self.held_buttons.discard(button)
        self.events.append(("mouse_up", {"x": x, "y": y, "button": button}))

    def post_mouse_click(
        self, x: int, y: int, button: MouseButton = "left", count: int = 1
    ) -> None:
        self.pointer_x = x
        self.pointer_y = y
        self.events.append(("mouse_click", {"x": x, "y": y, "button": button, "count": count}))

    def post_mouse_drag_move(self, x: int, y: int, button: MouseButton = "left") -> None:
        self.pointer_x = x
        self.pointer_y = y
        self.events.append(("mouse_drag_move", {"x": x, "y": y, "button": button}))

    def post_scroll(self, x: int, y: int, steps: int) -> None:
        self.pointer_x = x
        self.pointer_y = y
        self.events.append(("scroll", {"x": x, "y": y, "steps": steps}))

    def post_key_down(self, key: str, modifiers: list[str] | None = None) -> None:
        self.held_keys.add(key)
        self.events.append(("key_down", {"key": key, "modifiers": modifiers or []}))

    def post_key_up(self, key: str, modifiers: list[str] | None = None) -> None:
        self.held_keys.discard(key)
        self.events.append(("key_up", {"key": key, "modifiers": modifiers or []}))

    def release_all(self) -> None:
        released = {"buttons": list(self.held_buttons), "keys": list(self.held_keys)}
        self.held_buttons.clear()
        self.held_keys.clear()
        self.events.append(("release_all", released))
