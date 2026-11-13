"""Platform backend factory."""

from __future__ import annotations

import os
import sys

from rct3_control.backend.mock import MockBackend
from rct3_control.backend.protocol import PlatformBackend


def get_backend(prefer_mock: bool = False) -> PlatformBackend:
    """Return platform backend based on operating system and configuration."""
    if prefer_mock or os.environ.get("RCT3_MOCK_BACKEND") == "1" or sys.platform != "darwin":
        return MockBackend()

    try:
        from rct3_control.backend.macos import MacOSBackend

        return MacOSBackend()
    except (ImportError, OSError, RuntimeError):
        return MockBackend()
