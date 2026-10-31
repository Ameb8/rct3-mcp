"""Local diagnostic CLI entry point to check permissions, windows, and capture readiness."""

from __future__ import annotations

import platform
import sys

from rct3_control.backend import get_backend
from rct3_control.session import GameSession
from rct3_control.types import RCT3ControlError


def run_diagnostics(target_title: str = "RollerCoaster Tycoon 3") -> int:
    """Run diagnostic checks and print report."""
    print("=" * 60)
    print("RCT3 MCP Local Environment Diagnostics")
    print("=" * 60)

    # 1. Environment facts
    print(f"Platform:     {sys.platform}")
    print(f"Machine arch: {platform.machine()}")
    print(f"Python:       {sys.version.split()[0]}")
    print("-" * 60)

    backend = get_backend()
    backend_name = type(backend).__name__
    print(f"Active Backend: {backend_name}")

    # 2. Permissions
    perms = backend.check_permissions()
    print("Permissions:")
    sr_mark = "✔ OK" if perms.screen_recording else "❌ MISSING"
    ax_mark = "✔ OK" if perms.accessibility else "❌ MISSING"
    print(f"  Screen Recording: {sr_mark}")
    print(f"  Accessibility:    {ax_mark}")
    if perms.details:
        print(f"  Details: {perms.details}")
    print("-" * 60)

    # 3. Windows
    windows = backend.list_windows()
    print(f"Visible Application Windows Found: {len(windows)}")
    target_lower = target_title.lower()
    matches = []
    for w in windows:
        is_match = (
            target_lower in w.title.lower()
            or target_lower in w.owner_name.lower()
            or "rct3" in w.owner_name.lower()
        )
        if is_match:
            matches.append(w)
        print(
            f"  - [{w.window_id}] '{w.title}' (owner: '{w.owner_name}', pid: {w.owner_pid}, "
            f"bounds: {w.bounds.width}x{w.bounds.height} at ({w.bounds.x},{w.bounds.y}), focused: {w.is_focused})"
        )

    print("-" * 60)
    print(f"Game Candidates matching '{target_title}': {len(matches)}")
    for m in matches:
        print(f"  Candidate: ID={m.window_id} Title='{m.title}' Owner='{m.owner_name}'")

    print("-" * 60)

    # 4. Session & Capture Readiness
    session = GameSession(backend=backend, target_title=target_title)
    status = session.get_status()
    print("Status Result:")
    print(
        f"  Selected Window: {status.selected_window.window_id if status.selected_window else 'None'}"
    )
    print(f"  Geometry:        {status.geometry}")
    print(f"  Focus:           {status.focus}")
    print(f"  Stopped:         {status.stopped}")
    if status.actionable_problems:
        print("  Actionable Problems:")
        for p in status.actionable_problems:
            print(f"    - {p}")

    # 5. Test Capture if window present
    if status.selected_window and perms.screen_recording:
        try:
            png_bytes, meta = session.observe()
            print(
                f"\n✔ Test Capture SUCCESS: frame_id={meta.frame_id}, size={meta.width}x{meta.height}, {len(png_bytes)} bytes"
            )
        except RCT3ControlError as e:
            print(f"\n❌ Test Capture FAILED: [{e.code.value}] {e.message}")
            return 1

    print("=" * 60)
    return 0 if not status.actionable_problems else 1


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "RollerCoaster Tycoon 3"
    sys.exit(run_diagnostics(target_title=target))


if __name__ == "__main__":
    main()
