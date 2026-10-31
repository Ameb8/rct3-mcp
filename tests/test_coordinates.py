"""Tests for coordinate transforms, window movement, resize detection, and bounds validation."""

import pytest

from rct3_control.backend.mock import MockBackend
from rct3_control.session import GameSession
from rct3_control.types import ErrorCode, RCT3ControlError


@pytest.fixture
def mock_backend() -> MockBackend:
    return MockBackend(
        origin_x=100,
        origin_y=200,
        width=1280,
        height=720,
        title_bar_height=28,
    )


@pytest.fixture
def session(mock_backend: MockBackend) -> GameSession:
    return GameSession(backend=mock_backend)


@pytest.mark.asyncio
async def test_coordinate_mapping_and_translation(session: GameSession, mock_backend: MockBackend):
    # Establish observation
    _, meta = session.observe()
    frame_id = meta.frame_id

    # Test click inside valid game content (e.g. x=300, y=100)
    # Origin is (100, 200). Screen coords should be (100 + 300, 200 + 100) = (400, 300)
    res = await session.click(frame_id=frame_id, x=300, y=100)
    assert res["screen_x"] == 400
    assert res["screen_y"] == 300

    # Simulate window moving without resizing (moved to origin 150, 250)
    mock_backend.origin_x = 150
    mock_backend.origin_y = 250

    # Next action with same frame_id should automatically translate using new origin
    res2 = await session.click(frame_id=frame_id, x=300, y=100)
    assert res2["screen_x"] == 450
    assert res2["screen_y"] == 350


@pytest.mark.asyncio
async def test_window_resize_invalidates_frame(session: GameSession, mock_backend: MockBackend):
    _, meta = session.observe()
    frame_id = meta.frame_id

    # Simulate window resize
    mock_backend.width = 1600
    mock_backend.height = 900

    with pytest.raises(RCT3ControlError) as exc_info:
        await session.click(frame_id=frame_id, x=300, y=100)

    assert exc_info.value.code == ErrorCode.OBSERVATION_REQUIRED
    assert "dimensions or scale changed" in exc_info.value.message


@pytest.mark.asyncio
async def test_bounds_validation_rejects_out_of_bounds(session: GameSession):
    _, meta = session.observe()
    frame_id = meta.frame_id

    # Title bar is y: 0..27. Content rect starts at y=28.
    # An action in title bar (e.g. y=10) must be rejected
    with pytest.raises(RCT3ControlError) as exc_info:
        await session.click(frame_id=frame_id, x=100, y=10)
    assert exc_info.value.code == ErrorCode.OUT_OF_BOUNDS

    # Action outside width/height
    with pytest.raises(RCT3ControlError) as exc_info2:
        await session.click(frame_id=frame_id, x=1500, y=400)
    assert exc_info2.value.code == ErrorCode.OUT_OF_BOUNDS

    # Negative coordinates
    with pytest.raises(RCT3ControlError) as exc_info3:
        await session.click(frame_id=frame_id, x=-10, y=100)
    assert exc_info3.value.code == ErrorCode.OUT_OF_BOUNDS


@pytest.mark.asyncio
async def test_stale_or_invalid_frame_id_rejected(session: GameSession):
    session.observe()
    with pytest.raises(RCT3ControlError) as exc_info:
        await session.click(frame_id="stale-invalid-id", x=300, y=100)
    assert exc_info.value.code == ErrorCode.OBSERVATION_REQUIRED
