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
import cards_build, new_profile, temporary, voice
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


transcripts = {}  # session id -> its transcript path (a glob over every project folder otherwise)


def transcript(sid):
    """The Claude Code transcript file for a session, or None."""
    if sid not in transcripts or not os.path.exists(transcripts[sid]):
        files = glob.glob(os.path.join(HOME, ".claude", "projects", "*", sid + ".jsonl"))
        if not files:
            return None
        transcripts[sid] = files[0]
    return transcripts[sid]


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
    path = transcript(sid)
    if not path:
        raise ValueError(f"Can't find the Claude Code transcript for session {sid}.")
    with open(path, encoding="utf-8") as f:
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


CLAUDE_JSON = os.path.join(HOME, ".claude.json")
UNTRUSTED = re.compile(r"Workspace not trusted\. Run `claude` in (.+?) once")


def trust(folder):
    """Mark a folder trusted for Claude Code, as accepting its trust prompt does. Remote Control
    checks the folder itself (or its git repo), not the folders above it."""
    with open(CLAUDE_JSON, encoding="utf-8") as f:
        data = json.load(f)
    key = folder.strip().replace("\\", "/")
    data.setdefault("projects", {}).setdefault(key, {})["hasTrustDialogAccepted"] = True
    tmp = CLAUDE_JSON + ".olympus-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CLAUDE_JSON)


def continue_elsewhere(thread, allow=False):
    """allow: you agreed in T3 to trust the folder an earlier try asked about ("trust" in the reply)."""
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
        start = lambda: claude("--bg", "--resume", sid, "--remote-control", title[:60], cwd=cwd)
        out = start()
        untrusted = UNTRUSTED.search(out.stderr + out.stdout)
        if untrusted and not allow:  # T3 asks you, then calls again with allow
            return {"trust": untrusted.group(1).strip(), "title": title}
        if untrusted:
            trust(untrusted.group(1))
            out = start()
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


turn_cache = {}  # transcript path -> (bytes read, items, index by tool_use id)
PREFIX = "turn-item:provider:claudeAgent:native-item:"  # T3's id for a Claude tool call, so items match


def turn_calls(path):
    """The olympus tool calls and your messages in a Claude transcript, in the shape of T3's turn
    items, for turnbox.js when T3's socket has no history for a chat. Reads only what was added
    since the last call (from the start again if the file shrank); a half-written line waits."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return []
    offset, items, calls = turn_cache.get(path, (0, [], {}))
    if size < offset:
        offset, items, calls = 0, [], {}
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
    end = data.rfind(b"\n") + 1
    for line in data[:end].splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") == "user":
            if isinstance(content, str) or any(b.get("type") == "text" for b in content or []):
                items.append({"id": "transcript-user:" + str(entry.get("uuid", len(items))), "type": "user_message"})
            for b in content if isinstance(content, list) else []:
                if b.get("type") == "tool_result" and b.get("is_error") and b.get("tool_use_id") in calls:
                    calls[b["tool_use_id"]]["status"] = "failed"
        elif entry.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                name = b.get("name", "")
                if b.get("type") == "tool_use" and name.endswith(("__update_plan", "__wrap_up")):
                    item = {"id": PREFIX + b["id"], "type": "dynamic_tool", "toolName": name,
                            "input": b.get("input") or {}, "status": "completed"}
                    calls[b["id"]] = item
                    items.append(item)
    turn_cache[path] = (offset + end, items, calls)
    return items


def turn_state(thread):
    """GET /turn: a chat's turn items from its transcript; empty when there is no session or file."""
    # only the session's transcript is needed, not the folder session_for also checks
    sid = temporary.session_of(thread)
    path = sid and transcript(sid)
    return {"items": turn_calls(path) if path else [], "run": None}


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


dictation = None  # the one recording in progress (voice.Dictation)


