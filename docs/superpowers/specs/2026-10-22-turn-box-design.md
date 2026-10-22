# Task list, next-step box and New profile button: design

Date: 2026-10-22. Owner: Mohammed (TCTS). Builds on PR #1 (wrap_up card, Ctrl+Shift+B context panel, `new_profile.py`).

## Why

PR #1 added a next-step card, but it polls the helper every 2 seconds, and the helper re-reads the whole Claude transcript each time. It also behaves differently from Claude desktop: it always shows a box, has no task list, and Claude calls the tool unreliably because nothing in the system prompt asks it to. Mohammed wants it to work the way Claude desktop's does, with T3 Olympus's god themes. He also wants to create a profile from inside T3 instead of typing `python new_profile.py`.

Success: in a T3 chat, Claude keeps a live task list while it works and ends the turn with a recap box, both appearing the moment Claude makes the call and both drawn in the profile's theme. A new profile can be made from a sidebar button and shows up with its god without retyping anything.

## Reference behaviour

Reverse-engineered from Claude desktop 3.1623 (notes kept outside the repo in `C:/Users/moham/re-work/notes/ccd_turn_spec.md`, `t3_hook_findings.md`). Claude desktop runs an in-process MCP server `ccd_turn` with two tools, `update_plan` and `wrap_up`, adds a section to Claude's system prompt saying when to call them, and rebuilds the list and box from the tool calls' inputs in the normal message stream. It reads no files and never polls.

**This repo is public.** Match the behaviour, limits and field names, but write our own tool descriptions, prompt text and result messages. Do not paste Anthropic's text into the repo.

## Goals

1. **One MCP server, two tools** (`wrapup_mcp.py`, server name stays `olympus`, so the tools are `mcp__olympus__update_plan` and `mcp__olympus__wrap_up`).
   - `update_plan`: `scope` (`first_task | continuation | new_task`, required with `items`), `items` (1–12 of `{content ≤160 chars, status: pending|in_progress|completed}`), `advance` (true or "true"), `done` (1-based step numbers), `start` (one step number). Update order: `done` → `start` → `advance` (completes the in_progress step, starts the next pending one after it, else the first pending anywhere). `items` replaces the whole list; advance/done/start in the same call are ignored with a note. The server keeps the plan in memory (one stdio process per Claude session) and answers with short plain results ("Plan shown (N steps).", "Step k of N is in progress.", "Every step is done.", "Nothing changed: …"), warning when more than one step is in_progress.
   - `wrap_up`: `recap` (required, aim ~300 chars, cut at 1200), `ask` (~100 chars), `blocked` (bool), `actions` (1–2 reply buttons `{label ≤24 chars and ≤4 words, message ≤300 chars}`, recommendation first). Accept the old aliases `outcome`/`next_recap` → recap, `next_ask`/`next_brief` → ask, `next_actions` → actions, non-empty `needs_user` → blocked. Drop a button whose label or message starts with `/` or `!` or contains invisible characters. A box is drawn when `blocked`, or when there is an `ask` and at least one valid button; otherwise the result says nothing is pending and no box is drawn. Problems (too many buttons, long label) are returned as advice for next time, never as an error, except a missing recap. The result tells Claude to write its closing message after the call and not repeat the question.
   - No app-action buttons (commit, create_pr, …): T3 has no such commands. Reply buttons only.
2. **System-prompt instructions** via the MCP `initialize` result's `instructions` field, which Claude Code adds to the system prompt. Our own wording, covering: use `update_plan` instead of TodoWrite/Task tools for multi-step work; send the whole plan with the first tool call; `advance` alongside the call that starts the next step; don't restate the plan in text; every turn that kept a list, changed files or ran commands ends with `wrap_up` before the closing message; recap is 2–3 sentences of what is now true incl. what isn't done or verified; ask only when the user must decide, the decision alone, no options listed; subagents don't call either tool.
3. **No polling.** A small hook script (source file `olympus-hook.js`), inlined by `patch.py` into `index.html` as a plain (non-module, non-defer) script before T3's module script, wraps `window.WebSocket` for T3's `/ws` socket, maps request ids to thread ids from outgoing `orchestration.subscribeThread` requests, parses incoming `Chunk` frames and fires a `window` event `olympus:turn-item` with `{threadId, item}` for each turn item. After a page load or thread switch, one `GET /api/orchestration/threads/:id` (header `x-t3-orchestration-protocol: 2`) fills in the current state; if that fails, call the helper's `/wrapup` and `/plan` once. The 2-second interval goes.
4. **Rendering (`turnbox.js`, replaces `nextstep.js`).** One themed card directly above the composer (the spot under the latest message; T3's message list is virtualised, so we don't inject into it). It shows:
   - while a turn runs: the task list rebuilt from the thread's `update_plan` calls (same reducer as the server, run on the inputs of calls that didn't error). Completed: filled check, muted. In progress: spinner while the turn runs, dots when idle. Pending: muted empty circle. At most 12 visible. A list from before the user's last message is labelled "Plan from before your last message".
   - after the turn ends, when the latest `wrap_up` qualifies as a box: the question in primary text, the recap in secondary text, the buttons (first is primary), an × to dismiss for that turn (no × when blocked). Blocked with no ask: "Claude is waiting on you. Pick a reply or type your own." When `wrap_up` is called, every step shows as completed; when the box has content the list hides.
   - hidden as soon as the user sends a message or a new turn starts. No read-only history record (non-goal).
   - A button sends its `message` (or label) as a normal reply by filling T3's composer and clicking T3's own send button. Ctrl+click only fills the composer. Ctrl+Enter on an empty composer presses the primary button.
   - Colours come from the theme's CSS variables, as the existing cards do.
