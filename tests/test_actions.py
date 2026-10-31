"""Tests for input actions: click, drag, scroll, press_key, wait, and focus management."""

import pytest

from rct3_control.backend.mock import MockBackend
from rct3_control.session import GameSession
from rct3_control.types import ErrorCode, RCT3ControlError


@pytest.fixture
def mock_backend() -> MockBackend:
    return MockBackend(origin_x=0, origin_y=0, width=1280, height=720, title_bar_height=0)


@pytest.fixture
def session(mock_backend: MockBackend) -> GameSession:
    return GameSession(backend=mock_backend)


@pytest.mark.asyncio
async def test_click_options_and_validation(session: GameSession, mock_backend: MockBackend):
    _, meta = session.observe()
    frame_id = meta.frame_id

    # Left click
    await session.click(frame_id=frame_id, x=100, y=100, button="left", count=1)
    # Right double click
    await session.click(frame_id=frame_id, x=150, y=150, button="right", count=2)

    # Invalid button
    with pytest.raises(RCT3ControlError) as exc_info:
        await session.click(frame_id=frame_id, x=100, y=100, button="invalid")  # type: ignore
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    # Invalid count
    with pytest.raises(RCT3ControlError) as exc_info2:
        await session.click(frame_id=frame_id, x=100, y=100, count=3)
    assert exc_info2.value.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_drag_and_limits(session: GameSession, mock_backend: MockBackend):
    _, meta = session.observe()
    frame_id = meta.frame_id

    # Normal drag
    res = await session.drag(
        frame_id=frame_id,
        start_x=100,
        start_y=100,
        end_x=300,
        end_y=300,
        button="left",
        duration_ms=100,
    )
    assert res["action"] == "drag"

    # Drag duration too short (< 50ms)
    with pytest.raises(RCT3ControlError) as exc_info:
        await session.drag(
            frame_id=frame_id, start_x=100, start_y=100, end_x=200, end_y=200, duration_ms=20
        )
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    # Drag duration too long (> 5000ms)
    with pytest.raises(RCT3ControlError) as exc_info2:
        await session.drag(
            frame_id=frame_id, start_x=100, start_y=100, end_x=200, end_y=200, duration_ms=6000
        )
    assert exc_info2.value.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_scroll_and_limits(session: GameSession, mock_backend: MockBackend):
    _, meta = session.observe()
    frame_id = meta.frame_id

    # Valid scroll
    res = await session.scroll(frame_id=frame_id, x=200, y=200, steps=5)
    assert res["steps"] == 5

    # Out of range steps (> 20)
    with pytest.raises(RCT3ControlError) as exc_info:
        await session.scroll(frame_id=frame_id, x=200, y=200, steps=25)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_press_key_and_hold(session: GameSession, mock_backend: MockBackend):
    _, meta = session.observe()
    frame_id = meta.frame_id

    # Valid key press (Space to pause/resume)
    res = await session.press_key(frame_id=frame_id, key="space", hold_ms=50)
    assert res["key"] == "space"

    # Key down and up recorded in events
    key_events = [ev for ev in mock_backend.events if ev[0] in ("key_down", "key_up")]
    assert any(ev[0] == "key_down" and ev[1]["key"] == "space" for ev in key_events)
    assert any(ev[0] == "key_up" and ev[1]["key"] == "space" for ev in key_events)

    # Out of range hold_ms (< 20ms)
    with pytest.raises(RCT3ControlError) as exc_info:
        await session.press_key(frame_id=frame_id, key="space", hold_ms=10)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_wait_and_limits(session: GameSession):
    # Valid wait
    res = await session.wait(seconds=0.05)
    assert res["seconds"] == 0.05

    # Negative wait
    with pytest.raises(RCT3ControlError) as exc_info:
        await session.wait(seconds=-1.0)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    # Excessive wait (> 30s)
    with pytest.raises(RCT3ControlError) as exc_info2:
        await session.wait(seconds=35.0)
    assert exc_info2.value.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_focus_loss_handling(session: GameSession, mock_backend: MockBackend):
    _, meta = session.observe()
    frame_id = meta.frame_id

    # Mock window unfocused and cannot be focused
    mock_backend.is_focused = False
    mock_backend.focus_window = lambda pid: False

    with pytest.raises(RCT3ControlError) as exc_info:
        await session.click(frame_id=frame_id, x=200, y=200)

    assert exc_info.value.code == ErrorCode.FOCUS_LOST
