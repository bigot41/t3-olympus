"""The olympus MCP server: update_plan (a live task list) and wrap_up (a recap card with answer buttons).

    python wrapup_mcp.py --register <folder>    make the tools available to Claude chats in that folder

Claude calls update_plan while it works and wrap_up when the turn is done. Both calls are saved in the
chat's transcript like any tool call; the T3 window rebuilds the list and card from them (see
olympus-hook.js and turnbox.js). The server keeps the plan in memory (one process per Claude session),
applies the same limits the window does, and answers with short notes Claude can act on. Its
`instructions` go into Claude's system prompt, so Claude knows when to call each tool.
"""
import json, os, re, subprocess, sys

NAME = "olympus"
MAX_STEPS, MAX_STEP_CHARS, MAX_RECAP, MAX_ASK = 12, 160, 1200, 100
MAX_BUTTONS, MAX_LABEL_CHARS, MAX_LABEL_WORDS, MAX_MESSAGE = 2, 24, 4, 300
STATUSES = ("pending", "in_progress", "completed")
SCOPES = ("first_task", "continuation", "new_task")
HIDDEN = re.compile("[​-‏ -‮⁠-⁤﻿]")

INSTRUCTIONS = """\
The user watches two things the app draws from your tool calls: a task list while you work and a recap card when you finish.

Task list. For any request that edits files or takes more than one command, the first tool call of the turn goes out together with update_plan carrying the whole plan: {"items": [...], "scope": ...}. Items are short imperative phrases in order, the step you are starting in_progress, the rest pending. scope says what the request is to this session: first_task when nothing is finished yet, then continuation (builds on earlier work, the default) or new_task (unrelated). Use update_plan instead of TodoWrite or the Task tools; the app shows only this list. When you start the next step, send {"advance": true} with that step's first call. If you are already past the step shown, send {"done": [numbers], "start": number}, counting from 1. Keep exactly one step in_progress. Do not write the plan out again as a list in your text.

Wrap-up. Every turn in which you kept a task list, changed files or ran commands ends with wrap_up, called once when the work is done and before your closing message. recap is two or three sentences on what is now true and where it stands, including anything not done or not checked. Add ask only when the user has to decide or do something: one short question, the decision alone, without the options and without a recommendation. Then give one or two buttons that answer it, your recommendation first; a label is one to three words, the message is what gets sent as the user's reply. When nothing is waiting on the user, send the recap alone and no card is drawn. Set blocked when you cannot go on without the user. After the call, write your closing message in full; the recap does not replace it, and do not repeat the question there.

Skip both for short answers and ordinary conversation. If you are a subagent, call neither.
"""

PLAN_TOOL = {
    "name": "update_plan",
    "description": (
        "Keeps the task list the user sees while you work. Send the whole list with items (and scope), "
        "then move it along with advance, or done and start, using step numbers counted from 1."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "enum": list(SCOPES),
                      "description": "Needed with items: what this request is to the session."},
            "items": {"type": "array", "minItems": 1, "maxItems": MAX_STEPS,
                      "description": "The whole plan, in order. Replaces any earlier list.",
                      "items": {"type": "object", "required": ["content", "status"], "properties": {
                          "content": {"type": "string", "maxLength": MAX_STEP_CHARS,
                                      "description": "A short imperative phrase."},
                          "status": {"type": "string", "enum": list(STATUSES)}}}},
            "advance": {"type": "boolean",
                        "description": "Finish the step in progress and start the next pending one."},
            "done": {"type": "array", "items": {"type": "integer", "minimum": 1},
                     "description": "Step numbers (from 1) to mark completed."},
            "start": {"type": "integer", "minimum": 1, "description": "Step number (from 1) to start."},
        },
    },
}

WRAP_TOOL = {
    "name": "wrap_up",
    "description": (
        "End your turn with this when you kept a task list, changed files or ran commands. It shows the "
        "user a recap and, when the next move is theirs, one question with one or two reply buttons. "
        "Call it once, after the work and before your closing message. Skip it for short answers and "
        "plain conversation."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "recap": {"type": "string", "description": "Two or three short sentences (about 300 characters): "
                      "what is now true, where it stands, what isn't done or checked."},
            "ask": {"type": "string", "description": "Only when the user must decide or act: one short "
                    "question (about 100 characters), the decision alone, no options."},
            "blocked": {"type": "boolean", "description": "True when you cannot go on without the user."},
            "actions": {"type": "array", "maxItems": MAX_BUTTONS,
                        "description": "One or two reply buttons answering ask, your recommendation first.",
                        "items": {"type": "object", "required": ["label"], "properties": {
                            "label": {"type": "string", "description": "One to three words, e.g. 'Yes, ship it'."},
                            "message": {"type": "string", "description": "The reply the button sends, in the "
                                        "user's voice. Defaults to the label."}}}},
        },
        "required": ["recap"],
    },
}
TOOLS = [PLAN_TOOL, WRAP_TOOL]
plan = None  # this session's task list: [{"content", "status"}], or None before the first update_plan


