"""Tests for stop latching, input serialization, held input cleanup, and fail-safe triggers."""

import asyncio

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
async def test_stop_latch_blocks_input_until_reset(session: GameSession):
    _, meta = session.observe()
    frame_id = meta.frame_id

    # Normal click works
    await session.click(frame_id=frame_id, x=200, y=200)

    # Trigger stop
    res = session.stop()
    assert res["status"] == "stopped"
    assert session.safety.is_stopped

    # Subsequent input should immediately raise STOPPED error
    with pytest.raises(RCT3ControlError) as exc_info:
        await session.click(frame_id=frame_id, x=200, y=200)
    assert exc_info.value.code == ErrorCode.STOPPED

    # Reset stop
    reset_res = session.reset_stop()
    assert reset_res["status"] == "ready"
    assert not session.safety.is_stopped

    # Reset invalidates frame_id, so old frame_id still fails
    with pytest.raises(RCT3ControlError) as exc_info2:
        await session.click(frame_id=frame_id, x=200, y=200)
    assert exc_info2.value.code == ErrorCode.OBSERVATION_REQUIRED

    # New observation allows acting again
    _, new_meta = session.observe()
    await session.click(frame_id=new_meta.frame_id, x=200, y=200)


@pytest.mark.asyncio
async def test_held_inputs_released_on_error(session: GameSession, mock_backend: MockBackend):
    _, meta = session.observe()
    frame_id = meta.frame_id

    # If backend raises an exception during an active drag, held button must be released
    def fail_drag_move(x: int, y: int, button: str = "left"):
        raise RuntimeError("Simulated failure during drag")

    mock_backend.post_mouse_drag_move = fail_drag_move

    with pytest.raises(RuntimeError):
        await session.drag(
            frame_id=frame_id,
            start_x=100,
            start_y=100,
            end_x=300,
            end_y=300,
            duration_ms=100,
        )

    # Held buttons in safety manager must be empty and release_all must have been invoked
    assert len(session.safety._held_buttons) == 0
    release_events = [ev for ev in mock_backend.events if ev[0] == "release_all"]
    assert len(release_events) > 0


@pytest.mark.asyncio
async def test_screen_corner_fail_safe(session: GameSession, mock_backend: MockBackend):
    _, meta = session.observe()
    frame_id = meta.frame_id

    # Move cursor to screen corner (0, 0)
    mock_backend.pointer_x = 0
    mock_backend.pointer_y = 0

    with pytest.raises(RCT3ControlError) as exc_info:
        await session.click(frame_id=frame_id, x=200, y=200)

    assert exc_info.value.code == ErrorCode.STOPPED
    assert session.safety.is_stopped


@pytest.mark.asyncio
async def test_interruption_during_drag(session: GameSession, mock_backend: MockBackend):
    _, meta = session.observe()
    frame_id = meta.frame_id

    async def trigger_stop_soon():
        await asyncio.sleep(0.05)
        session.stop()

    stop_task = asyncio.create_task(trigger_stop_soon())

    with pytest.raises(RCT3ControlError) as exc_info:
        await session.drag(
            frame_id=frame_id,
            start_x=100,
            start_y=100,
            end_x=400,
            end_y=400,
            duration_ms=500,
        )

    await stop_task
    assert exc_info.value.code == ErrorCode.STOPPED
    assert session.safety.is_stopped
    assert len(session.safety._held_buttons) == 0
