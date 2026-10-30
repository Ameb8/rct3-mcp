# RCT3 local computer-control tools

Status: implementation specification, ready for a coding agent.

## 1. Authority and purpose

This document defines the v1 implementation and acceptance criteria. It takes
precedence over `rct3-mcp.md`, which is background reference only. Requirements
from that walkthrough are not requirements here unless repeated in this spec.

Build a small local tool that lets a vision-capable agent follow the owner's
instructions to create things in RollerCoaster Tycoon 3 on the owner's Mac.
This is for personal use on one existing installation, not distribution or
production deployment.

The first agent host is Antigravity CLI. Expose controls through a local MCP
server using stdio. Keep game-control code independent of the MCP adapter so
another MCP host can use it and a CLI could be added later. Do not implement a
second full command interface or a provider abstraction in v1.

The agent interprets screenshots, chooses actions, and checks the results. The
server supplies reliable observation and input; it does not plan park layouts
or decide what to build.

## 2. Supported environment and starting condition

Confirmed by the owner or local inspection:

- Intel MacBook Pro; architecture `x86_64`.
- macOS 14.6.1 at specification time.
- RollerCoaster Tycoon 3 Complete Edition installed through Steam.
- The owner can already launch and play the game directly, without Wine or
  CrossOver.
- Agent and server run locally in the owner's logged-in, unlocked GUI session.

Support this working native installation first. Discover and record its actual
application identity, window identity, and relevant input bindings during setup.
Do not implement support for other game editions, operating systems, or runtimes.

The owner manually launches the game, loads a park or scenario, and leaves the
game in windowed mode. Use a fixed window size that fits the current display;
record the actual working size rather than requiring 1280 by 720. Initially
validate on one display; supporting other display arrangements is not a gate.

The agent has exclusive use of the mouse and keyboard while operating. The owner
can interrupt it. The display must remain awake and the GUI session unlocked;
document a session-scoped way to keep it awake. Do not change global sleep or
security settings automatically.

## 3. User-visible goals

Given ordinary natural-language instructions and a manually loaded park, an
agent must be able to use the tools to:

- Navigate construction menus and select available items.
- Place flat rides, including choosing orientation and placing entrances/exits.
- Place shops beside paths.
- Build paths and ride queue connections as needed.
- Place scenery.
- Move, rotate, and zoom the camera to inspect or reach a placement location.
- Inspect a placed facility and open it when the task calls for that.
- Observe the result and recover from an unsuccessful placement or an ordinary
  in-game dialog by reassessing the screen.

These are tasks performed by the agent using general controls, not dedicated
server functions such as `build_shop` or `connect_path`.

The owner handles saving. Do not implement automatic saving, save backups,
loading parks, or filesystem access to game saves. Gameplay guidance must tell
the agent not to save, load, quit, or overwrite a park unless explicitly asked.

## 4. Exclusions

The following are not required for v1:

- Custom coaster track construction or autonomous whole-park management.
- OCR, structured cash/guest/rating extraction, template matching, or a template
  library.
- A macro engine, action DSL, recorded scripts, or configurable gameplay plans.
- Memory inspection, game-file editing, or reverse engineering game state.
- Remote access, HTTP hosting, authentication, daemon installation, or SSH use.
- Separate operating-system accounts or additional application sandboxing.
- Broad compatibility layers, packaging for release, or installers.
- Guaranteed operation while minimized, obscured, locked, or unattended for hours.

Do not add these preemptively. If a required acceptance task exposes a concrete
limitation, first try a small change to the observation/input tools or gameplay
instructions. Explain any proposed substantial scope expansion before doing it.

## 5. Architecture and implementation discretion

Use Python, `uv` for the environment, a maintained Python MCP SDK, and macOS
capture/input APIs or utilities as appropriate. Verify compatibility on this
machine. Pin resolved dependencies in the lockfile.

Keep three responsibilities separable:

1. Locate the selected game window and capture its contents.
2. Validate and execute mouse/keyboard input.
3. Expose those operations through MCP with images and structured metadata.