def _text(v):
    return v.strip() if isinstance(v, str) else ""


def _button(raw):
    """A valid {label, message}, or None. Long messages are cut; bad labels are dropped."""
    if not isinstance(raw, dict):
        return None
    label = _text(raw.get("label"))
    message = _text(raw.get("message")) or label
    if not label or len(label) > MAX_LABEL_CHARS or len(label.split()) > MAX_LABEL_WORDS:
        return None
    if any(t[0] in "/!" or HIDDEN.search(t) for t in (label, message)):
        return None
    return {"label": label, "message": message[:MAX_MESSAGE]}


def normalize_wrap_up(args):
    """Read a wrap_up call (old field names too) into a card, plus advice on what was trimmed or dropped."""
    recap = _text(args.get("recap")) or _text(args.get("outcome")) or _text(args.get("next_recap"))
    ask = _text(args.get("ask")) or _text(args.get("next_ask")) or _text(args.get("next_brief"))
    raw = args.get("actions")
    if raw is None:
        raw = args.get("next_actions")
    raw = raw if isinstance(raw, list) else []
    blocked = args.get("blocked") in (True, "true") or bool(args.get("needs_user"))
    valid = [b for b in map(_button, raw) if b]
    advice = []
    if any(k in args for k in ("outcome", "next_recap", "next_ask", "next_brief", "next_actions", "needs_user")):
        advice.append("Old field names were read this time. Use recap, ask, actions and blocked.")
    if len(recap) > MAX_RECAP:
        recap = recap[:MAX_RECAP]
        advice.append(f"recap was cut at {MAX_RECAP} characters; aim for about 300.")
    elif len(recap) > 300:
        advice.append("recap is two or three sentences, about 300 characters.")
    if len(ask) > MAX_ASK:
        advice.append("ask is the decision alone in one short sentence, about 100 characters.")
    if len(valid) > MAX_BUTTONS:
        advice.append(f"Use at most {MAX_BUTTONS} buttons; the rest were dropped.")
    if len(valid) < len(raw):
        advice.append("A button was dropped: a label is one to three words (24 characters at most), and "
                      "neither label nor message may start with / or ! or carry invisible characters.")
    if any(isinstance(b, dict) and len(_text(b.get("message"))) > MAX_MESSAGE for b in raw):
        advice.append(f"A button message was cut at {MAX_MESSAGE} characters.")
    card = {"recap": recap or None, "ask": ask or None, "blocked": blocked, "actions": valid[:MAX_BUTTONS]}
    if ask and not card["actions"] and not blocked:
        advice.append("No card was drawn: a question needs at least one valid button. "
                      "If nothing is waiting on the user, send the recap alone.")
    card["advice"] = advice
    return card


def shows_box(card):
    return bool(card["blocked"] or (card["ask"] and card["actions"]))


def _parse_steps(items):
    steps = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and _text(it.get("content")) and it.get("status") in STATUSES:
            steps.append({"content": _text(it["content"])[:MAX_STEP_CHARS], "status": it["status"]})
    return steps[:MAX_STEPS]


def _summary(steps):
    n, live = len(steps), [i + 1 for i, s in enumerate(steps) if s["status"] == "in_progress"]
    if len(live) == 1:
        return f"Step {live[0]} of {n} is in progress."
    if live:
        return (f"Steps {', '.join(map(str, live))} of {n} are in progress; keep one and send "
                '{"done": [n]} for any you finished.')
    done = sum(s["status"] == "completed" for s in steps)
    if done == n:
        return "Every step is done."
    return f'No step is in progress ({done} of {n} done); {{"start": n}} starts one.'


