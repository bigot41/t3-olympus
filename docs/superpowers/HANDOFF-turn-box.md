# Handoff: task list, next-step box and New profile button (branch `turn-box`)

Started 2026-10-22 by Mohammed's dev agent; handed over part way through. Tasks 1–3 of 7 are done. Pick it up from Task 3's review.

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

| Task | State | Commits |
|---|---|---|
| 1. MCP server: `update_plan` + `wrap_up` rules, `instructions` | done, reviewed | `40d08a1` |
| 2. `turnlogic.js` shared rules (`OlympusTurn.view`) | done, reviewed | `e72ec7b` |
| 3. Socket hook (`olympus-hook.js`, inlined into `index.html`), `patch.refresh()`, `launch.pyw` | done, **not reviewed yet** | `c1fc7db`, `f4eb82f` |
| 4. `turnbox.js`: draw the list and box above the composer; delete `nextstep.js` | not started | |
| 5. `helper.py`: `/turn` fallback reading the transcript incrementally; remove `/wrapup` | not started | |
| 6. New profile button: `make_profile()`, `POST /profile`, `GET /gods/themes`, dialog in `olympus.js` | not started | |
| 7. README/HANDOFF docs, `install.py`, live check in T3, merge | not started | |

Tests: `python -m unittest discover -s tests -v` (15 OK) and `node --test` from the repo root (39 pass). On Node 24, `node --test tests/` fails because it reads `tests/` as a module path.

## Next steps

1. **Review Task 3** against plan Task 3 (+ the ruling below). Check: the hook can never throw into T3's code; the hook source has no `</script>`; `refresh()` never writes `server.asar`; `c1fc7db` alone is broken (the inline line landed in `f4eb82f`), fine to squash.
2. **Do Tasks 4–7** from the plan. Task 4 must also:
   - swap `nextstep.js` for `turnbox.js` in `patch.files()`;
   - add the `test_patch` check that `olympus.js` has no `olympus-next`.
3. **Live check (Task 7).** The dev session runs inside T3. Don't restart T3 mid-session. Instead:
   - run `python -c "import patch; print(patch.refresh())"`;
   - press Ctrl+R in T3;
   - open a new chat in a profile and give it a multi-step task.

   Confirm these first, because they are inferred from T3's bundle and haven't been seen live:
   - the socket path ends in `/ws`;
   - a real `mcp__olympus__wrap_up` item arrives as `{type:"dynamic_tool", toolName, input, status}`;
   - `GET /api/orchestration/threads/:id` with header `x-t3-orchestration-protocol: 2` works from page JS.

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