A small package is sufficient. Choose module layout and libraries based on the
working implementation; the file-by-file architecture in the old walkthrough
is not binding. Add only dependencies needed for current requirements.

The implementation agent may choose capture backend, event timing, internal
types, and test tooling. It must empirically verify capture, coordinate mapping,
and game response rather than treating suggested APIs as proven to work.

There is no model API client, provider API key, or LLM dependency in the server.
The external agent host provides vision and reasoning.

## 6. Window and coordinate contract

All tool coordinates refer to the most recently returned observation image:

- Origin is the image's top-left; x increases rightward and y downward.
- Coordinates are integer image pixels, never unexplained desktop coordinates.
- Return the full game-window image at one consistent documented scale, without
  silent per-response downscaling. If normalization is used, map all input
  through the same transform.
- State whether window decorations are included. Exclude them if practical;
  otherwise identify the game-content rectangle and reject inputs into title
  bar/window controls.
- Include width, height, game-content rectangle, capture time, and `frame_id`
  alongside the image. The capture and its geometry must describe the same
  window state.
- Re-query the selected window before acting. If it moved without resizing,
  translate coordinates using its current origin. If its dimensions or capture
  scale changed, reject the action with `observation_required` until a new
  observation has been obtained.

Each successful observation establishes the current frame. Tools that inject
input require `frame_id` matching that current frame, binding coordinates to a
specific image. This is a geometry/evidence check, not a guarantee that an
animating game has remained unchanged. The agent must observe frequently.

Identify the game narrowly using its discovered application/process/window
identity. Never silently switch to an unrelated window. If multiple game
windows are plausible, report the ambiguity and provide a simple way to select
one. If the selected window closes or its identity becomes invalid, require
reselection and a new observation before further input.

## 7. MCP tools

Use the following small tool surface. Tool descriptions must explain units,
defaults, limits, and coordinate semantics. All operations have finite timeouts.

| Tool | Inputs | Behavior/result |
| --- | --- | --- |
| `status` | None | Report capture/input permissions, selected window, geometry, focus, stop state, and actionable problems. No injected input. |
| `observe` | None | Return an MCP image content block plus the frame metadata from section 6. No OCR or model-generated interpretation. |
| `move` | `frame_id`, `x`, `y` | Move the pointer within game content; supports hover inspection. |
| `click` | `frame_id`, `x`, `y`, optional `button`, optional `count` | Move to the point, settle, and click; left/right/middle; count 1 or 2. |
| `drag` | `frame_id`, start/end coordinates, optional `button`, `duration_ms`, `modifiers` | Move to the start, press, send intermediate drag events, and release. |
| `scroll` | `frame_id`, `x`, `y`, signed `steps` | Move to the point and scroll vertically. Document direction and verify it in-game. |
| `press_key` | `frame_id`, `key`, optional `modifiers`, `hold_ms` | Press a key/chord for a bounded interval, then release everything it pressed. |
| `type_text` | `frame_id`, `text` | Enter text into an already focused in-game field. Report unsupported characters clearly. |
| `wait` | `seconds` | Wait for bounded wall-clock time, checking interruption. Does not claim to measure simulated game time. |
| `stop` | None | Latch the stopped state and initiate release of held input. Available during an active operation. |
| `reset_stop` | None | Clear the latch without resuming any prior action; invalidate the current frame so a new observation is required. |

Successful input results report the executed action and its relevant parameters.
They mean input was delivered, not that the game accepted a placement. They do
not need to include another image; the agent calls `observe` to check results.

Defaults and limits:

- Click button defaults to left and count to 1.
- Drag defaults to left button and 400 ms; allowed duration 50–5000 ms.
- Key hold defaults to 80 ms; allowed duration 20–5000 ms.
- Wait duration is 0–30 seconds.
- Scroll is limited to 20 steps in either direction per call.
- Text is limited to 256 characters per call; no automatic Enter after text.
- Support key names needed for navigation and the actual game bindings,
  including arrows, Escape, Enter, Tab, Space, editing keys, letters, digits,
  and modifiers. Document keyboard-layout assumptions and tested text support.