def voice_post(path, data):
    """Dictation: /voice/start, then /voice/audio with raw 16 kHz 16-bit mono audio, then /voice/stop."""
    global dictation
    if path == "/voice/start":
        if dictation:
            dictation.stop(0)
        dictation = voice.Dictation()
        return {"ok": True}
    d = dictation
    if not d:
        raise ValueError("No dictation in progress.")
    if path == "/voice/audio":
        d.audio(data)
        if d.error:
            raise ValueError(d.error)
        return {"text": d.text()}
    if path == "/voice/stop":
        dictation = None
        text = d.stop()
        if d.error and not text:
            raise ValueError(d.error)
        return {"text": text}
    raise ValueError("not found")


def make_profile(body):
    """POST /profile from the New profile button: new_profile.make_profile, plus the updated god map."""
    result = new_profile.make_profile(str(body.get("name", "")), body.get("god") or None,
                                      str(body.get("about", "")), bool(body.get("agent")))
    return {**result, "gods": gods()}


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


PETS_OPEN = os.path.join(HERE, "local", "pets-open.json")
PETS_SEEN = os.path.join(HERE, "local", "pets-seen.json")


PETS_OFF = os.path.join(HERE, "local", "pets-off")  # there while you've turned the pets off
PETS_PORT = 47834  # pets.pyw holds it while it runs
pets_checked = 0.0


def ensure_pets():
    """Start the desktop pets if they aren't running and you haven't turned them off: T3 is open
    (pets.js is asking), however it was opened. Checked at most every 10 s."""
    global pets_checked
    if os.path.exists(PETS_OFF) or time.time() - pets_checked < 10:
        return
    pets_checked = time.time()
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", PETS_PORT))  # free, so no pets: release it and start them
        except OSError:
            return  # held: the pets are running
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    subprocess.Popen([pythonw if os.path.exists(pythonw) else sys.executable, os.path.join(HERE, "pets.pyw")],
                     cwd=HERE, close_fds=True, creationflags=NO_WINDOW)


def pets_toggle(_body=None):
    """POST /pets/toggle (Ctrl+Alt+P in T3): turn the desktop pets off or on, and keep it that way.
    Off: pets.pyw sees PETS_OFF and leaves. On: they start straight away."""
    global pets_checked
    if os.path.exists(PETS_OFF):
        os.remove(PETS_OFF)
        pets_checked = 0.0
        ensure_pets()
        return {"on": True}
    os.makedirs(os.path.dirname(PETS_OFF), exist_ok=True)
    open(PETS_OFF, "w").close()
    return {"on": False}


def pets_poll(query):
    """GET /pets/poll from pets.js: note the chat T3 shows (so a desktop pet's done badge clears),
    and hand over a chat a pet was clicked for (pets.pyw writes it), once."""
    ensure_pets()
    q = urllib.parse.parse_qs(query)
    os.makedirs(os.path.dirname(PETS_SEEN), exist_ok=True)
    with open(PETS_SEEN + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"thread": q.get("thread", [""])[0], "focus": q.get("focus", ["0"])[0] == "1",
                   "time": time.time()}, f)
    os.replace(PETS_SEEN + ".tmp", PETS_SEEN)
    # held open up to 2 s, so a click on a pet reaches T3 within ~50 ms
    end = time.time() + 2
    while not os.path.exists(PETS_OPEN):
        if time.time() > end:
            return {}
        time.sleep(0.05)
    try:
        with open(PETS_OPEN, encoding="utf-8") as f:
            ask = json.load(f)
        os.remove(PETS_OPEN)
    except (OSError, ValueError):
        return {}
    if time.time() - ask.get("time", 0) > 60:
        return {}
    return {"open": ask.get("thread"), "profile": ask.get("profile")}


building = threading.Lock()
refreshing = set()
refresh_guard = threading.Lock()


def hover_card(name):
    """Rebuild one profile's local hover card without making model requests."""
    with building:  # one rebuild at a time, so cards.json writes never overlap
        return cards_build.build(name).get(name, {})


