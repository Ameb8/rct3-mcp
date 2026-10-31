# Validation Record

## 1. Environment and Execution Context

- **Development/Verification Host**: Linux `pi4` (`aarch64` Debian GNU/Linux 6.12.75)
- **Target Game Environment**: Intel MacBook Pro (`x86_64`), macOS 14+, RollerCoaster Tycoon 3 Complete Edition on Steam.
- **Python Toolchain**: Python 3.12 (`cpython-3.12.13`), `uv` 0.11.32.
- **MCP Framework**: Official Python `mcp` SDK (v2.3.0).

---

## 2. Automated Check Results

All automated checks were executed in the project virtual environment.

### 2.1 Dependencies Installation
```bash
$ uv sync
Resolved 49 packages
Installed: rct3-control, mcp, pillow, pydantic, hatchling, pytest, pytest-asyncio, ruff
Status: PASSED
```

### 2.2 Code Quality & Formatting
```bash
$ uv run ruff check src tests
All checks passed!

$ uv run ruff format --check src tests
9 files already formatted.
Status: PASSED
```

### 2.3 Automated Test Suite
```bash
$ uv run pytest -v
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.2.0, pluggy-1.7.0
rootdir: /home/ameb8/projects/rct3-mcp
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, asyncio-1.4.1

tests/test_actions.py::test_click_options_and_validation PASSED          [  5%]
tests/test_actions.py::test_drag_and_limits PASSED                       [ 10%]
tests/test_actions.py::test_scroll_and_limits PASSED                     [ 15%]
tests/test_actions.py::test_press_key_and_hold PASSED                    [ 21%]
tests/test_actions.py::test_wait_and_limits PASSED                       [ 26%]
tests/test_actions.py::test_focus_loss_handling PASSED                   [ 31%]
tests/test_coordinates.py::test_coordinate_mapping_and_translation PASSED [ 36%]
tests/test_coordinates.py::test_window_resize_invalidates_frame PASSED   [ 42%]
tests/test_coordinates.py::test_bounds_validation_rejects_out_of_bounds PASSED [ 47%]
tests/test_coordinates.py::test_stale_or_invalid_frame_id_rejected PASSED [ 52%]
tests/test_mcp_server.py::test_mcp_tool_discovery PASSED                 [ 57%]
tests/test_mcp_server.py::test_mcp_status_tool PASSED                    [ 63%]
tests/test_mcp_server.py::test_mcp_observe_tool_returns_image_and_metadata PASSED [ 68%]
tests/test_mcp_server.py::test_mcp_input_cycle_through_server PASSED     [ 73%]
tests/test_safety_and_stop.py::test_stop_latch_blocks_input_until_reset PASSED [ 78%]
tests/test_safety_and_stop.py::test_held_inputs_released_on_error PASSED [ 84%]
tests/test_safety_and_stop.py::test_screen_corner_fail_safe PASSED       [ 89%]
tests/test_safety_and_stop.py::test_interruption_during_drag PASSED      [ 94%]
tests/test_stdio_protocol.py::test_stdio_protocol_and_stdout_isolation PASSED [100%]

============================= 19 passed in 16.23s ==============================
Status: PASSED
```

### 2.4 Diagnostic Tool Verification
```bash
$ uv run rct3-diagnostics
============================================================
RCT3 MCP Local Environment Diagnostics
============================================================
Platform:     linux
Machine arch: aarch64
Python:       3.12.13
------------------------------------------------------------
Active Backend: MockBackend
Permissions:
  Screen Recording: ✔ OK
  Accessibility:    ✔ OK
------------------------------------------------------------
Visible Application Windows Found: 1
  - [1001] 'RollerCoaster Tycoon 3' (owner: 'RollerCoaster Tycoon 3', pid: 12345, bounds: 1280x720 at (100,100), focused: True)
------------------------------------------------------------
Game Candidates matching 'RollerCoaster Tycoon 3': 1
  Candidate: ID=1001 Title='RollerCoaster Tycoon 3' Owner='RollerCoaster Tycoon 3'
------------------------------------------------------------
Status Result:
  Selected Window: 1001
  Geometry:        origin_x=100 origin_y=100 width=1280 height=720 scale=1.0 content_rect=Rect(x=0, y=28, width=1280, height=692) has_title_bar=True title_bar_height=28
  Focus:           True
  Stopped:         False

✔ Test Capture SUCCESS: frame_id=92fb1388-339c-4660-b983-415424442751, size=1280x720, 4388 bytes
============================================================
Status: PASSED
```

---

## 3. Acceptance Gates Status

### Gate 1: Actual Game and Host Feasibility
- **Status**: **PENDING LIVE TARGET EXECUTION**
- **Exercised Offline**:
  - Window capture abstraction with explicit image-to-screen coordinate mapping.
  - Coordinate translation on window movement and frame invalidation on resize.
  - Out-of-bounds rejection (including window title bar rejection).
  - MCP stdio server with protocol-compliant JSON-RPC, `status`, `observe` returning inline base64 PNG `ImageContent` and metadata, `move`, `click`, `drag`, `scroll`, `press_key`, `wait`, `stop`, `reset_stop`.
  - Input tracking, cleanup on error, and screen-corner fail-safe abort.
  - Full end-to-end stdio transport subprocess test verifying protocol initialize handshake, tool listing, tool invocation, and strict stdout isolation from logging.
- **Outstanding Live Check on Owner's Mac**:
  - Antigravity CLI is currently running in a Linux terminal on `pi4`. Per SPEC Section 2 ("Agent and server run locally in the owner's logged-in, unlocked GUI session") and Section 4 ("No remote access/SSH daemon use"), live window capture and synthetic input must execute locally on the owner's Intel MacBook Pro where RCT3 is installed.
  - **Required Step**: On the Intel Mac, sync/pull the repo, run `uv run rct3-diagnostics` with RCT3 open in windowed mode, grant Screen Recording and Accessibility permissions, and launch Antigravity CLI with the MCP server to verify live capture, one click, one key press, and one camera drag in the live game.

### Gate 2: Reliable Tool Contract
- **Status**: Not started (Deferred to Section 2 of IMPLEMENTATION.md).

### Gate 3: End-to-End Construction
- **Status**: Not started (Deferred to Section 3 of IMPLEMENTATION.md).
