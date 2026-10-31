"""Safety manager, input tracking, human interruption, and serialization."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from rct3_control.backend.protocol import PlatformBackend
from rct3_control.types import ErrorCode, MouseButton, RCT3ControlError

logger = logging.getLogger("rct3_control.safety")


class SafetyManager:
    """Manages input serialization, held state tracking, and human interruption."""

    def __init__(self, backend: PlatformBackend):
        self.backend = backend
        self._action_lock = asyncio.Lock()
        self._stop_event = threading.Event()
        self._held_buttons: set[str] = set()
        self._held_keys: set[str] = set()
        self._held_modifiers: set[str] = set()
        self._active_action: str | None = None
        self._stop_reason: str = ""

    @property
    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    @property
    def active_action(self) -> str | None:
        return self._active_action

    def check_stopped(self) -> None:
        """Raise an error if the safety stop latch is currently active."""
        if self._stop_event.is_set():
            msg = f"System is currently in a STOPPED state ({self._stop_reason})."
            raise RCT3ControlError(
                ErrorCode.STOPPED,
                msg,
                "The owner interrupted execution or safety stopped. Call reset_stop after owner confirmation, then observe.",
            )

    def check_fail_safe_corner(self) -> None:
        """Check if pointer is parked in the screen fail-safe corner (0, 0)."""
        try:
            x, y = self.backend.get_pointer_position()
            if x <= 1 and y <= 1:
                self.trigger_stop("Screen-corner fail-safe triggered (pointer moved to 0,0)")
        except (OSError, RuntimeError) as e:
            logger.debug("Failed checking fail-safe corner: %s", e)

    def trigger_stop(self, reason: str = "Human stop triggered") -> None:
        """Latch the stop state and immediately release all held inputs."""
        self._stop_event.set()
        self._stop_reason = reason
        self.release_all_held(force=True)

    def reset_stop(self) -> None:
        """Clear the stop latch. (Frame must also be invalidated by session)."""
        self._stop_event.clear()
        self._stop_reason = ""
        self.release_all_held(force=True)

    def release_all_held(self, force: bool = False) -> None:
        """Release any held buttons, keys, and modifiers."""
        try:
            self.backend.release_all()
        except (OSError, RuntimeError) as e:
            logger.debug("Backend release_all error: %s", e)
        finally:
            self._held_buttons.clear()
            self._held_keys.clear()
            self._held_modifiers.clear()

    @asynccontextmanager
    async def serialize(self, action_name: str) -> AsyncGenerator[None, None]:
        """Serialize ordinary operations so multiple calls cannot interleave input."""
        # Stop check before waiting for lock
        self.check_stopped()
        self.check_fail_safe_corner()
        self.check_stopped()

        async with self._action_lock:
            # Recheck after acquiring lock in case stop was triggered while waiting
            self.check_stopped()
            self.check_fail_safe_corner()
            self.check_stopped()

            self._active_action = action_name
            try:
                yield
            finally:
                self._active_action = None
                self.release_all_held()

    def record_button_down(self, button: MouseButton) -> None:
        self._held_buttons.add(button)

    def record_button_up(self, button: MouseButton) -> None:
        self._held_buttons.discard(button)

    def record_key_down(self, key: str, modifiers: list[str] | None = None) -> None:
        self._held_keys.add(key)
        if modifiers:
            self._held_modifiers.update(modifiers)

    def record_key_up(self, key: str, modifiers: list[str] | None = None) -> None:
        self._held_keys.discard(key)
        if modifiers:
            for m in modifiers:
                self._held_modifiers.discard(m)