def apply_plan(steps, args):
    """Apply one update_plan call to the steps (None = no plan yet).
    Returns (new steps, result text, refused); a refused call leaves the steps unchanged."""
    items = args.get("items")
    has_update = any(args.get(k) not in (None, False, "false", []) for k in ("advance", "done", "start"))
    if items is not None:
        if args.get("scope") not in SCOPES:
            return steps, 'items also needs "scope": first_task, continuation or new_task. Send it again with scope.', True
        new = _parse_steps(items)
        if not new:
            return steps, "items needs at least one step with content and status.", True
        text = f"Plan shown ({len(new)} steps)."
        if sum(s["status"] == "in_progress" for s in new) > 1:
            text += " Keep only one step in progress."
        if has_update:
            text += " items sets every status, so the advance/done/start sent with it changed nothing."
        return new, text, False
    if not has_update:
        return steps, 'Pass {"items": [...], "scope": ...} (whole plan), {"advance": true}, or {"done": [n], "start": m}.', True
    if not steps:
        return steps, ("Nothing changed: there is no list in this session. Send the whole list with "
                       '{"items": [...], "scope": ...}.'), True
    n, done, start = len(steps), args.get("done") or [], args.get("start")
    done = done if isinstance(done, list) else [done]
    if any(type(x) is not int or not 1 <= x <= n for x in done + ([] if start is None else [start])):
        return steps, (f"Nothing changed: done and start take whole step numbers from 1, and the list has {n} "
                       "step(s). Send the update again with numbers that name a step, or the whole list."), True
    new = [dict(s) for s in steps]
    for x in done:
        new[x - 1]["status"] = "completed"
    if start is not None:
        new[start - 1]["status"] = "in_progress"
    if args.get("advance") in (True, "true"):
        cur = next((i for i, s in enumerate(new) if s["status"] == "in_progress"), None)
        if cur is not None:
            new[cur]["status"] = "completed"
        nxt = next((i for i in range(cur + 1, n) if new[i]["status"] == "pending"), None) if cur is not None else None
        if nxt is None:
            nxt = next((i for i, s in enumerate(new) if s["status"] == "pending"), None)
        if nxt is not None:
            new[nxt]["status"] = "in_progress"
    return new, "Plan updated. " + _summary(new), False


def register(folder):
    """Add this server to Claude Code for one folder (local scope: stored in ~/.claude.json, no prompt)."""
    folder = os.path.abspath(os.path.expanduser(folder))
    subprocess.run(["claude", "mcp", "remove", "-s", "local", NAME], cwd=folder, capture_output=True)
    r = subprocess.run(["claude", "mcp", "add", "-s", "local", NAME, "--", sys.executable.replace(
        "pythonw.exe", "python.exe"), os.path.abspath(__file__)], cwd=folder, capture_output=True, text=True)
    print(f"next-step card on for {folder}" if r.returncode == 0 else f"couldn't add it to {folder}: {r.stderr.strip()}")


def send(msg):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", **msg}) + "\n")
    sys.stdout.flush()


def reply(id, result):
    send({"id": id, "result": result})


def tool_result(text, error=False):
    out = {"content": [{"type": "text", "text": text}]}
    if error:
        out["isError"] = True
    return out


def call_tool(name, args):
    global plan
    if not isinstance(args, dict):
        args = {}
    if name == "update_plan":
        plan, text, error = apply_plan(plan, args)
        return tool_result(text, error)
    if name == "wrap_up":
        card = normalize_wrap_up(args)
        if not card["recap"]:
            return tool_result("recap is required: what is now true or changed and where it stands, "
                               "in two or three sentences.", True)
        text = ("Shown to the user as a card. Now write your closing message; don't repeat the question."
                if shows_box(card) else "Nothing is waiting on the user, so no card is drawn. Now write your closing message.")
        return tool_result(" ".join([text] + card["advice"]))
    return tool_result(f"Unknown tool: {name}", True)


def serve():
    for line in sys.stdin:
        msg = json.loads(line)
        method, id = msg.get("method"), msg.get("id")
        if id is None:  # notifications need no answer
            continue
        if method == "initialize":
            reply(id, {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2025-06-18"),
                       "capabilities": {"tools": {}}, "serverInfo": {"name": NAME, "version": "2"},
                       "instructions": INSTRUCTIONS})
        elif method == "tools/list":
            reply(id, {"tools": TOOLS})
        elif method == "tools/call":
            p = msg.get("params") or {}
            reply(id, call_tool(p.get("name"), p.get("arguments")))
        else:
            send({"id": id, "error": {"code": -32601, "message": "unknown method"}})


if __name__ == "__main__":
    if sys.argv[1:2] == ["--register"] and len(sys.argv) == 3:
        register(sys.argv[2])
    else:
        serve()
