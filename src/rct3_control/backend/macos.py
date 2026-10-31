"""macOS implementation for window capture, input synthesis, and permissions."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile

from PIL import Image

from rct3_control.backend.protocol import PlatformBackend
from rct3_control.types import (
    ErrorCode,
    MouseButton,
    PermissionStatus,
    RCT3ControlError,
    Rect,
    WindowGeometry,
    WindowInfo,
)

# Carbon virtual keycode mapping for standard macOS keyboards
KEY_MAP: dict[str, int] = {
    # Control / navigation keys
    "escape": 53,
    "esc": 53,
    "return": 36,
    "enter": 36,
    "tab": 48,
    "space": 49,
    "backspace": 51,
    "delete": 51,
    "forwarddelete": 117,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
    "pageup": 116,
    "pagedown": 121,
    "home": 115,
    "end": 119,
    # Letter keys
    "a": 0,
    "b": 11,
    "c": 8,
    "d": 2,
    "e": 14,
    "f": 3,
    "g": 5,
    "h": 4,
    "i": 34,
    "j": 38,
    "k": 40,
    "l": 37,
    "m": 46,
    "n": 45,
    "o": 31,
    "p": 35,
    "q": 12,
    "r": 15,
    "s": 1,
    "t": 17,
    "u": 32,
    "v": 9,
    "w": 13,
    "x": 7,
    "y": 16,
    "z": 6,
    # Number keys
    "0": 29,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "5": 23,
    "6": 22,
    "7": 26,
    "8": 28,
    "9": 25,
    # Punctuation / symbols
    "-": 27,
    "=": 24,
    "[": 33,
    "]": 30,
    ";": 41,
    "'": 39,
    "\\": 42,
    ",": 43,
    ".": 47,
    "/": 44,
}

MODIFIER_FLAG_MAP: dict[str, int] = {
    "shift": 0x00020000,
    "control": 0x00040000,
    "ctrl": 0x00040000,
    "option": 0x00080000,
    "alt": 0x00080000,
    "command": 0x00100000,
    "cmd": 0x00100000,
}


class MacOSBackend(PlatformBackend):
    """Native macOS backend using Quartz, AppKit, and CoreGraphics APIs."""

    def __init__(self, target_title_substr: str = "RollerCoaster Tycoon 3"):
        self.target_title_substr = target_title_substr
        self._quartz = None
        self._appkit = None
        self._app_services = None
        self._init_libraries()

    def _init_libraries(self) -> None:
        if sys.platform != "darwin":
            return
        try:
            import Quartz

            self._quartz = Quartz
        except ImportError:
            pass
        try:
            import AppKit

            self._appkit = AppKit
        except ImportError:
            pass
        try:
            import ApplicationServices

            self._app_services = ApplicationServices
        except ImportError:
            pass

    def check_permissions(self) -> PermissionStatus:
        screen_ok = False
        accessibility_ok = False
        details = []

        if sys.platform != "darwin":
            return PermissionStatus(
                screen_recording=False,
                accessibility=False,
                details="Not running on macOS; native permissions unavailable.",
            )

        # Accessibility check
        if self._app_services:
            accessibility_ok = bool(self._app_services.AXIsProcessTrusted())
        else:
            # Fallback to checking via osascript
            res = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to return true'],
                check=False,
                capture_output=True,
                text=True,
            )
            accessibility_ok = res.returncode == 0

        if not accessibility_ok:
            details.append(
                "Accessibility permission missing. Grant permission to your terminal/Python in System Settings > Privacy & Security > Accessibility."
            )

        # Screen Recording check
        if self._quartz:
            try:
                if hasattr(self._quartz, "CGPreflightScreenCaptureAccess"):
                    screen_ok = bool(self._quartz.CGPreflightScreenCaptureAccess())
                else:
                    screen_ok = True
            except (AttributeError, OSError, RuntimeError):
                screen_ok = False
        else:
            with tempfile.NamedTemporaryFile(suffix=".png") as tf:
                res = subprocess.run(
                    ["screencapture", "-x", "-R0,0,1,1", tf.name],
                    check=False,
                    capture_output=True,
                )
                screen_ok = (res.returncode == 0) and os.path.getsize(tf.name) > 0

        if not screen_ok:
            details.append(
                "Screen Recording permission missing. Grant permission in System Settings > Privacy & Security > Screen Recording."
            )

        return PermissionStatus(
            screen_recording=screen_ok,
            accessibility=accessibility_ok,
            details=" ".join(details),
        )

    def list_windows(self) -> list[WindowInfo]:
        if not self._quartz:
            return []

        window_list = self._quartz.CGWindowListCopyWindowInfo(1 | 16, 0)
        if not window_list:
            return []

        results: list[WindowInfo] = []
        front_pid = None
        if self._appkit:
            front_app = self._appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
            if front_app:
                front_pid = front_app.processIdentifier()

        for win in window_list:
            bounds_dict = win.get("kCGWindowBounds", {})
            rect = Rect(
                x=int(bounds_dict.get("X", 0)),
                y=int(bounds_dict.get("Y", 0)),
                width=int(bounds_dict.get("Width", 0)),
                height=int(bounds_dict.get("Height", 0)),
            )
            pid = int(win.get("kCGWindowOwnerPID", 0))
            layer = int(win.get("kCGWindowLayer", 0))

            if layer != 0 or rect.width < 100 or rect.height < 100:
                continue

            results.append(
                WindowInfo(
                    window_id=int(win.get("kCGWindowNumber", 0)),
                    owner_name=str(win.get("kCGWindowOwnerName", "")),
                    owner_pid=pid,
                    title=str(win.get("kCGWindowName", "") or ""),
                    bounds=rect,
                    is_focused=(front_pid is not None and pid == front_pid),
                    layer=layer,
                )
            )
        return results

    def get_window_geometry(self, window_id: int) -> WindowGeometry | None:
        windows = self.list_windows()
        for win in windows:
            if win.window_id == window_id:
                title_bar_h = 28
                content_rect = Rect(
                    x=0,
                    y=title_bar_h,
                    width=win.bounds.width,
                    height=max(0, win.bounds.height - title_bar_h),
                )
                return WindowGeometry(
                    origin_x=win.bounds.x,
                    origin_y=win.bounds.y,
                    width=win.bounds.width,
                    height=win.bounds.height,
                    scale=1.0,
                    content_rect=content_rect,
                    has_title_bar=True,
                    title_bar_height=title_bar_h,
                )
        return None

    def capture_window(self, window_id: int) -> tuple[bytes, WindowGeometry]:
        geo = self.get_window_geometry(window_id)
        if geo is None:
            raise RCT3ControlError(
                ErrorCode.WINDOW_UNAVAILABLE,
                f"Window {window_id} could not be found to capture.",
                "Ensure RCT3 is running and visible.",
            )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp_path = tf.name

        try:
            cmd = ["screencapture", "-l", str(window_id), "-x", "-o", tmp_path]
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                with open(tmp_path, "rb") as f:
                    png_bytes = f.read()

                with Image.open(io.BytesIO(png_bytes)) as img:
                    img_w, _ = img.size
                    scale = img_w / geo.width if geo.width > 0 else 1.0
                    geo.scale = scale
                    geo.content_rect = Rect(
                        x=int(geo.content_rect.x * scale),
                        y=int(geo.content_rect.y * scale),
                        width=int(geo.content_rect.width * scale),
                        height=int(geo.content_rect.height * scale),
                    )

                return png_bytes, geo
            else:
                raise RCT3ControlError(
                    ErrorCode.CAPTURE_FAILED,
                    f"screencapture failed: {proc.stderr.strip()}",
                    "Check Screen Recording permissions.",
                )
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def focus_window(self, pid: int) -> bool:
        if self._appkit:
            app = self._appkit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            if app:
                return bool(app.activateWithOptions_(2))
        return False

    def is_window_focused(self, pid: int) -> bool:
        if self._appkit:
            front = self._appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
            return bool(front and front.processIdentifier() == pid)
        return False

    def get_pointer_position(self) -> tuple[int, int]:
        if self._quartz:
            event = self._quartz.CGEventCreate(None)
            if event:
                loc = self._quartz.CGEventGetLocation(event)
                return (int(loc.x), int(loc.y))
        return (0, 0)

    def post_mouse_move(self, x: int, y: int) -> None:
        if not self._quartz:
            return
        point = self._quartz.CGPoint(x=float(x), y=float(y))
        event = self._quartz.CGEventCreateMouseEvent(None, 5, point, 0)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, event)

    def post_mouse_down(self, x: int, y: int, button: MouseButton = "left") -> None:
        if not self._quartz:
            return
        point = self._quartz.CGPoint(x=float(x), y=float(y))
        event_type, btn_num = self._mouse_button_mapping(button, is_down=True)
        event = self._quartz.CGEventCreateMouseEvent(None, event_type, point, btn_num)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, event)

    def post_mouse_up(self, x: int, y: int, button: MouseButton = "left") -> None:
        if not self._quartz:
            return
        point = self._quartz.CGPoint(x=float(x), y=float(y))
        event_type, btn_num = self._mouse_button_mapping(button, is_down=False)
        event = self._quartz.CGEventCreateMouseEvent(None, event_type, point, btn_num)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, event)

    def post_mouse_click(
        self, x: int, y: int, button: MouseButton = "left", count: int = 1
    ) -> None:
        if not self._quartz:
            return
        point = self._quartz.CGPoint(x=float(x), y=float(y))
        down_type, btn_num = self._mouse_button_mapping(button, is_down=True)
        up_type, _ = self._mouse_button_mapping(button, is_down=False)

        for c in range(1, count + 1):
            down_ev = self._quartz.CGEventCreateMouseEvent(None, down_type, point, btn_num)
            self._quartz.CGEventSetIntegerValueField(
                down_ev, self._quartz.kCGMouseEventClickState, c
            )
            self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, down_ev)

            up_ev = self._quartz.CGEventCreateMouseEvent(None, up_type, point, btn_num)
            self._quartz.CGEventSetIntegerValueField(up_ev, self._quartz.kCGMouseEventClickState, c)
            self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, up_ev)

    def post_mouse_drag_move(self, x: int, y: int, button: MouseButton = "left") -> None:
        if not self._quartz:
            return
        point = self._quartz.CGPoint(x=float(x), y=float(y))
        if button == "left":
            event_type = 6
            btn_num = 0
        elif button == "right":
            event_type = 7
            btn_num = 1
        else:
            event_type = 27
            btn_num = 2
        event = self._quartz.CGEventCreateMouseEvent(None, event_type, point, btn_num)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, event)

    def post_scroll(self, x: int, y: int, steps: int) -> None:
        if not self._quartz:
            return
        self.post_mouse_move(x, y)
        event = self._quartz.CGEventCreateScrollWheelEvent(None, 1, 1, steps)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, event)

    def post_key_down(self, key: str, modifiers: list[str] | None = None) -> None:
        if not self._quartz:
            return
        keycode = KEY_MAP.get(key.lower())
        if keycode is None:
            raise RCT3ControlError(
                ErrorCode.UNSUPPORTED_KEY_OR_TEXT,
                f"Unsupported key: {key}",
                f"Supported keys include: {', '.join(list(KEY_MAP.keys())[:15])}...",
            )
        event = self._quartz.CGEventCreateKeyboardEvent(None, keycode, True)
        if modifiers:
            flags = 0
            for m in modifiers:
                flags |= MODIFIER_FLAG_MAP.get(m.lower(), 0)
            self._quartz.CGEventSetFlags(event, flags)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, event)

    def post_key_up(self, key: str, modifiers: list[str] | None = None) -> None:
        if not self._quartz:
            return
        keycode = KEY_MAP.get(key.lower())
        if keycode is None:
            return
        event = self._quartz.CGEventCreateKeyboardEvent(None, keycode, False)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, event)

    def release_all(self) -> None:
        if not self._quartz:
            return
        loc = self.get_pointer_position()
        point = self._quartz.CGPoint(x=float(loc[0]), y=float(loc[1]))
        up_ev_left = self._quartz.CGEventCreateMouseEvent(None, 2, point, 0)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, up_ev_left)
        up_ev_right = self._quartz.CGEventCreateMouseEvent(None, 4, point, 1)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, up_ev_right)
        up_ev_mid = self._quartz.CGEventCreateMouseEvent(None, 26, point, 2)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, up_ev_mid)

    def _mouse_button_mapping(self, button: MouseButton, is_down: bool) -> tuple[int, int]:
        if button == "left":
            return (1 if is_down else 2, 0)
        elif button == "right":
            return (3 if is_down else 4, 1)
        else:
            return (25 if is_down else 26, 2)
