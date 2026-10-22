# Handoff: task list, next-step box and New profile button (branch `turn-box`)

Started 2026-10-22 by Mohammed's dev agent, continued the same day from another machine. All 7 tasks are done and checked live in T3. What's left is taking PR #3 out of draft and merging (after PR #2).

## What this is

PR #1 added a next-step card that polls the helper every 2 seconds, and the helper re-reads the whole Claude transcript each time. This branch makes it work the way Claude desktop does:

- **Task list.** A live list that ticks off steps while Claude works.
- **Next-step box.** A recap with answer buttons when the turn ends.
- **No polling.** Both are drawn the moment T3 receives the tool call.
- **New profile button.** A "+" in the sidebar replaces `python new_profile.py`.

Read these first:
- the design: `docs/superpowers/specs/2026-10-22-turn-box-design.md`, including "Decisions from the builder check";
- the plan: `docs/superpowers/plans/2026-10-22-turn-box.md`, which has a step-by-step section for each task;
- how T3's socket and data work: `docs/superpowers/notes/t3-hook-findings.md`, from reading T3's bundle.

The behaviour comes from reverse-engineering Claude desktop 3.1623. Those notes quote Anthropic's prompt text, so they stay out of this public repo. The design doc already has everything needed: fields, limits and rules. **Write our own wording for all tool and prompt text.**

## Status

`handoff-tasks` (PR #2: temporary chats, split view, dictation, review fixes) was merged into this branch first (`b8f0697`), so this PR now also shows PR #2's commits until #2 is merged.

| Task | State | Commits |
|---|---|---|
| 1. MCP server: `update_plan` + `wrap_up` rules, `instructions` | done, reviewed | `40d08a1` |
| 2. `turnlogic.js` shared rules (`OlympusTurn.view`) | done, reviewed | `e72ec7b` |
| 3. Socket hook, `patch.refresh()`, `launch.pyw` | done, reviewed; one fix | `c1fc7db`, `f4eb82f`, `d30311e` |
| 4. `turnbox.js` replaces `nextstep.js` | done, checked live | `9e3d33b` |
| 5. `helper.py` `/turn` incremental fallback; `/wrapup` removed | done, checked live | `3e4ee74` |
| 6. New profile button (`make_profile`, `POST /profile`, `GET /gods/themes`, dialog) | done, checked live | `cc7e9a0` |
| 7. README, install run, sidebar fix, final live check | done | README commit, `0d4bdbd`, final-check fixes |

Tests: `python -m unittest discover -s tests` (39 OK) and `node --test` (39 pass).

### Checked live in T3 (with the DevTools port)

- The orchestration socket's path is `/ws`. Olympus calls arrive as `{type: "dynamic_tool", toolName: "mcp__olympus__update_plan" | "mcp__olympus__wrap_up", input, status}`; your messages as `user_message`; run status goes `running` → `waiting` → `completed`. Each event comes twice (harmless, items are kept by id).
- **Not as the notes expected:** `GET /api/orchestration/threads/:id` from the page returns T3's HTML, because the page's origin doesn't serve that API, and `orchestration.subscribeThread` sends only events after the client's last known sequence, so a chat T3 has seen before sends no history. `turnbox.js` therefore fills a chat once from the helper's `/turn` (same item ids as T3's, so nothing shows twice) and uses the socket for everything live.
- After a reload the box came back from `/turn`; clicking Yes sent the reply, the list showed and ticked during the turn, the new box appeared at the end; the box stays with its own chat.
- New profile: the dialog made a throwaway profile (folder, `CLAUDE.md`, T3 project, god in `gods.json`, `olympus` connected), "Start a chat in it" opened it under its god with no reload; then it was removed.

### Found and fixed on the way

- The hook gives each `/ws` socket its own `send`, which hid T3's commands from `temporary.js` (PR #2), so leaving a temporary chat stopped deleting it. The hook now records the command socket as `window.olympusT3Socket`.
- `make_profile` takes about 15 s, mostly `claude mcp add`; the dialog shows "Creating…". An existing T3 project counts as added.
- The sidebar lists chats, not projects, so a new empty profile isn't in it until it has a chat; T3's project chooser lists it at once, hence the "Start a chat in it" button instead of a reload.
- The extra "+" squeezed the sidebar's Search label; the button moved to the bottom row after Usage (`0d4bdbd`).
- Final check: in a brand-new chat T3 gets the turn's start in its launch reply, before subscribing, so the hook never saw "running". `turnbox.js` now takes running from T3's own Stop generation button; the hook also passes on events from T3's wider subscription that name their chat.
- Final check result: a new chat given a plain multi-step task (no tool names) kept the list and ended with `wrap_up` on its own; spinner, ticks and clearing all worked. A recap with no question correctly draws no box.

## Next steps

1. Merge PR #2 first, then take PR #3 out of draft and merge it (it contains PR #2's commits too).
2. On a machine with profiles, run `python install.py` so each profile gets the `olympus` tools.

## Facts found along the way

- **Run status.** `run.updated` payloads carry `status`. Seen values are `running`, `waiting` and `completed`, read from `~/.t3/userdata/statev2.sqlite`, table `orchestration_events`. The hook emits `event.payload ?? event`. Treat anything other than running or waiting as "turn ended".
- **MCP loading.** T3 starts Claude with setting sources `user, project, local`. So `claude mcp add -s local` in a profile folder should give its chats the `olympus` tools.
- **Install.** `install.py` has never been run on Mohammed's machine, so there are no `olympus` entries in `~/.claude.json` yet.
- **Task list.** T3 already shows Claude's own TodoWrite list above the composer (`data-composer-tasks-list`). The instructions tell Claude to use `update_plan` instead.
- **Patch state.** `patch.is_patched()` is False on this branch because the client files changed. Opening T3 from the shortcut while this branch is checked out will re-patch with half-done code. Mohammed's local checkout has been switched back to `main` to avoid that.

## Rulings made so far (check these)

- **Task 3 keeps `nextstep.js`.** Task 3 concatenates `cards.js, turnlogic.js, nextstep.js, panel.js`, and Task 4 does the swap. This is so Task 3 doesn't depend on a file Task 4 creates. If it's wrong, one line moves.
- **Commit attribution.** Subagent commits carry the implementing model's own Co-Authored-By line, which is Sonnet. Changing it means editing a trailer.
- **Builder-check decisions.** All the decisions in the design doc's "Decisions from the builder check" section were the dev agent's call. They cover registration scope, visibility rules, no restart (hook inlined in `index.html`), the New profile flow and plan-after-restart.

## Minor review findings, deferred

- **Task 1:**
  - no tests for dropping a button with invisible characters, or for cutting a message at 300 characters;
  - plan result texts are only loosely asserted;
  - the `HIDDEN` regex uses literal invisible characters; switch to `\u` escapes;
  - "Plan shown (1 steps)." has a grammar slip;
  - no advice when steps over 12, or invalid steps, are dropped;
  - `turn_cases.json` has no trailing newline.
- **Task 2:**
  - JS accepts float step numbers (`2.0`) that Python refuses;
  - the two sides strip slightly different whitespace (`\x1c-\x1f`, `\x85`);
  - `advance` on a fully completed list after a `wrap_up` counts as a plan call, so a finished list shows as live;
  - `parseSteps` is called twice at `turnlogic.js:186`.