- Do not expose unpaired key-down/key-up or button-down/button-up tools.

If empirical game behavior requires different timings, tune defaults and
document the reason. Do not remove finite hold limits.

## 8. Execution, interruption, and errors

Serialize ordinary operations so multiple calls cannot interleave mouse/key
events. `stop` and the human interruption mechanism must remain effective during
an active drag, key hold, or wait; they must not sit behind the ordinary queue.

Before input, verify permissions, window identity, current geometry, content
bounds, stop state, and the supplied frame ID. Focus the selected game once if
needed; verify focus before input. If focus is subsequently lost during an
operation, abort rather than repeatedly fighting the user for focus.

Validate complete action arguments before pressing anything. Never blindly
retry an input action after an error because it may already have taken effect.
Errors during partial execution must say that partial input may have occurred
and that the agent should observe before continuing.

Track held buttons, keys, and modifiers. Release them on completion, handled
errors, MCP cancellation, stop, and graceful process termination. Cleanup must
not be blocked by normal input guards. Do not claim cleanup is guaranteed after
SIGKILL, interpreter crashes, or operating-system failure; document recovery.

Provide one human stop mechanism independent of the agent's next tool call:
prefer a tested global keyboard shortcut; a tested screen-corner mechanism is
an acceptable fallback. Document the exact gesture in the README. It must latch
the stopped state and attempt release within 500 ms under normal operating
conditions. After the owner interrupts, gameplay instructions require the agent
to stop and wait for the owner's explicit instruction before clearing the latch.

Use stable error codes with concise messages and a practical recovery hint:

- `permission_missing`
- `window_not_found` / `window_ambiguous` / `window_unavailable`
- `focus_lost`
- `observation_required`
- `invalid_argument` / `out_of_bounds` / `unsupported_key_or_text`
- `stopped` / `cancelled` / `timeout`
- `capture_failed` / `input_failed` / `internal_error`

Use MCP tool-error responses for execution failures, preserving structured
details where the SDK permits. Reserve stdout for MCP protocol traffic; send
diagnostics to stderr. Do not mislabel every dark or blank image as a permission
failure: distinguish known permission problems from failed or unusable captures.

## 9. Observation, configuration, and diagnostics

Return screenshots inline as MCP image content, not only local file paths. The
first host integration gate must prove that Antigravity CLI's agent can use
those images to identify a visible control and act on it.

Keep configuration minimal: game/window selection, capture settings if needed,
input timing, and interruption settings. A small local file is sufficient.
Reject invalid settings with useful messages. Do not require the owner to
populate unused OCR regions, templates, save paths, or macros.

Provide a simple local diagnostic entry point that reports permissions, candidate
windows, selected geometry, and capture readiness. This is not a requirement to
duplicate all MCP tools as CLI commands.

During validation, retain representative screenshots and a concise action/error
log under a gitignored local runs directory. Include timestamps, frame IDs, and
action outcomes. Document how to disable capture retention and delete run data;
do not build a logging service. Never commit personal park screenshots or local
machine paths by default.

## 10. Gameplay instructions

Ship a short `GAMEPLAY.md` for the controlling agent, separate from development
instructions. Cover:

1. Check readiness and obtain/view an observation before acting.
2. Follow the owner's requested construction task using small steps.
3. Observe after every meaningful UI transition or placement; initially use one
   action per observation. A key press or click is not proof of gameplay success.
4. If an action fails or the result is uncertain, observe and reassess rather
   than repeatedly sending the same action.
5. Use camera controls as needed and verify paths/entrances/exits visually.
6. Prefer construction while paused if live testing confirms it works. Otherwise
   use the slowest practical speed and short action bursts. Do not assume a
   pause state from a key toggle alone.
7. Treat waits as wall-clock time. Pause/speed controls are ordinary UI actions;
   no verified pause/resume or simulated-time tools are required in v1.
8. On human interruption, stop and wait for explicit instructions. After reset,
   obtain a new observation and reassess rather than resume a queued action.
