"""Local stdio MCP server for RCT3 computer control."""

from __future__ import annotations

import base64
import json
import logging
import sys

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ImageContent, TextContent

from rct3_control.backend import get_backend
from rct3_control.session import GameSession
from rct3_control.types import MouseButton, RCT3ControlError

logger = logging.getLogger("rct3_control.server")


def create_server(session: GameSession | None = None) -> MCPServer:
    """Create and configure the MCP server instance."""
    if session is None:
        session = GameSession(backend=get_backend())

    server = MCPServer(name="rct3-control")

    @server.tool(
        name="status",
        description=(
            "Report capture/input permissions, selected RCT3 window, geometry, "
            "focus state, human stop latch status, and actionable problems. Injects no input."
        ),
    )
    def status() -> CallToolResult:
        res = session.get_status()
        text = json.dumps(res.model_dump(), indent=2)
        return CallToolResult(content=[TextContent(type="text", text=text)])

    @server.tool(
        name="observe",
        description=(
            "Capture the full game window and return an inline PNG image alongside "
            "frame metadata (frame_id, dimensions, content_rect, scale). "
            "Establishes a new frame required for subsequent input tools."
        ),
    )
    def observe() -> CallToolResult:
        try:
            png_bytes, metadata = session.observe()
            b64_data = base64.b64encode(png_bytes).decode("ascii")
            meta_json = json.dumps(metadata.model_dump(), indent=2)
            return CallToolResult(
                content=[
                    ImageContent(type="image", data=b64_data, mime_type="image/png"),
                    TextContent(
                        type="text",
                        text=f"Frame established successfully:\n{meta_json}",
                    ),
                ]
            )
        except RCT3ControlError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(e.to_dict(), indent=2))],
                is_error=True,
            )

    @server.tool(
        name="move",
        description=(
            "Move pointer to (x, y) within the game content rectangle. "
            "Coordinates refer to the last returned observation image pixel coordinates. "
            "Requires current frame_id."
        ),
    )
    async def move(frame_id: str, x: int, y: int) -> CallToolResult:
        try:
            res = await session.move(frame_id=frame_id, x=x, y=y)
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(res, indent=2))]
            )
        except RCT3ControlError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(e.to_dict(), indent=2))],
                is_error=True,
            )

    @server.tool(
        name="click",
        description=(
            "Move to (x, y), settle, and click. "
            "x, y: integer image pixels within game content. "
            "button: 'left', 'right', or 'middle' (default 'left'). "
            "count: 1 or 2 (default 1). "
            "Requires current frame_id."
        ),
    )
    async def click(
        frame_id: str,
        x: int,
        y: int,
        button: MouseButton = "left",
        count: int = 1,
    ) -> CallToolResult:
        try:
            res = await session.click(frame_id=frame_id, x=x, y=y, button=button, count=count)
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(res, indent=2))]
            )
        except RCT3ControlError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(e.to_dict(), indent=2))],
                is_error=True,
            )

    @server.tool(
        name="drag",
        description=(
            "Perform a smooth bounded drag from (start_x, start_y) to (end_x, end_y). "
            "duration_ms: duration in milliseconds (50 to 5000 ms, default 400). "
            "button: 'left', 'right', or 'middle' (default 'left'). "
            "Requires current frame_id."
        ),
    )
    async def drag(
        frame_id: str,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: MouseButton = "left",
        duration_ms: int = 400,
        modifiers: list[str] | None = None,
    ) -> CallToolResult:
        try:
            res = await session.drag(
                frame_id=frame_id,
                start_x=start_x,
                start_y=start_y,
                end_x=end_x,
                end_y=end_y,
                button=button,
                duration_ms=duration_ms,
                modifiers=modifiers,
            )
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(res, indent=2))]
            )
        except RCT3ControlError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(e.to_dict(), indent=2))],
                is_error=True,
            )

    @server.tool(
        name="scroll",
        description=(
            "Move pointer to (x, y) and scroll vertical wheel. "
            "steps: signed integer between -20 and 20 (positive scrolls up/zoom in, negative scrolls down/zoom out). "
            "Requires current frame_id."
        ),
    )
    async def scroll(frame_id: str, x: int, y: int, steps: int) -> CallToolResult:
        try:
            res = await session.scroll(frame_id=frame_id, x=x, y=y, steps=steps)
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(res, indent=2))]
            )
        except RCT3ControlError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(e.to_dict(), indent=2))],
                is_error=True,
            )

    @server.tool(
        name="press_key",
        description=(
            "Press a key or chord for a bounded interval, then release everything pressed. "
            "key: key name (e.g. 'space', 'escape', 'return', 'left', 'right', 'up', 'down', 'p'). "
            "modifiers: optional list ('shift', 'control', 'option', 'command'). "
            "hold_ms: bounded hold time (20 to 5000 ms, default 80). "
            "Requires current frame_id."
        ),
    )
    async def press_key(
        frame_id: str,
        key: str,
        modifiers: list[str] | None = None,
        hold_ms: int = 80,
    ) -> CallToolResult:
        try:
            res = await session.press_key(
                frame_id=frame_id, key=key, modifiers=modifiers, hold_ms=hold_ms
            )
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(res, indent=2))]
            )
        except RCT3ControlError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(e.to_dict(), indent=2))],
                is_error=True,
            )

    @server.tool(
        name="wait",
        description=(
            "Wait for bounded wall-clock seconds (0.0 to 30.0 s) checking human interruption. "
            "Does not simulate in-game passage of time if paused."
        ),
    )
    async def wait(seconds: float) -> CallToolResult:
        try:
            res = await session.wait(seconds=seconds)
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(res, indent=2))]
            )
        except RCT3ControlError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(e.to_dict(), indent=2))],
                is_error=True,
            )

    @server.tool(
        name="stop",
        description=(
            "Latch the human stop state and immediately release any held input. "
            "Blocks any subsequent input until reset_stop is called."
        ),
    )
    def stop() -> CallToolResult:
        res = session.stop()
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(res, indent=2))])

    @server.tool(
        name="reset_stop",
        description=(
            "Clear the stop latch after human confirmation. "
            "Invalidates the current frame so a new observation is required before further input."
        ),
    )
    def reset_stop() -> CallToolResult:
        res = session.reset_stop()
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(res, indent=2))])

    return server


def main() -> None:
    """Run the stdio MCP server."""
    # Ensure all diagnostic and ordinary logs go strictly to stderr
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Starting RCT3 MCP server on stdio...")
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
