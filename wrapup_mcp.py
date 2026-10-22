"""A one-tool MCP server: wrap_up, which ends a turn with a short recap and answer buttons.

    python wrapup_mcp.py --register <folder>    make the tool available to Claude chats in that folder

Claude calls wrap_up(recap, ask, actions); the call is saved in the chat's transcript like any
tool call, and olympus.js (through helper.py's /wrapup) draws it as a card under the last reply.
Clicking a button sends its message as your next reply.
"""
import json, os, subprocess, sys

NAME = "olympus"
TOOL = {
    "name": "wrap_up",
    "description": (
        "End your turn with this when you changed files, ran commands or finished multi-step work. "
        "It shows the user a card under your reply: a recap and, when the next move is theirs, one "
        "question with one or two answer buttons. Call it once, after the work and before your closing "
        "message. Skip it for short answers and plain conversation."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "recap": {"type": "string", "description": "Two or three short sentences: what changed, "
                      "where it stands, what isn't done or checked. Said to the user."},
            "ask": {"type": "string", "description": "Only when the user must decide or act: one short "
                    "question, without listing the options. Leave out otherwise."},
            "actions": {"type": "array", "maxItems": 2, "description": "Buttons answering ask, your pick first.",
                        "items": {"type": "object", "required": ["label"], "properties": {
                            "label": {"type": "string", "description": "1-3 words, e.g. 'Yes, ship it'."},
                            "message": {"type": "string", "description": "The reply the button sends, in the "
                                        "user's voice. Defaults to the label."}}}},
        },
        "required": ["recap"],
    },
}


def register(folder):
    """Add this server to Claude Code for one folder (local scope: stored in ~/.claude.json, no prompt)."""
    folder = os.path.abspath(os.path.expanduser(folder))
    subprocess.run(["claude", "mcp", "remove", "-s", "local", NAME], cwd=folder, capture_output=True)
    r = subprocess.run(["claude", "mcp", "add", "-s", "local", NAME, "--", sys.executable.replace(
        "pythonw.exe", "python.exe"), os.path.abspath(__file__)], cwd=folder, capture_output=True, text=True)
    print(f"next-step card on for {folder}" if r.returncode == 0 else f"couldn't add it to {folder}: {r.stderr.strip()}")


def reply(id, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id, "result": result}) + "\n")
    sys.stdout.flush()


def serve():
    for line in sys.stdin:
        msg = json.loads(line)
        method, id = msg.get("method"), msg.get("id")
        if id is None:  # notifications need no answer
            continue
        if method == "initialize":
            reply(id, {"protocolVersion": msg["params"].get("protocolVersion", "2025-06-18"),
                       "capabilities": {"tools": {}}, "serverInfo": {"name": NAME, "version": "1"}})
        elif method == "tools/list":
            reply(id, {"tools": [TOOL]})
        elif method == "tools/call":
            reply(id, {"content": [{"type": "text", "text": "Shown to the user as a card under your reply. "
                                    "Now write your closing message; don't repeat the question."}]})
        else:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id,
                                         "error": {"code": -32601, "message": "unknown method"}}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    if sys.argv[1:2] == ["--register"] and len(sys.argv) == 3:
        register(sys.argv[2])
    else:
        serve()
