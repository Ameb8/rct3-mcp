"""Abstract interface for platform capture and input backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rct3_control.types import (
    MouseButton,
    PermissionStatus,
    WindowGeometry,
    WindowInfo,
)


@runtime_checkable
class PlatformBackend(Protocol):
    """Protocol implemented by platform-specific capture and input backends."""

    def check_permissions(self) -> PermissionStatus:
        """Check Screen Recording and Accessibility permissions."""
        ...

    def list_windows(self) -> list[WindowInfo]:
        """List visible application windows."""
        ...

    def get_window_geometry(self, window_id: int) -> WindowGeometry | None:
        """Get the current geometry and content rectangle of the window."""
        ...

    def capture_window(self, window_id: int) -> tuple[bytes, WindowGeometry]:
        """Capture window pixels as PNG bytes and return the geometry at capture time."""
        ...

    def focus_window(self, pid: int) -> bool:
        """Bring the application to the foreground."""
        ...

    def is_window_focused(self, pid: int) -> bool:
        """Check if the application window is currently active and focused."""
        ...

    def get_pointer_position(self) -> tuple[int, int]:
        """Return the current global pointer coordinates (x, y)."""
        ...

    def post_mouse_move(self, x: int, y: int) -> None:
        """Move pointer to global screen coordinates (x, y)."""
        ...

    def post_mouse_click(
        self, x: int, y: int, button: MouseButton = "left", count: int = 1
    ) -> None:
        """Click at global screen coordinates (x, y)."""
        ...

    def post_mouse_down(self, x: int, y: int, button: MouseButton = "left") -> None:
        """Press mouse button at (x, y)."""
        ...

    def post_mouse_up(self, x: int, y: int, button: MouseButton = "left") -> None:
        """Release mouse button at (x, y)."""
        ...

    def post_mouse_drag_move(self, x: int, y: int, button: MouseButton = "left") -> None:
        """Move pointer during a drag."""
        ...

    def post_scroll(self, x: int, y: int, steps: int) -> None:
        """Scroll vertical wheel at global position (x, y). Positive is up, negative is down."""
        ...

    def post_key_down(self, key: str, modifiers: list[str] | None = None) -> None:
        """Press down a key."""
        ...

    def post_key_up(self, key: str, modifiers: list[str] | None = None) -> None:
        """Release a key."""
        ...

    def release_all(self) -> None:
        """Emergency release of any held mouse buttons and keys."""
        ...