def refresh_card(body):
    """Refresh one known profile, rejecting duplicate in-flight requests."""
    name = body.get("name") if isinstance(body, dict) else None
    if not isinstance(name, str) or name not in cards_build.profiles():
        return 400, {"ok": False, "error": "Choose one known profile."}
    with refresh_guard:
        if name in refreshing:
            return 409, {"ok": False, "error": "Refresh already in progress."}
        refreshing.add(name)
    try:
        with building:
            card = cards_build.build(name, refresh=True, strict_refresh=True)[name]
        return 200, {"ok": True, "card": card}
    except Exception:
        return 502, {"ok": False, "error": "Couldn't refresh AI summary. Try again later."}
    finally:
        with refresh_guard:
            refreshing.discard(name)


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
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {"error": "forbidden"})
        if self.path == "/config":
            return self.reply(200, {"show_in": CONFIG.get("buttons_show_in", "all")})
        if self.path == "/gods":
            return self.reply(200, gods())
        if self.path == "/gods/themes":  # the gods a profile can have, for the New profile dialog
            return self.reply(200, new_profile.gods_available())
        if self.path == "/temporary":  # the project, and leftover chats to delete
            return self.reply(200, {"title": temporary.TITLE, "ready": temporary.ensure() is not None,
                                    "threads": temporary.threads()})
        if self.path.startswith("/session?thread="):
            return self.reply(200, session_info(urllib.parse.unquote(self.path.split("=", 1)[1])))
        if self.path.startswith("/turn?thread="):
            return self.reply(200, turn_state(urllib.parse.unquote(self.path.split("=", 1)[1])))
        if self.path.startswith("/pets/poll?"):
            return self.reply(200, pets_poll(self.path.split("?", 1)[1]))
        if self.path.startswith("/card?name="):
            return self.reply(200, hover_card(urllib.parse.unquote(self.path.split("=", 1)[1])))
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if not self.allowed():
            return self.reply(403, {"error": "forbidden"})
        if self.path == "/card/refresh":
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            except (ValueError, UnicodeError):
                return self.reply(400, {"ok": False, "error": "Invalid refresh request."})
            try:
                code, result = refresh_card(body)
            except Exception:
                code, result = 502, {"ok": False, "error": "Couldn't refresh AI summary. Try again later."}
            return self.reply(code, result)
        if self.path.startswith("/voice/"):
            try:
                data = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                return self.reply(200, voice_post(self.path, data))
            except Exception as e:  # shown to you in T3
                return self.reply(400, {"error": str(e)})
        action = {"/continue": lambda b: continue_elsewhere(str(b["thread"]), b.get("allow") is True),
                  "/cloud": lambda b: send_to_cloud(str(b["thread"])), "/gods": set_god,
                  "/temporary/leaving": temporary_leaving, "/temporary/purge": temporary_purge,
                  "/profile": make_profile, "/pets/toggle": pets_toggle}.get(self.path)
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


STAMP = os.path.join(HERE, "local", "helper.json")  # the running helper's code version
CODE = ("helper.py", "voice.py", "temporary.py", "organize.py", "cards_build.py", "background_patch.py", "new_profile.py", "wrapup_mcp.py")


if __name__ == "__main__":
    version = max(os.path.getmtime(os.path.join(HERE, f)) for f in CODE)
    if running():
        # one copy at a time, but a copy started before T3 Olympus was updated is replaced,
        # or new features would wait for the next reboot
        try:
            with open(STAMP, encoding="utf-8") as f:
                old = json.load(f)
        except (OSError, ValueError):
            old = {}
        if old.get("version") == version:
            sys.exit(0)
        # the process listening on the helper's port (also covers a copy older than the stamp file)
        listen = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                                creationflags=NO_WINDOW).stdout
        pid = next((line.split()[-1] for line in listen.splitlines()
                    if f"127.0.0.1:{PORT}" in line and "LISTENING" in line), None)
        if not pid or not pid.isdigit():
            sys.exit(0)
        subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, creationflags=NO_WINDOW)
        for _ in range(30):
            if not running():
                break
            time.sleep(0.1)
        else:
            sys.exit(0)
    os.makedirs(os.path.dirname(STAMP), exist_ok=True)
    with open(STAMP, "w", encoding="utf-8") as f:
        json.dump({"version": version}, f)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
