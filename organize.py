"""Sort T3's chats into your profile projects (one T3 project per folder in profiles_dir).

    python organize.py --dry-run   show what would move
    python organize.py             back up T3's data, then move (close T3 first)

T3 imports Claude Code history as one project per folder a session ran in, which
scatters chats over dozens of projects. T3 has no "move thread" command, so this
appends the same "thread.metadata-updated" record T3 writes itself, with the new
projectId, to its event log, and updates T3's thread list to match.

The rules live in config.json (copy config.example.json):
  folders   folder name (or prefix) under projects_dir -> profile; first match wins
  topics    exact chat title -> profile, for chats started in projects_dir itself
  archive   path fragments of test runs: archived into the default profile
  remove_empty_projects   true to remove projects outside profiles_dir left with no chats
Anything else goes to default_profile. A profile is any folder in profiles_dir that is
also a T3 project, so a new profile needs no code change.
"""
import datetime, json, os, shutil, sqlite3, subprocess, sys, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
DATA = os.path.join(HOME, ".t3", "userdata")
DB = os.path.join(DATA, "statev2.sqlite")
with open(os.path.join(HERE, "config.json" if os.path.exists(os.path.join(HERE, "config.json"))
                       else "config.example.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)
P = os.path.normpath(os.path.expanduser(CONFIG["projects_dir"]))
PROFILES = os.path.normpath(os.path.expanduser(CONFIG["profiles_dir"]))
FOLDERS = list(CONFIG["folders"].items())
TOPICS = CONFIG["topics"]
DEFAULT = CONFIG["default_profile"]


def target(root, title):
    """(profile, archive) for a thread, or None to leave it where it is."""
    if root.startswith(PROFILES + os.sep):
        return None
    if any(m in root for m in CONFIG["archive"]):
        return DEFAULT, True
    if root == P:
        return TOPICS.get(title, DEFAULT), False
    if root.startswith(P + os.sep):
        rel = root[len(P) + 1:]
        return next((prof for prefix, prof in FOLDERS if rel.startswith(prefix)), DEFAULT), False
    return DEFAULT, False  # anything outside projects_dir


def main(dry):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    projects = {r["workspace_root"]: r["project_id"] for r in con.execute(
        "select project_id, workspace_root from projection_projects where deleted_at is null")}
    profile_ids = {os.path.basename(root): pid for root, pid in projects.items()
                   if os.path.dirname(root) == PROFILES}
    roots = {v: k for k, v in projects.items()}

    moves = []
    for t in con.execute("select thread_id, project_id, title, payload_json from orchestration_v2_projection_threads "
                         "where deleted_at is null"):
        root = roots.get(t["project_id"], "")
        hit = target(root, t["title"])
        if hit and hit[0] in profile_ids:  # a rule naming a profile T3 doesn't have yet is skipped
            moves.append((t, root, *hit))

    for t, root, prof, archive in moves:
        print(f"{prof:10} {'(archive) ' if archive else ''}{t['title'][:60]!r:64} <- {root[-50:]}")
    print(f"{len(moves)} threads to move")
    if dry:
        return
    if moves:
        move(con, moves, profile_ids)
    con.close()
    if CONFIG.get("remove_empty_projects"):
        remove_empty_projects()


def remove_empty_projects():
    """Remove projects outside _profiles that no longer hold any thread, through T3's own CLI."""
    con = sqlite3.connect(DB)
    empty = [r[0] for r in con.execute(
        "select p.workspace_root from projection_projects p where p.deleted_at is null and not exists "
        "(select 1 from orchestration_v2_projection_threads t where t.project_id = p.project_id and t.deleted_at is null)")
        if not r[0].startswith(PROFILES + os.sep)]
    con.close()
    t3 = os.path.join(HOME, ".t3", "bin", "t3.cmd")
    for root in empty:
        subprocess.run(["cmd", "/c", t3, "project", "remove", root], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if empty:
        print(f"removed {len(empty)} empty projects")


def move(con, moves, profile_ids):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(HOME, ".t3", f"userdata-backup-{stamp}")
    con.execute("pragma wal_checkpoint(full)")
    shutil.copytree(DATA, backup, ignore=shutil.ignore_patterns("logs", "caches"))
    print("backup:", backup)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    with con:
        for t, root, prof, archive in moves:
            snap = json.loads(t["payload_json"])
            snap["projectId"] = profile_ids[prof]
            if archive and not snap.get("archivedAt"):
                snap["archivedAt"] = now
            version = con.execute("select coalesce(max(stream_version), 0) + 1 from orchestration_events "
                                  "where aggregate_kind = 'thread' and stream_id = ?", (t["thread_id"],)).fetchone()[0]
            cmd = f"organize-profiles:{uuid.uuid4()}"
            con.execute(
                "insert into orchestration_events (event_id, aggregate_kind, stream_id, stream_version, event_type, "
                "occurred_at, command_id, causation_event_id, correlation_id, actor_kind, payload_json, metadata_json, "
                "application_event_version) values (?, 'thread', ?, ?, 'thread.metadata-updated', ?, ?, null, ?, "
                "'user', ?, ?, 2)",
                (f"event:thread:{t['thread_id']}:command:{cmd}", t["thread_id"], version, now, cmd, cmd,
                 json.dumps(snap, separators=(",", ":")),
                 json.dumps({"providerInstanceId": snap.get("providerInstanceId", "claudeAgent")})))
        sync_projection(con, {t["thread_id"] for t, *_ in moves})
    print(f"moved {len(moves)} threads")


def sync_projection(con, only=None):
    """Apply the organize-profiles records to T3's thread list. T3 only updates that list as records
    are written while it runs, not from the log at startup, so the move has to land in both."""
    latest = con.execute(
        "select stream_id, payload_json from orchestration_events e where command_id like 'organize-profiles:%' "
        "and sequence = (select max(sequence) from orchestration_events x "
        "where x.command_id like 'organize-profiles:%' and x.stream_id = e.stream_id)").fetchall()
    for tid, payload in latest:
        if only is not None and tid not in only:
            continue
        moved = json.loads(payload)
        row = con.execute("select payload_json from orchestration_v2_projection_threads where thread_id = ?",
                          (tid,)).fetchone()
        if not row:
            continue
        snap = json.loads(row[0])
        snap["projectId"] = moved["projectId"]
        snap["archivedAt"] = snap.get("archivedAt") or moved.get("archivedAt")
        con.execute("update orchestration_v2_projection_threads set project_id = ?, archived_at = ?, payload_json = ? "
                    "where thread_id = ?",
                    (snap["projectId"], snap["archivedAt"], json.dumps(snap, separators=(",", ":")), tid))
    con.execute("update orchestration_v2_projection_metadata set last_sequence = "
                "(select max(sequence) from orchestration_events) where projection_name = 'thread-projections'")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
