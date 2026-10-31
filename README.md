# RollerCoaster Tycoon 3 (RCT3) MCP Control

Local computer-control MCP server designed to let Antigravity CLI and vision-capable coding agents interact with native RollerCoaster Tycoon 3 Complete Edition on an Intel Mac.

---

## 1. Prerequisites and Environment

- **Machine**: Intel Mac (`x86_64`) running macOS 14+ (or compatible).
- **Game**: RollerCoaster Tycoon 3 Complete Edition installed via Steam, running natively in **windowed mode**.
- **Python Toolchain**: Python 3.12+ managed by [`uv`](https://docs.astral.sh/uv/).
- **Agent Host**: Antigravity CLI connected via stdio transport.

---

## 2. Installation and Setup

### 2.1 Install dependencies
Clone or place this repository on the machine where RCT3 is installed, and run:
```bash
uv sync
```
This sets up the virtual environment (`.venv`) and installs locked dependencies (`mcp`, `pillow`, `pydantic`, `pyobjc-framework-Quartz`, `pyobjc-framework-Cocoa`, etc.).

### 2.2 macOS Permissions (TCC)
To capture the game window and inject mouse/keyboard events, macOS requires explicit permissions:

1. Open **System Settings > Privacy & Security**.
2. **Screen Recording**:
   - Enable your terminal application (e.g., `Terminal`, `iTerm2`) or the Python runner.
   - Required so the server can capture game window frames.
3. **Accessibility**:
   - Enable your terminal application.
   - Required for synthetic mouse movements, clicks, drags, and key events.

---

## 3. Game and Window Setup

1. Launch Steam and open **RollerCoaster Tycoon 3 Complete Edition**.
2. In the game options, ensure the display is set to **Windowed Mode** (e.g. 1280x720 or a size that comfortably fits your screen).
3. Load a sandbox park or scenario.
4. Ensure the game window remains visible and not minimized.

---

## 4. Diagnostics and Verification

Run the diagnostics command to check macOS permissions, discover the RCT3 game window, verify window geometry, and test window capture:

```bash
uv run rct3-diagnostics
```

Expected diagnostic output includes:
- Platform and architecture
- Screen Recording (`✔ OK`) and Accessibility (`✔ OK`) permissions
- Discovered candidate window ID, title, and bounds
- Geometry scale and content rectangle
- Test capture verification (`✔ Test Capture SUCCESS`)

---

## 5. Starting the MCP Server

The server speaks the Model Context Protocol over `stdio`. Server `stdout` is reserved exclusively for JSON-RPC MCP messages, while operational logs are written to `stderr`.

### Standalone launch:
```bash
uv run rct3-mcp
```

### Antigravity CLI Configuration:
Add the server to your `~/.gemini/config/mcp_config.json` (or use the workspace plugin in `.agents/plugins/rct3-control/`):

```json
{
  "mcpServers": {
    "rct3-control": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/rct3-mcp",
        "rct3-mcp"
      ]
    }
  }
}
```

---

## 6. Exposed MCP Tools

| Tool | Parameters | Description |
| --- | --- | --- |
| `status` | None | Reports permissions, candidate windows, active geometry, focus state, stop status, and actionable issues. |
| `observe` | None | Captures game window and returns an inline PNG image along with metadata (`frame_id`, dimensions, `content_rect`). Establishes a new frame. |
| `move` | `frame_id`, `x`, `y` | Moves pointer to coordinate (in image pixel space within content rect). |
| `click` | `frame_id`, `x`, `y`, `button` (left/right/middle), `count` (1/2) | Moves to point, settles, and clicks. |
| `drag` | `frame_id`, `start_x`, `start_y`, `end_x`, `end_y`, `button`, `duration_ms` (50–5000), `modifiers` | Executes a smooth bounded drag (used for camera panning, placing paths/tracks). |
| `scroll` | `frame_id`, `x`, `y`, `steps` (-20 to 20) | Scrolls vertical wheel at point (used for zooming). |
| `press_key` | `frame_id`, `key`, `modifiers`, `hold_ms` (20–5000) | Presses and releases a key (e.g. `space` to pause/resume, arrow keys, `escape`). |
| `wait` | `seconds` (0.0 to 30.0) | Waits for bounded wall-clock duration while checking for human stop. |
| `stop` | None | Latches the stop state and releases held inputs immediately. |
| `reset_stop` | None | Clears the stop latch and invalidates the frame, requiring a new observation before acting. |

---

## 7. Safety, Human Stop, and Recovery

### Human Interruption Mechanisms:
1. **Screen-Corner Fail-Safe**:
   - Slam or move the mouse cursor to the top-left corner of the primary display `(0, 0)`.
   - The safety manager detects this immediately, latches the stop state, and releases all held buttons and keys within 500 ms.
2. **`stop` MCP Tool**:
   - Calling the `stop` tool halts operations and blocks any further actions until `reset_stop` is called.

### Recovery from Interruption or Stuck Input:
- If an operation is interrupted or an unexpected error occurs, all held keys and mouse buttons are released automatically in a `finally` cleanup block.
- Once stopped, the system rejects all subsequent input commands with `stopped`.
- To resume:
  1. Call `reset_stop` after verifying the game state.
  2. Call `observe` to get a fresh screenshot and a new `frame_id`.
  3. Resume actions using the new `frame_id`.

---

## 8. Development and Automated Checks

Reproducible check commands:

```bash
# Install locked dependencies
uv sync

# Run automated tests (offline / headless without GUI or permissions)
uv run pytest -v

# Run linting
uv run ruff check .

# Run format check
uv run ruff format --check .
```
