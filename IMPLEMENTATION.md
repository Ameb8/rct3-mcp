# Implementation handoff

Read [SPEC.md](SPEC.md) first. It defines required behavior and acceptance.
This document suggests an execution sequence; internal design choices may change
when evidence supports a simpler working approach.

## 1. Establish a minimal working slice

Start with the real integration risks rather than building every tool at once.

1. Inspect the existing repository and the installed Python/tooling environment.
   Select a Python version and maintained MCP SDK compatible with this Intel Mac
   and macOS version. Check current primary documentation for APIs you use.
2. Create a minimal `uv` project, dependency lockfile, and gitignore entries for
   local configuration, virtual environments, captures, and run logs.
3. Identify the actual game process and window. Add a small diagnostic entry
   point to report candidates and relevant macOS permissions. Keep imports and
   offline tests usable without an open game or permission prompts.
4. Implement a game-window capture and explicit image-to-screen transform.
   Record image dimensions, content bounds, scale, and window geometry together.
5. Expose `status` and `observe` through a local stdio MCP server. Verify protocol
   startup and ensure ordinary logging never reaches stdout.
6. Add enough input for the first live check: click, bounded key press, camera
   drag, and scroll. Build input tracking, release-on-error, finite durations,
   and a usable stop mechanism before injecting live input.
7. Configure the installed Antigravity CLI to launch the server. Verify the
   agent can interpret an inline screenshot and use the tool coordinates.

Keep the first implementation small and replaceable. It is acceptable to extend
this slice into the final code; it does not need a separate prototype framework.

**Checkpoint:** pass SPEC Gate 1. Record actual observations, especially screenshot
consumption, input acceptance, camera bindings, and building while paused. Do not
implement OCR or templates to avoid testing the host's vision path.

If permissions or a prepared game are missing, give the owner exact instructions
for the next live check. Continue independent offline work, but retain the gate
as pending and avoid speculative compatibility work.

## 2. Complete the control contract

Use the proven capture/input path to implement all tools in SPEC section 7.

Keep one source of truth for window selection, image geometry, current frame,
stop state, and held inputs. Keep the MCP adapter thin: tool validation and
serialization should call reusable control operations rather than duplicate
macOS logic across handlers.

Pay particular attention to these behaviors:

- Coordinates always refer to the image delivered to the agent. Test content
  offsets, display scaling, and translation after window movement.
- Resizing, changing capture scale, replacing the selected window, or resetting
  stop invalidates the current observation. Return useful recovery instructions.
- Validate an entire action before sending any down event. Bounds checks cover
  the complete drag, not only its first point.
- Recheck focus and interruption during long operations. Use short interruptible
  intervals rather than one blocking sleep for a hold or wait.
- Ordinary operations serialize, while stop remains responsive. Do not hold a
  lock needed by stop for the duration of an ordinary action. A synchronous
  event-posting loop must not block the MCP event loop from accepting stop or
  cancellation; choose a small worker or cooperative execution design as needed.
- A stop or cancellation must prevent previously queued actions from executing
  later after reset. Invalidate/cancel that queued work explicitly.
- Release held input through a cleanup path that bypasses ordinary input guards.
  Test errors between down and up, including modifiers.
- Never retry uncertain input automatically. Describe partial execution in the
  failure result and require the agent to inspect the screen.

Add focused fake-backend tests as these behaviors are implemented. Test observable
contracts and failure behavior rather than a particular private module layout.
Keep native integration details behind small boundaries that tests can replace.

**Checkpoint:** pass SPEC Gate 2 with both automated and live evidence. Test the
human interruption gesture during each of drag, key hold, and wait; a unit test
of a stop flag is insufficient evidence for the actual gesture.

## 3. Validate useful construction

Write an initial `GAMEPLAY.md` from SPEC section 10 and use it for the demo.
Have the owner load a suitable test park if one is not already available.

Run SPEC Gate 3 through Antigravity CLI. The controlling agent must inspect images
and use the exposed tools for construction; a developer clicking through the
steps or a hardcoded placement script does not establish acceptance.

Use representative before/after screenshots to verify:

- A flat ride, its entrance and exit, and connected paths/queue.
- The ride's visible open/setup status.
- An accessible open shop.
- Several placed scenery items.

When a task fails, distinguish an input/capture defect from an agent navigation
mistake. Fix the responsible layer, then repeat the affected check. Improve
tool descriptions or gameplay guidance when that resolves the issue; avoid
turning each menu sequence into a server-side macro.

Leave saving to the owner. Report anything the screenshots do not establish
confidently, including uncertain connections or facility status.

## 4. Prepare a reproducible handoff

Finish the documentation required by SPEC section 12:

- `README.md`: actual setup and launch commands, diagnostic usage, Antigravity
  configuration, permissions, window setup, stop/reset, recovery, and run data.
- `GAMEPLAY.md`: operating instructions for the agent controlling the game.
- `AGENTS.md`: update its check commands once the project tooling exists.
- `VALIDATION.md`: a concise record of results and remaining limitations.

For each acceptance gate, record pass/pending/fail, what was exercised, the
observed result, and local evidence paths. Distinguish tested behavior from
assumptions and give exact next steps for pending checks. Keep personal images
and machine-specific configuration out of version control.

Run the project's documented lint/format checks and relevant automated tests.
Provide a final report with working behavior, live gates passed, commands run,
and any remaining owner action. Do not declare v1 complete until all three SPEC
gates have passed.

## Suggested starting layout

This layout is a starting point, not an additional requirement:

```text
pyproject.toml
uv.lock
src/rct3_control/
    window_capture.py
    input.py
    session.py
    server.py
    diagnostics.py
tests/
README.md
GAMEPLAY.md
VALIDATION.md
runs/                 # ignored
```

Split or combine files when it makes the implementation clearer. Do not recreate
the old walkthrough's module list or introduce a service framework to satisfy
this suggested layout.
