# Repository instructions for coding agents

## Purpose and authority

Implement personal-use computer control for the owner's existing native Steam
installation of RCT3 Complete Edition on an Intel Mac. The first consumer is
Antigravity CLI, connected through a local stdio MCP server.

Read these documents before implementing:

1. [SPEC.md](SPEC.md): authoritative v1 requirements and acceptance criteria.
2. [IMPLEMENTATION.md](IMPLEMENTATION.md): suggested build sequence and handoff.

`rct3-mcp.md` is historical background. Its CLI-first architecture, templates,
OCR, macros, save management, and optional extensions are not requirements unless
SPEC explicitly includes them. If the implementation plan conflicts with SPEC,
follow SPEC. Follow subsequent explicit owner instructions over repository docs
and update affected documentation when scope changes.

This file guides development. Put instructions for the agent playing the game
in `GAMEPLAY.md`; do not copy the old walkthrough's gameplay loop into this file
as if it were the repository's development workflow.

## Working approach

- Work toward all three SPEC acceptance gates, starting with live capture/input
  and Antigravity screenshot feasibility. Do not build the full system before
  testing that integration.
- Make routine implementation choices independently. Use Python, `uv`, and a
  maintained MCP SDK; keep game control independent of transport and provider.
- Keep the implementation small. Do not add OCR, template libraries, macros,
  remote services, additional runtimes, a full CLI, or model API integrations
  without a demonstrated need and agreement on a material scope expansion.
- Check current primary documentation when selecting or using external APIs.
  Treat suggested macOS APIs as candidates until verified on this machine.
- Preserve unrelated owner changes. Do not commit, push, or publish unless asked.
- Keep concise progress updates, including what has been verified and what is
  still uncertain. Record enough validation state for a later agent to resume
  without repeating completed live tests unnecessarily.

## Live game work

- The owner launches the game and loads the park. Request missing permissions,
  suitable park setup, or a human interruption test only when needed, with exact
  instructions. Continue useful independent work while those steps are pending.
- Announce when live input tests will take over the mouse/keyboard. During an
  authorized implementation session, routine reversible checks do not need a
  separate approval for every click.
- Start with harmless actions. Before live holds or drags, have bounded durations,
  cleanup, and a usable stop mechanism in place.
- Follow SPEC's window identity, coordinate, focus, bounds, and interruption
  requirements. Never hide partial execution or blindly retry uncertain input.
- After a human stop, wait for explicit instruction before resetting it. Discard
  old work and observe again rather than replaying queued actions.
- Leave saving to the owner. Do not automatically load, quit, overwrite saves,
  alter game files, or change global operating-system settings.
- Use the implemented MCP tools for the final construction demonstration. Native
  input code used to develop or diagnose the backend is not a substitute for
  demonstrating the agent-facing tool interface.

## Checks and evidence

Reproducible commands established and verified:

- Installing locked dependencies with `uv`:
  `uv sync`
- Running focused automated tests without a GUI or permissions:
  `uv run pytest -v`
- Checking lint and formatting:
  `uv run ruff check .`
  `uv run ruff format --check .`
- Starting the stdio MCP server:
  `uv run rct3-mcp`
- Running local diagnostics:
  `uv run rct3-diagnostics`

Run relevant checks before handoff. Add meaningful automated coverage for
coordinate transforms, validation, serialization, interruption, input cleanup,
and MCP image/metadata output as required by SPEC.

Use actual live evidence for game capture, input acceptance, focus behavior,
human interruption, and construction. Mocked tests alone cannot pass those gates.
Record results and limitations in `VALIDATION.md`; mark blocked or unperformed
checks pending with a concrete next step. Never claim the owner granted a
permission or performed an action without observing or receiving confirmation.

Reserve server stdout for MCP protocol traffic. Keep local configuration,
personal screenshots, and run logs out of git. Do not make private screenshots
into committed fixtures by default.

V1 is complete only when all three SPEC gates pass on the owner's Mac. If live
validation remains pending, report implemented behavior and the exact outstanding
check without presenting the project as fully accepted.
