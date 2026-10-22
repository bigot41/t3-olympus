"""Local helper behind the "Continue elsewhere" and "Send to cloud" buttons in T3.

    pythonw helper.py    the T3 Olympus shortcut starts it; one copy runs at a time

It listens on 127.0.0.1:47833 and only answers T3's own page (origin t3code://app).
The page sends the open thread's id; the helper looks up that thread's Claude Code
session in T3's database and runs the claude CLI on it:

  continue  claude --bg --resume <session> --remote-control <title>
            the same conversation keeps running in the background with Remote Control,
            so you can pick it up in Claude desktop, claude.ai or the phone app
  cloud     opens a terminal running send_to_cloud.py (handoff note, then claude --cloud)

config.json's buttons_show_in picks which T3 projects show the buttons ("all" or a list of names).
"""
import glob, json, os, re, socket, sqlite3, subprocess, sys, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import cards_build, temporary
from organize import CONFIG

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
DB = os.path.join(HOME, ".t3", "userdata", "statev2.sqlite")
GODS = os.path.join(HERE, "gods.json")
THEMES = os.path.join(HOME, ".t3", "userdata", "themes")
PORT = 47833
ORIGIN = "t3code://app"
PYTHON = sys.executable.replace("pythonw.exe", "python.exe")  # a console python for the terminal
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def session_for(thread):
    """(session id, folder it ran in, title) for a T3 thread, or raise ValueError."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        row = con.execute("select payload_json from orchestration_v2_projection_provider_threads where thread_id = ?",
                          (thread,)).fetchone()
        title = con.execute("select title from orchestration_v2_projection_threads where thread_id = ?",
                            (thread,)).fetchone()
    finally:
        con.close()
    if not row:
        raise ValueError("This chat has no Claude session yet. Send a message first.")
    ref = json.loads(row[0]).get("nativeThreadRef") or {}
    if ref.get("driver") != "claudeAgent" or not ref.get("nativeId"):
        raise ValueError("Only Claude chats can be continued elsewhere.")
    sid = ref["nativeId"]
    files = glob.glob(os.path.join(HOME, ".claude", "projects", "*", sid + ".jsonl"))
    if not files:
        raise ValueError(f"Can't find the Claude Code transcript for session {sid}.")
    with open(files[0], encoding="utf-8") as f:
        cwd = next((c for c in (json.loads(line).get("cwd") for line in f) if c), None)
    if not cwd or not os.path.isdir(cwd):
        raise ValueError(f"The folder this chat ran in is gone: {cwd}")
    return sid, cwd, (title[0] if title else "T3 chat")


def claude(*args, cwd=None):
    return subprocess.run(["claude", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60, creationflags=NO_WINDOW)


def remote_url(bg_id, wait=30):
    """The claude.ai link Remote Control prints in the background session's output."""
    end = time.time() + wait
    while time.time() < end:
        m = re.search(r"https://claude\.ai/code/session_\w+", claude("logs", bg_id).stdout)
        if m:
            return m.group(0)
        time.sleep(1.5)
    return None


def continue_elsewhere(thread):
    sid, cwd, title = session_for(thread)
    # already handed over: reuse that background session instead of starting another
    try:
        running = json.loads(claude("agents", "--json").stdout or "[]")
    except ValueError:
        running = []
    bg = next((a for a in running if a.get("kind") == "background" and a.get("sessionId") == sid), None)
    note = ""
    if bg:
        bg_id = bg["id"]
    else:
        out = claude("--bg", "--resume", sid, "--remote-control", title[:60], cwd=cwd)
        m = re.search(r"backgrounded\s*\W\s*(\w+)", out.stdout)
        if not m:
            raise ValueError("claude --bg failed: " + (out.stderr or out.stdout).strip()[-400:])
        bg_id = m.group(1)
        if "copy" in out.stdout.lower():
            note = "The session was busy, so Claude started a copy of it."
    return {"id": bg_id, "url": remote_url(bg_id), "title": title, "note": note}


def send_to_cloud(thread):
    sid, cwd, title = session_for(thread)
    subprocess.Popen(["wt", "-w", "new", "--title", "Send to cloud", "-d", cwd,
                      PYTHON, os.path.join(HERE, "send_to_cloud.py"), sid, title])
    return {"title": title}