9. Leave saving to the owner. Avoid destructive demolition unless the task
   requires it or the owner authorizes it.
10. Report completed work, unfinished connections/facilities, and uncertainties.

## 11. Implementation milestones and acceptance gates

Follow these gates in order. Complete useful offline work while waiting for
necessary human setup, but do not declare live gates passed without evidence.

### Gate 1: actual game and host feasibility

- Record game/application identity, window size, and capture backend.
- Produce a correct game image with verified coordinate dimensions.
- Connect the local stdio server to Antigravity CLI.
- Have the agent interpret the returned image and identify a visible control.
- Verify one harmless click, one key action, and one camera drag in the actual
  game; prove the expected UI/camera response using before/after observations.
- Verify scrolling/zoom and whether construction is possible while paused.

Do this before developing the complete tool suite. If Antigravity CLI cannot
consume MCP images in the installed version, investigate configuration first.
If that remains blocked, report the evidence and propose the smallest fallback
(such as image-file reading or Antigravity desktop). Do not silently change the
primary host or implement multiple transports speculatively.

### Gate 2: reliable tool contract

- Implement the tool surface, metadata, validation, and useful errors.
- Verify coordinate alignment on several separated points in game content.
- Move the window and confirm inputs still land correctly. Resize it and confirm
  a new observation is required before further input.
- Verify invalid/out-of-bounds actions inject no input.
- Verify human stop during drag, key hold, and wait; held input is released and
  later actions remain blocked until reset.
- Verify handled errors/cancellation release input and ordinary operations
  execute serially.
- Verify focus loss and missing permissions produce actionable failures.

### Gate 3: end-to-end construction

The owner provides a suitable loaded test park with available flat rides, shops,
paths, scenery, adequate space, and funds or sandbox conditions. Establish this
precondition without changing saves automatically.

Using Antigravity CLI and only the exposed controls for game interaction, have
the agent:

1. Place a flat ride in a suitable location.
2. Place its entrance and exit and connect them to the park path network,
   including an appropriate queue connection.
3. Open the ride and inspect its visible status for missing connections or other
   immediate setup problems.
4. Place a shop accessible from a path and open it.
5. Add several scenery items near the constructed area.
6. Show final screenshots and describe the result and any remaining issues.

The owner may prepare the starting park and grant permissions. During the
demonstration, construction must be performed by the agent without the owner
clicking through placement steps. An interruption test is separate from this
demonstration. No fixed action-count or performance target is required.

## 12. Tests, documentation, and completion

Automate meaningful tests for coordinate transforms and resize detection,
argument/bounds validation, execution serialization, stop/cancellation behavior,
and release of held input on error. Use fake input/capture boundaries so these
tests run without the game. A small MCP integration test should verify tool
discovery and that observation returns image content plus matching metadata.

Use live tests for actual capture, event acceptance, focus, human interruption,
and construction. Do not substitute mocked tests for these claims or build a
large GUI regression harness. Run formatting/linting and the relevant automated
tests before handoff.

Deliver:

- Working source, dependency lockfile, and focused tests.
- `README.md` with setup, exact launch command, Antigravity CLI configuration,
  macOS permission steps for the actual launcher, window setup, stop/reset
  behavior, and recovery from stuck input or capture problems.
- `GAMEPLAY.md` as described above.
- Development `AGENTS.md` identifying this spec as authoritative and describing
  how to run checks; do not confuse it with gameplay guidance.
- A brief validation record with commands/checks run, the observed outcomes for
  each gate, evidence locations, and remaining limitations.

The owner may need to grant Screen Recording/Accessibility permissions, restart
the host, prepare the park, or perform the human stop gesture. Request that help
when actually needed, with concrete instructions. Never claim those steps were
performed if they were not.

V1 is complete when all three gates pass on the owner's Mac and the documented
setup can reproduce the workflow. If human setup or host limitations prevent a
live gate, clearly mark it pending and identify the exact remaining action;
working source plus passing unit tests alone is not full acceptance.
