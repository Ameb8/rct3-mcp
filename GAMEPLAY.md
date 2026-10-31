# RCT3 Agent Gameplay Guide

Operational instructions for vision-capable agents controlling RollerCoaster Tycoon 3 through the MCP server.

---

## Operating Principles

### 1. Check Readiness and Observe First
- Always begin a session by calling `status` to ensure permissions, window geometry, and focus are valid.
- Call `observe` to capture the current screen and obtain a valid `frame_id`. You cannot send inputs without a `frame_id` matching the current observation frame.

### 2. Take Small, Deliberate Steps
- Execute tasks in single, atomic steps.
- Initially send **one action per observation**. Do not chain unverified actions.
- A successful tool response means input was delivered to macOS, **not** that the game UI changed or accepted a placement.

### 3. Observe and Verify Results Visually
- Always call `observe` after each click, drag, or key press to inspect the game window.
- Verify menus open, icons highlight, or construction previews appear as expected.
- If an action did not produce the intended result, stop and reassess the observation image rather than repeating the same click blindly.

### 4. Coordinate System and Boundaries
- All coordinate parameters `(x, y)` refer to pixel positions within the delivered observation image.
- Only interact with points inside the game content area (avoid window title bars and OS window controls).
- If the game window moves, the server translates coordinates automatically; if the window is resized, `observe` must be called again.

### 5. Pause and Game Speed
- Prefer performing construction and menu navigation while the game is **paused**.
- RCT3 can usually be paused by pressing `space` (or clicking the in-game pause button).
- Confirm the pause state visually from the observation image (e.g. paused text or stationary guests/trees); do not assume pause state solely from a key press.
- Remember that `wait(seconds)` measures real-world wall-clock time, not simulated in-game time.

### 6. Camera Controls
- **Panning**: Drag with the right mouse button (or middle mouse button depending on in-game settings) across a portion of the content view, or use arrow keys (`left`, `right`, `up`, `down`).
- **Zooming**: Use `scroll` with positive steps (zoom in) or negative steps (zoom out).
- Verify facility placement, path alignments, and entrance/exit positions from multiple camera angles if needed.

### 7. Human Interruption and Stop
- If the human user interrupts execution or slams the mouse to the top-left corner `(0, 0)`, the server latches into `STOPPED` state.
- If you receive a `stopped` error:
  1. Cease sending further inputs immediately.
  2. Inform the user and wait for their explicit instruction.
  3. Once authorized by the user, call `reset_stop`.
  4. Call `observe` to obtain a fresh frame and re-evaluate the current game state. Never resume queued actions blindly.

### 8. Park Saving and Demolition
- **Never save, overwrite saves, load parks, or quit the game.** Saving is strictly the responsibility of the owner.
- Avoid destructive demolition of existing rides or scenery unless explicitly instructed by the owner.

### 9. Reporting and Transparency
- Clearly report completed placements, connected paths, and facilities opened.
- Highlight any uncertainties (e.g. uncertain queue path connections or unresolved warnings in dialogs) so the user can verify them.
