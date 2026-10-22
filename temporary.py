"""Temporary chats: chats in a hidden "Temporary" T3 project that are deleted when you leave them.

T3 has no temporary mode, so a temporary chat is a normal chat in its own folder:
  - the folder turns Claude's automatic memory off, so nothing is read from or written to memory;
  - olympus.js hides the project, labels the chat, and uses T3's own Delete when you leave it;
  - purge() then removes what Claude Code and T3 keep outside T3's database for that chat
    (the transcript, file snapshots, session files, T3's per-chat log and uploaded files);
  - sweep() and scrub() run when the shortcut opens T3 (T3 closed): they clear files a crash left
    behind, and every row T3 still keeps in its database for deleted temporary chats.

What it can't prevent: while the chat is open it is on disk like any chat, T3's general
trace logs may hold fragments, and Anthropic receives the messages to answer them.
"""
import json, os, re, shutil, sqlite3, subprocess

HOME = os.path.expanduser("~")
DIR = os.path.join(HOME, ".t3", "olympus-temporary")
TITLE = "Temporary"
DATA = os.path.join(HOME, ".t3", "userdata")
DB = os.path.join(DATA, "statev2.sqlite")
CLAUDE = os.path.join(HOME, ".claude")
SETTINGS = {"autoMemoryEnabled": False}


def slug(path):
    """The folder name Claude Code uses under ~/.claude/projects for a working directory."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def is_temporary(root):
    return bool(root) and os.path.normcase(os.path.normpath(root)) == os.path.normcase(DIR)


def ensure():
    """Create the folder with memory off and add it to T3 as the "Temporary" project, once."""
    os.makedirs(os.path.join(DIR, ".claude"), exist_ok=True)
    with open(os.path.join(DIR, ".claude", "settings.json"), "w", encoding="utf-8") as f:
        json.dump(SETTINGS, f, indent=2)
    if project_id() is None:
        subprocess.run(["cmd", "/c", os.path.join(HOME, ".t3", "bin", "t3.cmd"), "project", "add", "--title", TITLE,
                        DIR.replace("\\", "/")], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return project_id()


def _ro():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def project_id():
    if not os.path.exists(DB):
        return None
    con = _ro()
    try:
        for pid, root in con.execute("select project_id, workspace_root from projection_projects where deleted_at is null"):
            if is_temporary(root):
                return pid
    finally:
        con.close()
    return None


def threads():
    """Ids of the chats T3 still has in the Temporary project."""
    pid = project_id()
    if not pid:
        return []
    con = _ro()
    try:
        return [r[0] for r in con.execute("select thread_id from orchestration_v2_projection_threads "
                                          "where project_id = ? and deleted_at is null", (pid,))]
    finally:
        con.close()


def session_of(thread):
    """The Claude Code session id behind a T3 chat, or None."""
    con = _ro()
    try:
        row = con.execute("select payload_json from orchestration_v2_projection_provider_threads where thread_id = ?",
                          (thread,)).fetchone()
    finally:
        con.close()
    ref = (json.loads(row[0]).get("nativeThreadRef") or {}) if row else {}
    return ref.get("nativeId")


def attachments_of(thread):
    """Upload folders under T3's attachments that this chat's records mention."""
    folder = os.path.join(DATA, "attachments")
    if not os.path.isdir(folder):
        return []
    con = _ro()
    try:
        text = "".join(r[0] or "" for r in con.execute(
            "select payload_json from orchestration_events where stream_id = ?", (thread,)))
    finally:
        con.close()
    return [os.path.join(folder, n) for n in os.listdir(folder) if n in text]


def _remove(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.remove(path)


def files_for(thread, session):
    """Everything outside T3's database that belongs to this chat."""
    paths = [os.path.join(DATA, "logs", "provider", f"events.{thread}.log")]
    if session:
        projects = os.path.join(CLAUDE, "projects", slug(DIR))
        paths += [os.path.join(projects, session + ".jsonl"), os.path.join(projects, session),
                  os.path.join(CLAUDE, "file-history", session), os.path.join(CLAUDE, "session-env", session)]
    return paths


def purge(thread, session=None, uploads=()):
    """Remove a temporary chat's files. Call it with what was looked up before T3 deleted the chat."""
    if os.path.basename(thread) != thread or (session and os.path.basename(session) != session):
        raise ValueError("bad id")
    for p in [*files_for(thread, session), *uploads]:
        _remove(p)


def scrub():
    """Remove every row T3 keeps for temporary chats it has deleted. T3's Delete only marks a chat
    deleted; its messages stay in the event log and projections. Run with T3 closed (the launcher),
    then VACUUM so the text doesn't linger in the file's free space. Returns how many chats."""
    pid = project_id()
    if not pid:
        return 0
    con = sqlite3.connect(DB)
    try:
        ids = [r[0] for r in con.execute("select thread_id from orchestration_v2_projection_threads "
                                          "where project_id = ? and deleted_at is not null", (pid,))]
        if not ids:
            return 0
        marks = ",".join("?" * len(ids))
        with con:
            for (table,) in con.execute("select name from sqlite_master where type = 'table'").fetchall():
                cols = {c[1] for c in con.execute(f'pragma table_info("{table}")')}
                for col in cols & {"thread_id", "stream_id", "aggregate_id", "source_thread_id", "target_thread_id"}:
                    con.execute(f'delete from "{table}" where "{col}" in ({marks})', ids)
        con.execute("pragma wal_checkpoint(truncate)")
        con.execute("vacuum")
        return len(ids)
    finally:
        con.close()


def sweep(keep=()):
    """Clear every temporary chat's files except those in keep (chats still open).
    Claude Code keeps all of them in one folder, since they all ran in DIR."""
    projects = os.path.join(CLAUDE, "projects", slug(DIR))
    keep_sessions = {session_of(t) for t in keep} - {None}
    if os.path.isdir(projects):
        for name in os.listdir(projects):
            if name.split(".")[0] not in keep_sessions:
                sid = name.split(".")[0]
                _remove(os.path.join(projects, name))
                for d in ("file-history", "session-env"):
                    _remove(os.path.join(CLAUDE, d, sid))
    for t in threads():
        if t not in keep:
            _remove(os.path.join(DATA, "logs", "provider", f"events.{t}.log"))
