"""Integration tests for the MCP Server: tool discovery, execution, and image return."""

import json

import pytest
from mcp_types import ImageContent, TextContent

from rct3_control.backend.mock import MockBackend
from rct3_control.server import create_server
from rct3_control.session import GameSession


@pytest.fixture
def mock_session() -> GameSession:
    backend = MockBackend(origin_x=50, origin_y=50, width=1280, height=720, title_bar_height=28)
    return GameSession(backend=backend)


@pytest.mark.asyncio
async def test_mcp_tool_discovery(mock_session: GameSession):
    server = create_server(session=mock_session)
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}

    expected_tools = {
        "status",
        "observe",
        "move",
        "click",
        "drag",
        "scroll",
        "press_key",
        "wait",
        "stop",
        "reset_stop",
    }
    assert expected_tools.issubset(tool_names)


@pytest.mark.asyncio
async def test_mcp_status_tool(mock_session: GameSession):
    server = create_server(session=mock_session)
    result = await server.call_tool("status", {})
    assert not result.is_error
    text_content = result.content[0]
    assert isinstance(text_content, TextContent)
    data = json.loads(text_content.text)

    assert data["permissions"]["screen_recording"] is True
    assert data["permissions"]["accessibility"] is True
    assert data["selected_window"]["window_id"] == 1001


@pytest.mark.asyncio
async def test_mcp_observe_tool_returns_image_and_metadata(mock_session: GameSession):
    server = create_server(session=mock_session)
    result = await server.call_tool("observe", {})
    assert not result.is_error

    # Must contain both ImageContent and TextContent
    img_blocks = [c for c in result.content if isinstance(c, ImageContent)]
    text_blocks = [c for c in result.content if isinstance(c, TextContent)]

    assert len(img_blocks) == 1
    assert img_blocks[0].mime_type == "image/png"
    assert len(img_blocks[0].data) > 0  # base64 data

    assert len(text_blocks) == 1
    assert "Frame established successfully" in text_blocks[0].text
    assert mock_session.current_frame_id is not None


@pytest.mark.asyncio
async def test_mcp_input_cycle_through_server(mock_session: GameSession):
    server = create_server(session=mock_session)

    # 1. Observe to establish frame
    obs_res = await server.call_tool("observe", {})
    assert not obs_res.is_error
    frame_id = mock_session.current_frame_id
    assert frame_id is not None

    # 2. Click through server
    click_res = await server.call_tool("click", {"frame_id": frame_id, "x": 300, "y": 150})
    assert not click_res.is_error
    click_data = json.loads(click_res.content[0].text)
    assert click_data["action"] == "click"
    assert click_data["x"] == 300

    # 3. Drag through server
    drag_res = await server.call_tool(
        "drag",
        {
            "frame_id": frame_id,
            "start_x": 200,
            "start_y": 200,
            "end_x": 400,
            "end_y": 400,
            "duration_ms": 100,
        },
    )
    assert not drag_res.is_error
    drag_data = json.loads(drag_res.content[0].text)
    assert drag_data["action"] == "drag"

    # 4. Press key through server
    key_res = await server.call_tool(
        "press_key", {"frame_id": frame_id, "key": "space", "hold_ms": 60}
    )
    assert not key_res.is_error
    key_data = json.loads(key_res.content[0].text)
    assert key_data["action"] == "press_key"

    # 5. Stop through server
    stop_res = await server.call_tool("stop", {})
    assert not stop_res.is_error
    stop_data = json.loads(stop_res.content[0].text)
    assert stop_data["status"] == "stopped"

    # 6. Click after stop should report stopped error
    click_blocked = await server.call_tool("click", {"frame_id": frame_id, "x": 300, "y": 150})
    assert click_blocked.is_error
    error_data = json.loads(click_blocked.content[0].text)
    assert error_data["error_code"] == "stopped"

    # 7. Reset stop
    reset_res = await server.call_tool("reset_stop", {})
    assert not reset_res.is_error
    reset_data = json.loads(reset_res.content[0].text)
    assert reset_data["status"] == "ready"
