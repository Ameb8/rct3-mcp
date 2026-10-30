# Controlling RollerCoaster Tycoon 3 from a CLI Agent on an Intel Mac

A setup guide and implementation spec for letting a command-line coding agent play the original RCT3 by looking at screenshots and sending synthetic mouse and keyboard input.

**Status:** background design reference. [SPEC.md](SPEC.md) is the authoritative v1 implementation specification and takes precedence over this walkthrough. Requirements and optional extensions below are not part of v1 unless included in SPEC.md. Items marked **VERIFY** depend on your exact game build or macOS version and must be confirmed on your machine, not assumed.

---

## Table of contents

1. [Goals and non-goals](#1-goals-and-non-goals)
2. [Architecture](#2-architecture)
3. [Step 0: identify your build and runtime](#3-step-0-identify-your-build-and-runtime)
4. [Host setup (macOS)](#4-host-setup-macos)
5. [Game setup](#5-game-setup)
6. [Project scaffold](#6-project-scaffold)
7. [Module specs](#7-module-specs)
   - SPEC-CFG, SPEC-ERR, SPEC-WIN, SPEC-CAP, SPEC-INP, SPEC-VIS, SPEC-OCR, SPEC-STATE, SPEC-MACRO, SPEC-SAFE, SPEC-CLI
8. [Building the template library](#8-building-the-template-library)
9. [Agent operating procedure](#9-agent-operating-procedure-agentsmd-spec)
10. [Phased build plan and acceptance gates](#10-phased-build-plan-and-acceptance-gates)
11. [Troubleshooting](#11-troubleshooting)
12. [Appendices](#12-appendices)

---

## 1. Goals and non-goals

### Goals

- A CLI tool, `rct3ctl`, that any shell-capable agent can call. It exposes **observe** (screenshot plus parsed state) and **act** (click, drag, key, scroll, named macros) commands.
- Every command prints machine-readable JSON, so the agent never has to parse prose.
- Deterministic code handles *where* to click (template matching, OCR, fixed coordinates). The model decides *what* to do.
- Safe by default: bounded actions, a kill switch, a human abort gesture, and save backups.
- Runs on an Intel Mac.

### Non-goals

- No OpenRCT2 integration. RCT3 has no scripting API, so everything goes through the GUI.
- No attempt at fully autonomous coaster *track design* in v1. See [Appendix C](#appendix-c-strategy-for-coasters).
- No game-memory modification. Read-only memory inspection is an optional appendix.

### Realistic expectations

| Task | Feasibility |
|---|---|
| Pause, resume, change game speed | Easy |
| Read cash, guest count, park rating | Easy to moderate (OCR) |
| Set prices, hire and place staff, research | Moderate (menu navigation via templates) |
| Place flat rides, shops, scenery on a grid | Moderate |
| Place prebuilt coasters | Moderate |
| Freehand coaster track building | Hard, slow, brittle |

---

## 2. Architecture

```
┌────────────────────┐   shell    ┌──────────────────────────────┐
│  CLI agent         │ ─────────► │  rct3ctl (Python CLI)        │
│  (Claude Code etc) │ ◄───────── │  JSON on stdout              │
└────────────────────┘   JSON     │                              │
        │ reads PNG paths         │  config  window  capture     │
        ▼                         │  inputs  vision  ocr  state  │
┌────────────────────┐            │  macros  safety              │
│  runs/<id>/frames  │ ◄───────── └──────────────┬───────────────┘
│  runs/<id>/actions │                           │ Quartz / AppKit / Vision
└────────────────────┘                           ▼
                                      ┌──────────────────────┐
                                      │ RCT3 window          │
                                      │ (native or Wine)     │
                                      └──────────────────────┘
```

### Key design decisions

1. **Frame space equals window points.** Captures are normalized so that 1 image pixel equals 1 screen point, regardless of Retina scaling. Click coordinates are then `window_origin + frame_xy` with no scale math anywhere except in `capture.py`.
2. **Everything is named.** Buttons are templates (`btn_pause`), numbers are OCR fields (`cash`), and multi-step routines are macros (`set_ticket_price`). The agent asks for names, not pixels, wherever possible.
3. **The game is paused by default.** The agent acts, then calls `tick N` to let N seconds of game time pass. This removes timing races between observation and action.
4. **Same-session execution.** `rct3ctl` must run inside the logged-in GUI session, because synthetic input and window capture do not work from a pure SSH session. See [Appendix A](#appendix-a-driving-it-over-ssh-launchagent-daemon) for the remote option.
5. **Declarative extension.** New behaviors are added as YAML macros and template images, not code changes.

---

## 3. Step 0: identify your build and runtime

Do this before anything else. The result decides which of three runtimes you use.

### 3.1 Gather facts

```bash
sw_vers                          # macOS version
uname -m                         # expect x86_64
system_profiler SPDisplaysDataType | grep -E "Resolution|Retina"
```

If you have a native Mac build installed, find its binary and check its architecture:

```bash
# adjust the path to wherever the .app lives
APP="/Applications/RollerCoaster Tycoon 3.app"
file "$APP/Contents/MacOS/"*
lipo -archs "$APP/Contents/MacOS/"* 2>/dev/null
```

### 3.2 Decision table

| Situation | Runtime | Notes |
|---|---|---|
| Native Mac build, binary includes `x86_64`, and it launches | **A. Native** | Best case. |
| Native Mac build is 32-bit only (`i386`) and macOS is 10.15 or newer | Native will not launch | 32-bit apps stopped running in macOS 10.15. Use B or C. **VERIFY** your build's architectures. |
| You own the Windows version (Steam or disc) | **B. CrossOver** (paid, easiest) or **C. Wine** | Both render into a normal macOS window, so everything in this guide still applies. |

For Wine on Intel, a maintained community build with 32-bit support is needed because RCT3 is a 32-bit Windows program. Check that whatever you pick lists 32-bit support before investing time. **VERIFY**

### 3.3 Record your decision

Write the result at the top of `config/rct3.yaml` (see SPEC-CFG): runtime, window owner name, and window title. The rest of the document is runtime-agnostic.

### 3.4 Runtime-specific notes

- **Native:** window owner name is the app name. Fullscreen is not needed. Use windowed mode.
- **CrossOver/Wine:** the window owner may be `wine`, `wine64-preloader`, `CrossOver`, or the game's exe name. Run `rct3ctl windows` (SPEC-CLI) to see what macOS reports. Turn **off** any "high resolution mode" or retina option for the bottle so the game renders at 1x. That makes templates simpler. **VERIFY** the option name in your version.

---

## 4. Host setup (macOS)

### 4.1 Dedicated environment (recommended)

If the agent will run unattended, create a separate standard user account, for example `rct3agent`, that owns the game, the repo, and the Python environment. A runaway agent can then only damage that account's files.

### 4.2 Python toolchain

```bash
brew install uv                     # or follow uv's installer
uv python install 3.12
```

### 4.3 Permissions (TCC)

macOS grants these **per executable**. Grant them to the exact binary that runs `rct3ctl`.

| Permission | Needed for | Where |
|---|---|---|
| Screen Recording | Capturing the game window's contents | System Settings > Privacy & Security > Screen & System Audio Recording (older macOS: Screen Recording) |
| Accessibility | Posting synthetic mouse and keyboard events | Privacy & Security > Accessibility |
| Input Monitoring | Usually not needed. Add only if events are silently dropped. | Privacy & Security > Input Monitoring |

Which executable? It depends on how you launch:

- Running from **Terminal.app** or **iTerm**: grant the terminal app.
- Running from an agent that spawns subprocesses (Claude Code and similar): the permission usually attaches to the terminal or host app that launched it. If prompts do not appear or capture comes back blank, grant the *resolved Python interpreter* too:

```bash
uv run python -c "import os,sys; print(os.path.realpath(sys.executable))"
```

Add that path through the `+` button in each pane (Cmd-Shift-G in the file picker to type a path). After granting, **fully restart** the process that needs it.

### 4.4 Stop the machine from interfering

```bash
sudo pmset -a displaysleep 0 sleep 0        # while a session runs; revert afterwards
caffeinate -dimsu &                          # alternative, scoped to this shell
```

Also:

- Disable the screensaver and screen lock for the session.
- Turn on Do Not Disturb or a Focus mode so notifications cannot steal focus or cover the game.
- Disable auto-correct and text-replacement popups if you plan to use `type`.
- Keep the display awake and the user session unlocked. A locked screen blocks capture and input.

### 4.5 Display

- Use a single display if you can. Multi-display setups work (coordinates can be negative) but add failure modes.
- Note whether the display is Retina. It does not change usage, but `doctor` reports the scale factor.

---

## 5. Game setup

1. Launch the game and set **windowed mode** at a fixed resolution that fits on screen with margin. 1280x720 is a good default. Larger means slower captures and bigger templates.
2. Turn off effects that make screenshots unstable: motion blur and shaky camera if present, and anything that animates the HUD. Keep **anti-aliasing and gamma constant** between template capture and agent runs. **VERIFY** which options your build has.
3. Keep the UI scale constant. Templates are pixel-matched, so changing the resolution later invalidates the library.
4. Record the keybindings in the Controls options screen and copy them into `config/rct3.yaml` under `bindings`. **Do not trust defaults from memory.** Camera rotate, zoom, pan, and pause bindings vary by build.
5. Create a **baseline save** of a fresh park. You will want to restart from it often during development.
6. Find where saves live, empirically:

```bash
# save a park in-game, then immediately:
find ~ -type f -mmin -2 2>/dev/null | grep -v -E "Caches|\.git/"
```

   Under Wine, expect the path to be inside the bottle or prefix. Put the directory in `config/rct3.yaml` as `saves.dir`.

---

## 6. Project scaffold

### 6.1 Layout

```
rct3-agent/
├── AGENTS.md                  # agent operating procedure (section 9)
├── pyproject.toml
├── Taskfile.yml
├── config/
│   ├── rct3.yaml              # runtime, window, input, safety, bindings, OCR regions
│   ├── templates.yaml         # template registry
│   └── macros.yaml            # named multi-step actions
├── assets/templates/          # PNG crops, captured with rct3ctl capture-template
├── runs/                      # created at runtime
│   └── <run-id>/{frames/, actions.jsonl}
├── src/rct3ctl/
│   ├── __init__.py
│   ├── errors.py
│   ├── config.py
│   ├── window.py
│   ├── capture.py
│   ├── inputs.py
│   ├── vision.py
│   ├── ocr.py
│   ├── state.py
│   ├── macros.py
│   ├── safety.py
│   └── cli.py
└── tests/
    ├── fixtures/              # recorded frames for offline tests
    ├── test_vision.py
    ├── test_ocr.py
    ├── test_macros.py
    └── gui/                   # needs a live game, marked macos_gui
```

### 6.2 `pyproject.toml`

```toml
[project]
name = "rct3ctl"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "numpy",
  "opencv-python-headless",
  "pillow",
  "pydantic>=2",
  "pyyaml",
  "typer",
  "pyobjc-framework-Quartz",
  "pyobjc-framework-Cocoa",
  "pyobjc-framework-ApplicationServices",
  "pyobjc-framework-Vision",
]

[project.optional-dependencies]
tesseract = ["pytesseract"]

[project.scripts]
rct3ctl = "rct3ctl.cli:app"

[dependency-groups]
dev = ["pytest", "ruff", "mypy", "types-PyYAML"]

[tool.pytest.ini_options]
markers = ["macos_gui: requires a live game window and TCC permissions"]
addopts = "-m 'not macos_gui'"

[tool.ruff]
line-length = 100

[tool.mypy]
strict = true
ignore_missing_imports = true   # pyobjc stubs are partial
```

If you are on an older macOS where the Vision framework is unavailable, drop `pyobjc-framework-Vision` and install the `tesseract` extra plus `brew install tesseract`. **VERIFY** Vision's minimum macOS version against Apple's docs.

### 6.3 `Taskfile.yml`

```yaml
version: "3"
tasks:
  setup:   { cmds: ["uv sync --all-groups"] }
  lint:    { cmds: ["uv run ruff check .", "uv run ruff format --check ."] }
  types:   { cmds: ["uv run mypy src"] }
  test:    { cmds: ["uv run pytest"] }
  gui:     { cmds: ["uv run pytest -m macos_gui tests/gui"] }
  doctor:  { cmds: ["uv run rct3ctl doctor"] }
```

---

## 7. Module specs

Conventions used below: **MUST**, **SHOULD**, and **MAY** carry their RFC 2119 meanings. Coordinates are `(x, y)` in **frame space** unless stated. Origin is top-left, y grows downward. Quartz global coordinates use the same orientation, with the origin at the top-left of the primary display.

---

### SPEC-CFG: `config.py` and `config/*.yaml`

**Purpose.** Load and validate all configuration once, and expose it as typed objects.

**Public interface**

```python
class AppCfg(BaseModel):
    runtime: Literal["native", "crossover", "wine"]
    owner_regex: str                 # matched against kCGWindowOwnerName
    title_regex: str | None          # matched against kCGWindowName, optional
    expected_size: tuple[int, int]   # expected frame size in points, e.g. (1280, 720)

class InputCfg(BaseModel):
    post_action_delay_ms: int = 80
    move_settle_ms: int = 40
    drag_step_px: int = 6
    drag_step_delay_ms: int = 8
    key_hold_ms: int = 45
    tap: Literal["hid", "session"] = "hid"

class SafetyCfg(BaseModel):
    failsafe_corner: Literal["top_left", "top_right", "bottom_left", "bottom_right", "off"] = "top_left"
    failsafe_margin_px: int = 3
    max_actions_per_minute: int = 120
    stop_file: Path = Path("runs/STOP")
    require_frontmost: bool = True
    act_while_paused: bool = True    # VERIFY: can you build while paused in your build?

class OcrField(BaseModel):
    rect: tuple[int, int, int, int]  # x0, y0, x1, y1 in frame space
    kind: Literal["money", "int", "text"]
    upscale: int = 3
    invert: bool = False
    threshold: int | None = None     # None = no binarization

class Config(BaseModel):
    app: AppCfg
    input: InputCfg
    safety: SafetyCfg
    bindings: dict[str, KeySpec]     # name -> key + modifiers
    ocr_fields: dict[str, OcrField]
    saves_dir: Path | None
    runs_dir: Path = Path("runs")

def load_config(path: Path = Path("config/rct3.yaml")) -> Config: ...
```

**Requirements**

- R1. Validation errors MUST name the YAML path of the bad key.
- R2. Unknown keys MUST be rejected (`extra="forbid"`). Typos should fail loudly.
- R3. `bindings` values MUST be validated against the keycode table in SPEC-INP.
- R4. Loading MUST NOT touch the GUI or require TCC permissions, so tests can run anywhere.

**Example `config/rct3.yaml`**

```yaml
app:
  runtime: crossover                 # native | crossover | wine
  owner_regex: "(?i)rct3|rollercoaster|wine|crossover"   # tighten after `rct3ctl windows`
  title_regex: "(?i)rollercoaster"
  expected_size: [1280, 720]

input:
  post_action_delay_ms: 80
  tap: hid

safety:
  failsafe_corner: top_left
  max_actions_per_minute: 120
  act_while_paused: true

bindings:            # VERIFY every entry against the in-game Controls screen
  pause:        { key: space }
  camera_left:  { key: left }
  camera_right: { key: right }
  camera_up:    { key: up }
  camera_down:  { key: down }

ocr_fields:
  cash:   { rect: [1040, 10, 1270, 34], kind: money }
  guests: { rect: [20, 686, 140, 712],  kind: int }

saves_dir: "~/Documents/RollerCoaster Tycoon 3"   # VERIFY with the find command in section 5
```

**Acceptance**

- `load_config()` round-trips the sample file.
- A config with a misspelled key raises an error naming that key.
- A binding with an unknown key name is rejected.

---

### SPEC-ERR: `errors.py`

**Purpose.** One exception hierarchy mapped to stable exit codes, so agents can branch on failures.

| Exception | Exit code | Meaning |
|---|---|---|
| `UsageError` | 2 | Bad arguments |
| `WindowNotFound` | 10 | No window matched the config |
| `NotFrontmost` | 11 | Game is not the frontmost app and focus failed |
| `PermissionMissing` | 12 | Screen Recording or Accessibility not granted |
| `TemplateNotFound` | 13 | Named template matched below threshold |
| `SafetyAbort` | 14 | STOP file, failsafe corner, rate limit, or out-of-bounds |
| `OcrLowConfidence` | 15 | Could not read a field reliably |
| `MacroFailed` | 16 | A macro step or assertion failed |

**Requirements**

- R1. Every exception MUST carry a `code` (string slug), a human `message`, and an optional `hint` (what to try next).
- R2. `cli.py` MUST convert any exception into the JSON error envelope in SPEC-CLI and exit with the mapped code. Unexpected exceptions exit 1 with `code: "internal"`.

---

### SPEC-WIN: `window.py`

**Purpose.** Locate the game window, report its geometry, and manage focus.

**Public interface**

```python
@dataclass(frozen=True)
class WindowInfo:
    window_id: int          # CGWindowID
    pid: int
    owner: str
    title: str
    x: float; y: float      # global points, top-left origin
    w: float; h: float      # points, includes title bar if present

def list_windows() -> list[WindowInfo]: ...
def find_game_window(cfg: AppCfg) -> WindowInfo: ...      # raises WindowNotFound
def is_frontmost(win: WindowInfo) -> bool: ...
def focus(win: WindowInfo, timeout_s: float = 2.0) -> None: ...   # raises NotFrontmost
def cursor_position() -> tuple[float, float]: ...          # global points
```

**Requirements**

- R1. `list_windows` MUST use `CGWindowListCopyWindowInfo` with `kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements`, and keep only entries with `kCGWindowLayer == 0` and a non-trivial size.
- R2. `find_game_window` MUST match `owner_regex` against the owner name, and `title_regex` against the title when configured. If several windows match, pick the largest and include the ambiguity in the result metadata.
- R3. Under Wine, window titles may be empty without Screen Recording permission. If titles are all empty and Screen Recording is not granted, raise `PermissionMissing`, not `WindowNotFound`.
- R4. `is_frontmost` MUST compare the pid of `NSWorkspace.sharedWorkspace().frontmostApplication()` to `win.pid`.
- R5. `focus` MUST activate the owning application via `NSRunningApplication`, with an `osascript` fallback, then poll `is_frontmost` until it succeeds or the timeout elapses.
- R6. `cursor_position` MUST be read from a fresh `CGEventCreate(None)` location, so it reflects the real pointer.
- R7. Geometry MUST be re-queried on every action. Never cache it across commands, since the user can move the window.

**Acceptance**

- With the game open, `find_game_window` returns a window whose size is within a few points of `expected_size` plus any title bar.
- With the game closed, it raises `WindowNotFound` with a hint to run `rct3ctl windows`.

---

### SPEC-CAP: `capture.py`

**Purpose.** Produce a normalized, loggable screenshot of the game window.

**Public interface**

```python
@dataclass
class Frame:
    image: np.ndarray        # BGR uint8, shape (h, w, 3), 1 px == 1 point
    window: WindowInfo
    native_scale: float      # captured_px / points (1.0 or 2.0 typically)
    taken_at: float          # time.monotonic()
    index: int               # per-run counter
    path: Path | None        # where it was saved, if logged

def capture(win: WindowInfo, *, save_dir: Path | None = None, index: int = 0) -> Frame: ...
```

**Requirements**

- R1. Capture MUST shell out to `screencapture -x -o -l <window_id> <tmpfile.png>`. `-x` silences the sound, `-o` excludes the window shadow, `-l` targets the window by ID. Use a tmp path on a RAM-backed or local volume.
- R2. After loading, compute `native_scale = image_width_px / win.w`. If it is not about 1.0, resize with `cv2.INTER_AREA` to `(round(win.w), round(win.h))`.
- R3. The resulting frame size SHOULD be within 2 px of `cfg.app.expected_size`. If not, still return the frame and attach a warning to the result metadata. Do not fail hard.
- R4. If the image is blank, or contains only the window chrome with no content, assume Screen Recording is missing and raise `PermissionMissing`. A cheap check: the image's standard deviation is near zero, or its pixel content matches the desktop.
- R5. When `save_dir` is given, write `frames/{index:04d}.png` and set `Frame.path`.
- R6. Capture latency SHOULD be under 400 ms. Report `capture_ms` in the result. If it is consistently slow, see the optional Quartz fast path in [Appendix D](#appendix-d-optional-optimizations).
- R7. Capture MUST work while the game is not frontmost. It must still fail clearly if the window is minimized.

**Acceptance**

- `rct3ctl shot` writes a PNG whose pixel size equals the game's point size on both Retina and non-Retina displays.
- Revoking Screen Recording makes `shot` exit 12, not return a blank image.

---

### SPEC-INP: `inputs.py`

**Purpose.** Post synthetic mouse and keyboard events with human-like pacing, in frame-space coordinates.

**Public interface**

```python
Button = Literal["left", "right", "middle"]

class Input:
    def __init__(self, cfg: Config, guard: Guard) -> None: ...

    def move(self, p: Pt) -> None: ...
    def click(self, p: Pt, button: Button = "left", count: int = 1, hold_ms: int | None = None) -> None: ...
    def drag(self, a: Pt, b: Pt, button: Button = "left", duration_ms: int = 400,
             hold_mods: tuple[str, ...] = ()) -> None: ...
    def scroll(self, dy: int, at: Pt | None = None) -> None: ...
    def key(self, name: str, mods: tuple[str, ...] = (), hold_ms: int | None = None) -> None: ...
    def key_down(self, name: str, mods: tuple[str, ...] = ()) -> None: ...
    def key_up(self, name: str, mods: tuple[str, ...] = ()) -> None: ...
    def type_text(self, text: str, per_key_ms: int = 25) -> None: ...
```

**Event mechanics (the part that usually goes wrong)**

- Build events with `Quartz.CGEventCreateMouseEvent`, `CGEventCreateKeyboardEvent`, and `CGEventCreateScrollWheelEvent`. Post with `CGEventPost(kCGHIDEventTap, ev)` by default. Fall back to `kCGSessionEventTap` only if `input.tap: session` is configured.
- Frame to global conversion: `gx = win.x + px`, `gy = win.y + py`, using a fresh `WindowInfo`.
- Mouse events by button:

| Action | Event types |
|---|---|
| Left | `LeftMouseDown`, `LeftMouseDragged`, `LeftMouseUp` |
| Right | `RightMouseDown`, `RightMouseDragged`, `RightMouseUp` |
| Middle | `OtherMouseDown`, `OtherMouseDragged`, `OtherMouseUp`, with the button number field set to 2 |

- **Always move first.** Post a `MouseMoved` to the target, sleep `move_settle_ms`, then press. Games that poll cursor position ignore a click that arrives before the pointer does.
- **Drags need intermediate events.** Interpolate between start and end at about `drag_step_px` per step, posting a dragged event each time. For each, set `kCGMouseEventDeltaX` and `kCGMouseEventDeltaY` via `CGEventSetIntegerValueField`. Camera rotation in many games is driven by relative deltas, not absolute positions.
- Double clicks: set `kCGMouseEventClickState` to the click number on each down and up pair.
- Modifier keys: set flags on the event with `CGEventSetFlags` (Shift, Control, Option, Command masks), and also send real modifier key down and up events if the game reads key state directly. Make that behavior configurable.
- Scroll: `CGEventCreateScrollWheelEvent` with line units. If the game ignores line units, retry with pixel units. Place the pointer over the target first.

**Keycode table (ANSI US layout, virtual key codes)**

| Key | Code | Key | Code | Key | Code |
|---|---|---|---|---|---|
| a | 0 | s | 1 | d | 2 |
| w | 13 | q | 12 | e | 14 |
| p | 35 | space | 49 | return | 36 |
| tab | 48 | escape | 53 | delete | 51 |
| left | 123 | right | 124 | down | 125 |
| up | 126 | shift | 56 | control | 59 |
| option | 58 | command | 55 | | |

Extend the table to cover everything in `bindings`. Layout-dependent keys are a known hazard for non-US layouts. Document the assumption.

**Requirements**

- R1. Every public method MUST call `guard.before_action(point_or_none)` first. See SPEC-SAFE.
- R2. Every method MUST sleep `post_action_delay_ms` after completing.
- R3. A drag MUST release the button in a `finally` block, even if aborted midway, so the game never gets a stuck button. Same for `key_down` without a matching `key_up`: track held keys and release them all on exit.
- R4. `type_text` MUST refuse characters not in the keycode table rather than silently dropping them.
- R5. All points MUST be bounds-checked against the current window rectangle. Out-of-bounds raises `SafetyAbort`.

**Acceptance (GUI tests)**

- After `move((100, 100))`, `cursor_position()` equals `(win.x + 100, win.y + 100)` within 1 point.
- A left click on a known harmless button (for example the options button) opens its dialog.
- A right-drag across the park view rotates the camera. A frame diff before and after is non-trivial.
- Killing the process mid-drag leaves no stuck mouse button.

---

### SPEC-VIS: `vision.py`

**Purpose.** Find named UI elements in a frame.

**Public interface**

```python
@dataclass(frozen=True)
class Match:
    name: str
    center: Pt
    bbox: tuple[int, int, int, int]
    score: float

class TemplateLibrary:
    def __init__(self, registry: Path, assets: Path) -> None: ...
    def names(self) -> list[str]: ...

def find(frame: Frame, lib: TemplateLibrary, name: str,
         region: Rect | None = None) -> Match | None: ...
def find_all(frame: Frame, lib: TemplateLibrary, name: str,
             region: Rect | None = None, max_results: int = 50) -> list[Match]: ...
def wait_for(grab: Callable[[], Frame], lib: TemplateLibrary, name: str,
             timeout_ms: int = 3000, poll_ms: int = 150) -> Match: ...
def annotate(frame: Frame, matches: list[Match], grid: int | None = None) -> np.ndarray: ...
```

**Template registry `config/templates.yaml`**

```yaml
templates:
  btn_pause:
    file: btn_pause.png
    threshold: 0.92
    region: [0.0, 0.88, 0.35, 1.0]     # optional search area, fractions of frame
  ind_paused:
    file: ind_paused.png
    threshold: 0.90
  tab_rides:
    file: tab_rides.png
    threshold: 0.93
    mask: tab_rides_mask.png           # optional: white = compare, black = ignore
```

**Requirements**

- R1. Use `cv2.matchTemplate` with `TM_CCOEFF_NORMED` on grayscale, or on color if a template is flagged `color: true`. When a mask is provided, use `TM_CCORR_NORMED` or `TM_SQDIFF` with the mask as OpenCV requires.
- R2. A match counts only if `score >= threshold` for that template. Per-template thresholds exist because icons with transparency or hover highlights score differently.
- R3. `region` is in fractions of the frame, converted to pixels and clipped. It both speeds up matching and prevents false positives elsewhere.
- R4. `find_all` MUST apply non-maximum suppression so one button does not yield a cluster of overlapping matches.
- R5. `wait_for` MUST poll by capturing fresh frames, and raise `TemplateNotFound` on timeout with the best score seen, so threshold tuning is data-driven.
- R6. Template matching is **not** scale invariant. Do not add multi-scale search by default. If the frame size differs from `expected_size`, `doctor` warns, because silently rescaling hides real configuration errors.
- R7. `annotate` MUST draw match boxes with labels. When `grid` is set, also draw labeled gridlines every `grid` pixels, which helps a vision model estimate coordinates when no template exists.
- R8. Hover states: buttons often look different under the cursor. Either store both variants as separate templates, or move the cursor to a neutral spot before capture. Config flag `park_cursor_before_capture: true` with a configurable parking position.

**Acceptance**

- Offline test: given recorded fixture frames, every registered template is found at the expected location in at least one fixture, and none is found in a fixture where it should be absent.
- `find` returns in under 50 ms on a 1280x720 frame with a region set.

---

### SPEC-OCR: `ocr.py`

**Purpose.** Read numeric and short text fields from fixed rectangles.

**Public interface**

```python
@dataclass(frozen=True)
class OcrResult:
    field: str
    raw: str
    value: int | str | None
    confidence: float          # 0..1; engine-reported where available
    engine: str

def read_field(frame: Frame, name: str, cfg: Config) -> OcrResult: ...
def parse_money(raw: str) -> int | None: ...
def parse_int(raw: str) -> int | None: ...
```

**Requirements**

- R1. Preprocess: crop `rect`, upscale by `upscale` with `INTER_CUBIC`, convert to grayscale, optionally invert and threshold.
- R2. Engine selection (`ocr.engine: auto`): prefer Apple Vision via `VNRecognizeTextRequest` with `recognitionLevel = accurate` and `usesLanguageCorrection = False` (language correction mangles numbers). Fall back to `pytesseract` with `--psm 7` and a character whitelist such as `0123456789$,.-` for numeric fields.
- R3. `parse_money` MUST handle `$1,234`, `-$1,234`, `1.234` (thousands dot in some locales), and OCR confusions (`O` to `0`, `l`/`I` to `1`, `S` to `5`) only inside numeric fields.
- R4. If parsing fails or confidence is below `min_confidence` (default 0.5), return `value=None`, never a guess.
- R5. `read_field` MUST NOT raise on low confidence. Callers decide. The CLI turns `None` into a field-level warning, not a global failure.
- R6. Provide `rct3ctl ocr --debug FIELD` that writes the preprocessed crop to the run directory. OCR tuning is mostly looking at crops.

**Acceptance**

- Offline test: fixture frames with known cash and guest values parse correctly.
- `parse_money` unit tests cover negatives, separators, and garbage input returning `None`.

---

### SPEC-STATE: `state.py`

**Purpose.** Combine OCR fields and template checks into one structured snapshot.

**Public interface**

```python
@dataclass
class ParkState:
    cash: int | None
    guests: int | None
    rating: int | None
    paused: bool | None
    extra: dict[str, Any]
    fields: dict[str, OcrResult]       # raw evidence, including confidences
    warnings: list[str]

def read_state(frame: Frame, lib: TemplateLibrary, cfg: Config) -> ParkState: ...
```

**Requirements**

- R1. `paused` MUST come from a template check on a pause indicator (`ind_paused`), not from keypress bookkeeping. Pressing the pause key twice must not desync the harness.
- R2. Every field is independently optional. One unreadable field MUST NOT hide the others.
- R3. Sanity checks: reject guest counts that are negative or implausibly large, and flag a cash value that changed by more than a configurable factor in one observation without an action explaining it. Emit a warning, not a fix.
- R4. `ParkState` MUST serialize to JSON with confidences included.

**Acceptance**

- On fixture frames, `paused` is correct in both states.
- A frame with an obscured cash field yields `cash: null` plus a warning.

---

### SPEC-MACRO: `macros.py` and `config/macros.yaml`

**Purpose.** Declarative multi-step routines, so adding a behavior does not require code.

**Step vocabulary**

| Step | Arguments | Behavior |
|---|---|---|
| `click_template` | `name`, `offset: [dx, dy]`, `button`, `count`, `region` | Find, then click the center plus offset |
| `click` | `at: [x, y]`, `button`, `count` | Fixed frame-space coordinate |
| `drag` | `from`, `to`, `button`, `duration_ms` | Drag |
| `key` | `name`, `mods`, `hold_ms` | Key tap |
| `scroll` | `dy`, `at` | Wheel |
| `type` | `text` | Type text |
| `wait_ms` | `ms` | Sleep |
| `wait_template` | `name`, `timeout_ms` | Wait until present |
| `assert_template` | `name` | Fail the macro if absent |
| `assert_absent` | `name` | Fail the macro if present |
| `ocr_expect` | `field`, `min`, `max` | Fail unless the field parses within the range |
| `if_template` | `name`, `then: [...]`, `else: [...]` | Branch |

String values MAY contain `{{param}}` placeholders, filled from `--arg key=value`.

**Example**

```yaml
macros:
  pause:
    description: Pause the game if it is running.
    steps:
      - if_template:
          name: ind_paused
          else:
            - click_template: { name: btn_pause }
            - wait_template: { name: ind_paused, timeout_ms: 1500 }

  open_rides_tab:
    steps:
      - click_template: { name: tab_rides }
      - wait_template: { name: hdr_rides, timeout_ms: 2000 }

  click_grid_cell:
    description: Click a position in the park view (used after selecting a placeable item).
    params: [x, y]
    steps:
      - click: { at: ["{{x}}", "{{y}}"] }
```

**Requirements**

- R1. Macros MUST be validated at load: unknown step types, missing params, and references to templates not in the registry fail `rct3ctl macros --check`.
- R2. Each step logs to `actions.jsonl` with its result, so a failed macro can be diagnosed without rerunning it.
- R3. On failure, the macro stops, saves a frame as `failure_<macro>_<step>.png`, and raises `MacroFailed` with the step index and reason. It MUST NOT continue past a failed assertion.
- R4. Macros MAY NOT call other macros in v1 (prevents cycles). Revisit if reuse becomes painful.
- R5. After the final step, if the macro declares `postcondition`, evaluate it and fail if it is false.

**Acceptance**

- `macros --check` passes on the shipped file and fails on a file referencing a missing template.
- Running `pause` twice leaves the game paused both times (idempotent).

---

### SPEC-SAFE: `safety.py`

**Purpose.** One guard object that every input action passes through.

**Public interface**

```python
class Guard:
    def __init__(self, cfg: Config, win_provider: Callable[[], WindowInfo]) -> None: ...
    def before_action(self, point: Pt | None = None) -> None: ...   # raises SafetyAbort
```

**Checks, in order**

1. **STOP file.** If `safety.stop_file` exists, abort. `rct3ctl panic` creates it, and `rct3ctl panic --clear` removes it. This is the agent-level kill switch, usable from another terminal.
2. **Failsafe corner.** If the real cursor sits within `failsafe_margin_px` of the configured screen corner, abort. This is the human-level kill switch: slam the mouse into the corner.
3. **Frontmost.** If `require_frontmost` and the game is not frontmost, try `focus()` once. If that fails, abort with `NotFrontmost`.
4. **Bounds.** If a point is given, it MUST lie inside the window rectangle, inset by a small margin that excludes the title bar buttons. The close, minimize, and zoom controls MUST be unreachable.
5. **Rate limit.** Sliding one-minute window; exceed `max_actions_per_minute` and abort.
6. **Quit-key protection.** Refuse `command+q`, `command+w`, and `command+option+escape` regardless of source.

**Requirements**

- R1. The guard MUST be the only path to the input layer. No other module may import Quartz event-posting functions.
- R2. Safety aborts MUST be loud: non-zero exit, JSON error with the reason, and a note in `actions.jsonl`.
- R3. `backup-saves` (SPEC-CLI) MUST copy `saves.dir` to a timestamped directory under `runs/<id>/backups/` and report the file count. Run it at the start of each session and before any macro tagged `risky: true`.

---

### SPEC-CLI: `cli.py`

**Purpose.** The agent-facing surface. Thin: parse args, call modules, print JSON.

**Output envelope (always, on stdout)**

```json
{
  "ok": true,
  "command": "observe",
  "data": { },
  "warnings": [],
  "error": null,
  "elapsed_ms": 412
}
```

On failure:

```json
{
  "ok": false,
  "command": "click-template",
  "data": null,
  "warnings": [],
  "error": { "code": "template_not_found", "message": "btn_build scored 0.71 (threshold 0.92)", "hint": "Run: rct3ctl observe --annotate btn_build" },
  "elapsed_ms": 933
}
```

Exit code follows the table in SPEC-ERR. Logs and tracebacks go to stderr, never stdout.

**Commands**

| Command | Purpose | Key output fields |
|---|---|---|
| `doctor` | Environment self-check | per-check pass/fail and hint |
| `windows` | List candidate windows | id, pid, owner, title, bounds |
| `focus` | Bring the game to front | `frontmost: true` |
| `shot [--out PATH]` | Capture only | `path`, `size`, `native_scale`, `capture_ms` |
| `observe [--annotate NAME...] [--grid N] [--no-state]` | Capture, optional overlay, state | `frame_path`, `view_path`, `state`, `matches` |
| `find NAME [--all] [--region x0 y0 x1 y1]` | Template lookup | matches with center, bbox, score |
| `ocr FIELD [--debug]` | Read one field | `OcrResult` |
| `state` | Parsed park state only | `ParkState` |
| `click X Y [--button B] [--count N]` | Raw click | `at`, `global_at` |
| `click-template NAME [--offset DX DY]` | Click a named element | `match`, `at` |
| `drag X1 Y1 X2 Y2 [--button B] [--duration-ms N]` | Raw drag | |
| `scroll DY [--at X Y]` | Wheel | |
| `key NAME [--mod cmd,shift,...] [--hold-ms N]` | Key tap | |
| `type TEXT` | Typing | |
| `macro NAME [--arg k=v ...]` | Run a macro | per-step results |
| `macros [--check]` | List or validate macros | |
| `pause` / `resume` | Idempotent, verified via template | `paused` |
| `tick SECONDS` | Resume, wait, pause, verify | `elapsed_game_s`, `state` |
| `capture-template NAME X0 Y0 X1 Y1` | Crop the current frame into the library | file path, registry entry |
| `backup-saves` | Copy the saves directory | destination, file count |
| `panic [--clear]` | Create or remove the STOP file | |

**Requirements**

- R1. All commands MUST be non-interactive. No prompts, ever.
- R2. `observe` writes two images: `frame_path` (exact normalized capture, used for template work) and `view_path` (annotated, optionally gridded, downscaled so the long edge is at most 1568 px for model consumption). Coordinates on all other commands are in `frame_path` space.
- R3. `tick` MUST verify the paused state afterwards via template and report an error if the game did not re-pause. A game left running while the agent thinks is the most common failure.
- R4. `click-template` MUST re-capture a fresh frame immediately before matching. Never reuse a frame from an earlier command.
- R5. Every action command MUST append a line to `runs/<id>/actions.jsonl`: timestamp, command, args, result code, and the index of the last observed frame.
- R6. `RCT3CTL_RUN` environment variable pins the run ID so multiple commands from one agent session land in one run directory. If unset, `observe` creates a new run and prints its ID.
- R7. `doctor` MUST check: Python and macOS versions, architecture, Screen Recording (`CGPreflightScreenCaptureAccess`), Accessibility (`AXIsProcessTrusted`), window found and size versus `expected_size`, native scale, a real capture that is not blank, OCR engine availability, template files present for every registry entry, and macro validity.

**Acceptance**

- `doctor` on a correctly configured machine exits 0 with every check passing.
- Every command emits valid JSON on stdout in both success and failure, verified by a test that pipes output through `json.loads`.

---

## 8. Building the template library

Templates are the project's real asset. Spend time here.

### 8.1 Workflow

1. Put the game in a known screen (for example the main park view with the toolbar visible).
2. `rct3ctl observe` and open `frame_path` in an image viewer that shows pixel coordinates (Preview's inspector works, or any editor).
3. Note the rectangle around the element, tight but with a 1 to 2 px margin of its own background.
4. `rct3ctl capture-template btn_pause 12 680 52 712`
5. Run `rct3ctl find btn_pause` and confirm score and location.
6. Edit `config/templates.yaml` to set `threshold` and, if useful, `region`.
7. Verify it is **absent** where it should be: navigate away and confirm `find` returns no match.

### 8.2 Naming convention

| Prefix | Meaning |
|---|---|
| `btn_` | Clickable button |
| `tab_` | Tab or category selector |
| `hdr_` | Header proving a screen is open |
| `ind_` | State indicator (paused, selected, warning) |
| `dlg_` | Dialog or popup |
| `item_` | Item inside a list (a specific ride or scenery piece) |

### 8.3 Choosing what to capture

- Prefer elements that are **static**: icon art, not text that changes.
- For toggles, capture both states as separate templates (`btn_pause_up`, `ind_paused`).
- Capture selected and unselected variants of tabs.
- For items inside scrolling lists, use `find_all` plus a scroll-and-retry macro rather than assuming position.
- Avoid capturing parts that include the game world behind translucent panels. The background changes, so use a mask or crop to the opaque part.

### 8.4 Maintaining the library

- Store templates in git. A changed resolution or setting invalidates all of them, so keep a `assets/templates/MANIFEST.md` listing the capture resolution and game options used.
- Keep recorded fixture frames in `tests/fixtures/` and run the offline vision tests after any change. A failing fixture test means the library drifted.

---

## 9. Agent operating procedure (AGENTS.md spec)

Ship an `AGENTS.md` at the repo root. This is its required content, in spec form.

### 9.1 Required sections

**Purpose.** One paragraph: the agent plays RCT3 through `rct3ctl`; it must never invoke raw `osascript`, `cliclick`, or Python event code directly.

**Session start checklist**

1. `export RCT3CTL_RUN=$(date +%Y%m%d-%H%M%S)`
2. `rct3ctl doctor` must exit 0, otherwise stop and report.
3. `rct3ctl backup-saves`
4. `rct3ctl pause`
5. `rct3ctl observe` and view `view_path`.

**The loop**

```
observe → decide ONE small step → act → observe → verify → repeat
```

Rules:

- Never act without an observation from the **same step**. The screen changes.
- Prefer, in order: `macro`, `click-template`, raw `click`. Use raw coordinates only when no template exists, and then use `--grid` to ground them.
- After any action that should change the screen, verify via `find`, `state`, or a new `observe`. If the expected change did not happen, do **not** repeat the action more than once. Take an observation and reassess.
- Keep the game paused while reasoning. Use `tick N` to advance time deliberately. Default to short ticks (10 to 30 s of wall time) while learning a screen, longer when idle.
- Cap: at most 8 actions between observations, at most 200 actions per session, unless the task says otherwise.
- On any `safety_abort` error: **stop**. Do not retry. Report the reason to the human.
- If `ocr` returns `null` for a field, do not assume a value. Take a screenshot and read it visually, and say that you did.
- Never click outside the park window. Never attempt to quit the game.
- Save the game (via macro) after any significant milestone.

**Error handling table.** Reproduce the exit-code table from SPEC-ERR with the recommended response for each code.

**Reporting.** At session end, print: actions taken, final state, any warnings, and path to `runs/<id>`.

### 9.2 Tool contract for different agent hosts

- **Shell-capable agents** (Claude Code and similar): call `rct3ctl` directly. For images, reference the PNG path in a form the host can display. Many agents can read image files from disk. **VERIFY** your host supports vision on file paths.
- **MCP**: optionally wrap the CLI in a thin MCP server where each CLI command becomes a tool and `observe` returns the image inline. Keep the CLI as the source of truth, and treat the MCP layer as a transport only.

### 9.3 Game-time model

Because the agent is slow relative to the game, treat the game as turn-based:

- `act_while_paused: true` means actions happen while paused (preferred). **VERIFY** your build allows placing and building while paused.
- If your build blocks actions while paused, set `act_while_paused: false` and use the slowest available game speed with short action bursts, accepting some drift.

---

## 10. Phased build plan and acceptance gates

Do not proceed to the next phase until the gate passes.

| Phase | Deliverable | Gate |
|---|---|---|
| **M0** Environment | Section 3 to 5 complete; game runs windowed | You can play the game manually in the chosen runtime; baseline save exists |
| **M1** Window and capture | SPEC-CFG, ERR, WIN, CAP; `windows`, `shot`, `doctor` (partial) | `shot` produces a correct, non-blank PNG at the right size; permissions failure exits 12 |
| **M2** Input | SPEC-INP, SAFE; `click`, `drag`, `key`, `scroll`, `panic` | Cursor lands on target within 1 pt; right-drag rotates camera; failsafe corner and STOP file both abort; no stuck buttons after kill |
| **M3** Vision | SPEC-VIS; `find`, `capture-template`, `observe` | 10 core templates found with score above threshold; fixture tests pass; `observe` output looks right to a human |
| **M4** State | SPEC-OCR, STATE; `ocr`, `state`, `pause`, `resume`, `tick` | Cash and guests read correctly across 20 observations; `tick` re-pauses reliably over 50 runs |
| **M5** Macros | SPEC-MACRO; 10 macros covering menu navigation and a flat-ride placement | `macros --check` clean; each macro succeeds 9 out of 10 from a clean state |
| **M6** Agent loop | AGENTS.md; a scripted task, for example "build a shop near the entrance and set its price" | The agent completes it unattended in under 40 actions, with the run log showing no safety aborts |
| **M7** Hardening | Retry policies, drift detection, longer sessions | A 30-minute unattended session completes with no unrecovered errors |

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `shot` returns blank, wallpaper-only, or chrome-only image | Screen Recording not granted to the launching executable | Grant it, then fully restart the terminal or agent process. Also grant the resolved Python path. |
| `doctor` says Accessibility not trusted | Same, for Accessibility | Grant and restart |
| Clicks do nothing, no errors | Game not frontmost; wrong event tap; or game filters synthetic events | Check `is_frontmost`; try `input.tap: session`; ensure you move the cursor before clicking |
| Clicks land at half or double the intended place | Retina scale handled in two places | Confirm frame is normalized to points (SPEC-CAP R2) and no other module multiplies by scale |
| Camera does not rotate on drag | Missing relative delta fields, or wrong mouse button | Set `kCGMouseEventDeltaX/Y` on dragged events; verify the rotate binding in Controls; try middle button |
| Keys ignored | Layout mismatch, wrong binding, or modifier handling | Re-read bindings in-game; try sending explicit modifier key events |
| Template never matches | Resolution or UI scale changed; hover highlight; translucent background; gamma differences | Recapture at current settings; park cursor before capture; use a mask; lower the threshold only after inspecting the best score |
| Template matches in the wrong place | Threshold too low or no `region` | Raise threshold; add a `region` |
| OCR returns garbage | Wrong rect; font too small; engine language correction on | Use `ocr --debug`, raise `upscale`, enable inversion or thresholding, disable language correction |
| Game minimized or focus stolen mid-run | Notification, screensaver, or another app | Enable Focus mode, disable the screensaver; the guard's `focus()` retry handles one-offs |
| Window not found under Wine or CrossOver | Owner name differs from the config | Run `rct3ctl windows`, then tighten `owner_regex` |
| Everything works in Terminal but not over SSH | SSH processes are outside the GUI session | Run in a GUI-session terminal, or use [Appendix A](#appendix-a-driving-it-over-ssh-launchagent-daemon) |
| Game running while the agent thinks | `tick` did not re-pause | Check the `ind_paused` template; make `tick` fail loudly (SPEC-CLI R3) |

---

## 12. Appendices

### Appendix A: driving it over SSH (LaunchAgent daemon)

**Problem.** Processes started over SSH are not in the user's GUI session, so window capture and event posting generally fail.

**Solution.** Run a small daemon inside the GUI session and have `rct3ctl` talk to it over a local socket. The daemon holds the TCC permissions.

**Spec: `rct3d`**

- R1. A long-running process that imports the same modules and serves requests on a Unix domain socket at `~/Library/Application Support/rct3ctl/rct3d.sock`, permissions `0600`.
- R2. Protocol: one JSON request per line (`{"command": "...", "args": {...}}`), one JSON envelope reply per line (same envelope as SPEC-CLI).
- R3. `rct3ctl` gains `--remote` (or auto-detects the socket): when the socket exists and the process is not in the GUI session, forward the command instead of executing locally.
- R4. The daemon MUST serialize commands (one at a time) and enforce SPEC-SAFE itself, since it is the only process that can post events.
- R5. Image paths in replies refer to the daemon's filesystem. Since SSH and the daemon are the same user and same machine, this just works. Keep run directories under the user's home.

**LaunchAgent plist** (`~/Library/LaunchAgents/com.example.rct3d.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.example.rct3d</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/rct3agent/rct3-agent/.venv/bin/python</string>
    <string>-m</string><string>rct3ctl.daemon</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/rct3agent/rct3-agent</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
  <key>StandardErrorPath</key><string>/tmp/rct3d.err</string>
</dict>
</plist>
```

Load it with `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.rct3d.plist`. Grant Screen Recording and Accessibility to the interpreter at the `ProgramArguments` path (resolve symlinks, see section 4.3). The user must be logged in with an unlocked session. Use Screen Sharing from another machine to watch and to recover from prompts.

### Appendix B: reading game state from memory (optional, read-only)

This is a research direction, not part of the core build.

- Needs `task_for_pid`, which requires root or a debugging entitlement, and is restricted by System Integrity Protection for protected processes. The game is a normal user process, so debugger access via `lldb` is the practical route. **VERIFY** on your macOS version.
- Addresses change between builds and between runs if ASLR applies. A workable method: find a value (cash) by searching for the known number, change it in-game, re-scan, and narrow down. Then locate stable pointer chains.
- Under Wine, the process is a Wine host process; Windows memory layouts apply inside it.
- Value: more reliable cash and guest counts than OCR. Cost: fragile per-build setup, and it can only observe.
- If pursued, keep it behind a `state.source: memory | ocr` setting, and fall back to OCR on any read failure.

### Appendix C: strategy for coasters

Freehand track building through GUI drags is slow and error-prone. In order of preference:

1. **Prebuilt coasters.** Use the game's pre-designed coaster options where they exist, and place them like any other ride. This turns a precision task into a placement task. **VERIFY** what your build offers.
2. **Saved designs.** Build a handful of coasters manually, save them as designs, and have macros load and place them.
3. **Scripted track building.** Only after M7. Use a small DSL (`straight 3`, `left_turn`, `lift_hill 4`) where each primitive is a macro with a post-condition check, and snapshot the park (save) before each segment so a failure can roll back.

### Appendix D: optional optimizations

- **Faster capture.** `CGWindowListCreateImage` through pyobjc avoids spawning a process per capture, but Apple has deprecated it on recent macOS. Treat it as an optional fast path behind a feature flag, and fall back to `screencapture` on any error. **VERIFY** it still works on your macOS version.
- **Persistent template cache.** Load and preprocess all templates once per process. Relevant mainly if you add the daemon.
- **Diff-based verification.** After an action, compute a frame diff on a region of interest to confirm that something changed, before running heavier template checks.
- **Adaptive waiting.** Replace fixed `wait_ms` with `wait_template` wherever a screen has a recognizable arrival marker.

### Appendix E: quick-start checklist

- [ ] Step 0 done: runtime chosen, config header filled in
- [ ] Game windowed at a fixed resolution; baseline save made
- [ ] Bindings copied from the in-game Controls screen
- [ ] Screen Recording and Accessibility granted to the right executable, process restarted
- [ ] `uv sync`; `rct3ctl doctor` passes
- [ ] 10 core templates captured and verified (including `btn_pause`, `ind_paused`)
- [ ] `tick 10` pauses again every time
- [ ] STOP file and failsafe corner both verified to abort an action
- [ ] `backup-saves` produces a copy
- [ ] AGENTS.md in place, first scripted task completed
