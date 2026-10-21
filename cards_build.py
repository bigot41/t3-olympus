"""Write cards.json, the hover card for each profile in T3's sidebar.

    python cards_build.py     rebuild every card now

helper.py calls build(name) when you hover a profile in T3, for that profile only.

Haiku reads each profile's folders and chat titles and says what that profile actually
works on, so nothing has to be kept up to date by hand. A profile is only sent to Haiku
again when its chats or folders changed (the "key" stored with each card).
"""
import hashlib, json, os, re, sqlite3, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from organize import DB, FOLDERS, PROFILES

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards.json")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROMPT = """These are the folders and chat titles of the "{name}" profile, one of the AI agent profiles \
someone uses in their coding app.

Folders: {folders}
Chat titles, newest first:
{chats}

Reply with JSON only, no other text:
{{"does": "one plain sentence, under 20 words, on what this profile actually works on",
 "topics": ["3 to 5 short phrases (under 5 words each) naming its main recurring work"]}}"""


def haiku(prompt):
    out = subprocess.run(
        ["claude", "-p", "--model", "haiku", "--effort", "low", "--tools", "", "--setting-sources", "",
         "--no-session-persistence"], input=prompt, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120, env={**os.environ, "MAX_THINKING_TOKENS": "0"},
        cwd=os.path.expanduser("~"), creationflags=NO_WINDOW).stdout
    return json.loads(re.search(r"\{.*\}", out, re.S).group(0))


def profiles():
    """{Name: (folders, chat titles newest first)} from organize's rules and T3's database."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out = {}
    for role in sorted(os.listdir(PROFILES)):
        folders = [f for f, p in FOLDERS if p == role]
        chats = [t for (t,) in con.execute(
            "select t.title from orchestration_v2_projection_threads t join projection_projects p "
            "on p.project_id = t.project_id where p.workspace_root = ? and t.deleted_at is null "
            "and t.archived_at is null order by t.updated_at desc", (os.path.join(PROFILES, role),))
            if not t.startswith("<")]
        out[role.capitalize()] = (folders, chats)
    con.close()
    return out


def build(only=None):
    """Rebuild the cards (or just the profile named `only`) and return them all."""
    try:
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = {}

    def card(item):
        name, (folders, chats) = item
        if only and name != only:
            return name, old.get(name, {})
        key = hashlib.sha1(json.dumps([folders, chats]).encode()).hexdigest()
        prev = old.get(name, {})
        summary = {k: prev[k] for k in ("does", "topics") if k in prev}
        if prev.get("key") != key or not summary:
            try:
                summary = haiku(PROMPT.format(name=name, folders=", ".join(folders) or "none",
                                              chats="\n".join(chats[:80]) or "none"))
            except Exception:  # keep the last summary rather than show nothing
                key = prev.get("key")
        return name, {"key": key, **summary, "projects": folders, "chats": len(chats), "recent": chats[:5]}

    with ThreadPoolExecutor(6) as pool:
        cards = dict(pool.map(card, profiles().items()))
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=1)
    os.replace(tmp, OUT)
    return cards


if __name__ == "__main__":
    build()