5. **New profile button.** A small "+" button on the sidebar's projects header (next to T3's own add-project icon, same look) opens a themed dialog: name, god (dropdown of the 18 themes, with Ares listed as `mars`), one-line "what it works on", and "let other chats hand work to it" (the `--agent` option). It POSTs `/profile` to the helper, which runs the same code as `new_profile.py` (refactor that file into an importable `make_profile(name, god, about, agent)` plus its CLI) and writes the "what it works on" line into the new `CLAUDE.md`. The god applies right away: `olympus.js` reads the god map from the helper's `/gods` on load and after a profile is created, instead of only the copy baked in at patch time.
6. **Review fixes from PR #1.** `helper.py` must not throw when the transcript file is missing; any transcript read it keeps (the `/wrapup` fallback) reads only bytes added since the last read, per file.
7. **Install and patch.** `install.py` registers the MCP server in each profile (already does) and the Startup entry. `patch.py` must also rewrite the unpacked client files when their content is stale, not only when `index.html` isn't marked unpacked, so updates to our JS reach T3 on the next launch. Writing the unpacked files doesn't need T3 closed; changing `server.asar` does.

## Non-goals

- App-action buttons, suggestion chips, "+N" overflow menu, links to side sessions.
- The sidebar status line from the recap and the "waiting on you" sidebar marker.
- A read-only record of answered boxes in the transcript.
- Blocking subagent calls with a hook (the instructions tell subagents not to call; the UI ignores calls from subagent turns if T3 marks them).
- Changing T3's own TodoWrite list.

## Anti-goals

- Anything that polls on a timer or re-reads whole transcripts.
- Breaking the existing theme switching, hand-off buttons, hover cards or context panel.
- New dependencies. Plain Python standard library and vanilla JS, matching the repo's style (see `HANDOFF.md` ground rules).
- Committing personal data (`config.json`, `gods.json`, `cards.json`, `handoffs/`, `local/`).

## Constraints

- T3 Code 0.1.x on Windows; DOM hooks listed in `HANDOFF.md`. The WebSocket and HTTP details above come from reading T3's bundle and must be confirmed live (socket path ends in `/ws`; HTTP snapshot works with the page's cookie; a real wrap_up item is `{type:"dynamic_tool", toolName:"mcp__olympus__wrap_up", input, status}`).
- The dev session runs inside T3. Don't close or restart T3 while building. The final check is done by reloading T3's window (Ctrl+R) after writing the unpacked files, or by reopening T3 from the shortcut.
- Pure logic (plan reducer, wrap_up normalising, box rules, frame parsing) is tested with Python `unittest` for the server and plain `node --test` for the JS, with the logic in functions the tests can load.

## Decisions from the builder check (dev agent's calls)

1. **Registration.** Local scope per profile folder (`claude mcp add -s local`, as `wrapup_mcp.register` does). T3 starts Claude with setting sources `user, project, local`, so local-scope servers load. `install.py` has never been run on this machine, which is why `~/.claude.json` has no `olympus` entries yet. Only profile folders get the tools; chats in other folders simply don't have them. Confirm live: a new T3 chat in a profile lists `mcp__olympus__*`.
2. **Visibility, following Claude desktop:**
   - During a turn: the current plan's list, live.
   - Turn ended with a qualifying `wrap_up`: the box; the list hides.
   - Turn ended without a box: the list hides, unless the turn stopped with unfinished steps (interrupted), in which case it stays with dots on the open step.
   - New turn, before Claude sends a new plan: the old plan shows only if it still has unfinished steps, labelled "Plan from before your last message". A fully done old plan never shows.
3. **No T3 restart needed to ship.** The hook is inlined into `index.html` (already unpacked) as a plain `<script>` before T3's module script, instead of a new file that would need a `server.asar` header entry. `patch.py` gets a way to rewrite the unpacked files (`index.html`, `olympus.css`, `olympus.js`) when their content is stale, which works with T3 open; `launch.pyw` does that even when T3 is running. Checking happens with Ctrl+R in T3.
4. **New profile while T3 runs.** Use the `t3 project add` CLI as `new_profile.py` does. If the project doesn't appear in the sidebar by itself, the dialog's success message says so and offers a reload button (`location.reload()`). The new `CLAUDE.md` is generic, built from the name and the "what it works on" line (first line `# <Title> profile`, then "You are the <title> agent. You work on: <about>." and a short "How you work" section); `profile-template/CLAUDE.md` stays for the by-hand route.
5. **Plan after a restart.** The MCP process lives through compaction; only a restart of Claude loses its in-memory plan. When `advance`/`done`/`start` arrive with no plan in memory, the server changes nothing and replies that it has no list in this session and to send the whole list again with `items`. No hooks.

## Left to the builder

- How to detect "turn finished" from T3's events (thread/session status in the stream or snapshot).
- Exact file split between `olympus-hook.js` and `turnbox.js`, and how tests load the JS logic.
- Dialog markup and where exactly the "+" button sits, as long as it matches T3's look.