def wrap_up_card(thread):
    """The chat's latest wrap_up call, if nothing has been said since it; else {}."""
    try:
        sid = session_for(thread)[0]
    except ValueError:
        return {}
    card = {}
    with open(glob.glob(os.path.join(HOME, ".claude", "projects", "*", sid + ".jsonl"))[0], encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            content = (entry.get("message") or {}).get("content")
            if entry.get("type") == "user" and (isinstance(content, str) or any(
                    b.get("type") == "text" for b in content or [])):
                card = {}  # you replied, so the old card is answered
            elif entry.get("type") == "assistant" and isinstance(content, list):
                for b in content:
                    if b.get("type") == "tool_use" and b.get("name", "").endswith("__wrap_up"):
                        card = {"id": b["id"], **b.get("input", {})}
    return card


connectors_cache = {}  # folder -> (time, list), since claude mcp list takes a few seconds


def session_info(thread):
    """Context use (as T3 recorded it) and the MCP servers Claude sees in the chat's folder."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        row = con.execute("select payload_json from orchestration_v2_projection_provider_threads where thread_id = ?",
                          (thread,)).fetchone()
        # T3 doesn't always store the chat's figure; every turn has one, so fall back to the latest
        turn = con.execute("select payload_json from orchestration_v2_projection_provider_turns where thread_id = ? "
                           "order by ordinal desc limit 1", (thread,)).fetchone()
    finally:
        con.close()
    context = ((json.loads(row[0]).get("contextUsage") if row else None)
               or (json.loads(turn[0]).get("tokenUsage") if turn else None) or {})
    context = {k: context.get(k) for k in ("usedTokens", "maxTokens")}
    try:
        cwd = session_for(thread)[1]
    except ValueError:
        return {"context": context, "connectors": []}
    when, found = connectors_cache.get(cwd, (0, None))
    if found is None or time.time() - when > 120:
        out = claude("mcp", "list", cwd=cwd).stdout
        found = [{"name": m.group(1), "ok": "✔" in m.group(2), "status": m.group(2).lstrip("✔✗! ").strip()}
                 for m in re.finditer(r"^(.+?): .* - (.+)$", out, re.M)]
        connectors_cache[cwd] = (time.time(), found)
    return {"context": context, "connectors": found}


leaving = {}  # temporary chat id -> (session, uploads), looked up before T3 deletes the chat


def temporary_leaving(body):
    """Note what to clean up for a temporary chat that is about to be deleted."""
    thread = str(body["thread"])
    if thread not in temporary.threads():
        raise ValueError("Not a temporary chat.")
    leaving[thread] = (temporary.session_of(thread), temporary.attachments_of(thread))
    return {"ok": True}


def temporary_purge(body):
    """After T3 deleted a temporary chat, remove its files too."""
    thread = str(body["thread"])
    if thread in temporary.threads():
        raise ValueError("T3 hasn't deleted this chat yet.")
    if thread not in leaving:
        raise ValueError("Unknown temporary chat.")
    session, uploads = leaving.pop(thread)
    temporary.purge(thread, session, uploads)
    return {"ok": True}


def gods():
    if not os.path.exists(GODS):
        return {}
    with open(GODS, encoding="utf-8") as f:
        return json.load(f)


def set_god(body):
    """Make a god the profile's god, from picking it by hand in T3."""
    project, god = str(body["project"]), str(body["god"])
    if not re.fullmatch(r"[a-z]+", god) or not os.path.exists(os.path.join(THEMES, f"pantheon-{god}.json")):
        raise ValueError(f"No Pantheon theme called {god}.")
    current = gods()
    current[project] = god
    with open(GODS, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
        f.write("\n")
    return current


building = threading.Lock()


def hover_card(name):
    """The hover card for one profile, rebuilt now: called when you hover it in T3.
    Haiku only runs when that profile's chats or folders changed since its last card."""
    with building:  # one rebuild at a time, so cards.json writes never overlap
        return cards_build.build(name).get(name, {})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def allowed(self):
        return self.headers.get("Origin") == ORIGIN

    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        if self.allowed():
            self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204 if self.allowed() else 403)
        if self.allowed():
            self.send_header("Access-Control-Allow-Origin", ORIGIN)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {"error": "forbidden"})
        if self.path == "/config":
            return self.reply(200, {"show_in": CONFIG.get("buttons_show_in", "all")})
        if self.path == "/gods":
            return self.reply(200, gods())
        if self.path == "/temporary":  # the project, and leftover chats to delete
            return self.reply(200, {"title": temporary.TITLE, "ready": temporary.ensure() is not None,
                                    "threads": temporary.threads()})
        if self.path.startswith("/session?thread="):
            return self.reply(200, session_info(urllib.parse.unquote(self.path.split("=", 1)[1])))
        if self.path.startswith("/wrapup?thread="):
            return self.reply(200, wrap_up_card(urllib.parse.unquote(self.path.split("=", 1)[1])))
        if self.path.startswith("/card?name="):
            return self.reply(200, hover_card(urllib.parse.unquote(self.path.split("=", 1)[1])))
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if not self.allowed():
            return self.reply(403, {"error": "forbidden"})
        action = {"/continue": lambda b: continue_elsewhere(str(b["thread"])),
                  "/cloud": lambda b: send_to_cloud(str(b["thread"])), "/gods": set_god,
                  "/temporary/leaving": temporary_leaving, "/temporary/purge": temporary_purge}.get(self.path)
        if not action:
            return self.reply(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            self.reply(200, action(body))
        except Exception as e:  # shown to you in T3
            self.reply(400, {"error": str(e)})


def running():
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PORT)) == 0


if __name__ == "__main__":
    if running():
        sys.exit(0)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
