"""Make a new profile in one step: its folder and CLAUDE.md, the T3 project, its god and its tools.

    python new_profile.py <name> [god] [--agent]

  god      a theme name such as athena or hephaestus (Ares is mars); pick later with Ctrl+Alt+A if left out
  --agent  also write ~/.claude/agents/<name>.md so other chats can hand work to this profile

The New profile button in T3's sidebar runs the same code through the helper (make_profile).
"""
import json, pathlib, re, subprocess, sys
import wrapup_mcp
from organize import PROFILES

HERE = pathlib.Path(__file__).resolve().parent
HOME = pathlib.Path.home()
GODS = HERE / "gods.json"
register = wrapup_mcp.register


def gods_available():
    return sorted(p.stem[len("pantheon-"):] for p in (HERE / "themes").glob("pantheon-*.json"))


def t3_add(title, folder):
    """Add the folder to T3 as a project; True when T3 has it (just added, or already there)."""
    r = subprocess.run(["cmd", "/c", str(HOME / ".t3" / "bin" / "t3.cmd"), "project", "add", "--title", title,
                        folder.as_posix()], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode == 0 and "Error" not in r.stdout + r.stderr or "ProjectAlreadyExists" in r.stdout + r.stderr


def make_profile(name, god=None, about="", agent=False):
    """Make the profile and return {title, folder, added, messages}. ValueError for a bad name or god."""
    name, god, about = (name or "").strip().lower(), (god or "").strip().lower() or None, (about or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError("A profile name is letters, numbers and dashes, like gamedev or my-site.")
    if god and god not in gods_available():
        raise ValueError(f"No god theme called {god}. Pick one of: {', '.join(gods_available())}")
    title = name.capitalize()  # how T3 names it in the sidebar, and the key in gods.json
    folder = pathlib.Path(PROFILES) / name
    messages = []

    claude_md = folder / "CLAUDE.md"
    if claude_md.exists() and not about:
        messages.append(f"{folder} already has a CLAUDE.md; kept it.")
    else:
        folder.mkdir(parents=True, exist_ok=True)
        claude_md.write_text(
            f"# {title} profile\n\nYou are the {title.lower()} agent."
            + (f" You work on: {about}" + ("" if about.endswith(".") else ".") if about else "")
            + "\n\n## How you work\n\n- Ask before deleting files or pushing to GitHub.\n"
              "- Keep answers short; show code, not descriptions of code.\n", encoding="utf-8")
        messages.append(f"Made {folder} with its CLAUDE.md.")

    added = t3_add(title, folder)
    messages.append(f"Added {title} to T3." if added else "T3 didn't add the project; add the folder in T3 by hand.")
    register(folder)

    if god:
        gods = json.loads(GODS.read_text(encoding="utf-8")) if GODS.exists() else {}
        gods[title] = god
        GODS.write_text(json.dumps(gods, indent=2) + "\n", encoding="utf-8")
        messages.append(f"{title} is under {god[0].upper() + god[1:]}.")

    if agent:
        path = HOME / ".claude" / "agents" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nname: {name}\ndescription: The {title} profile. Hand it work that belongs to "
                        f"{title}.\n---\n\nRead {folder.as_posix()}/CLAUDE.md and follow it.\n", encoding="utf-8")
        messages.append("Other chats can hand work to it.")
    return {"title": title, "folder": str(folder), "added": added, "messages": messages}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    try:
        result = make_profile(args[0], args[1] if len(args) > 1 else None, agent="--agent" in sys.argv)
    except ValueError as e:
        sys.exit(str(e))
    print("\n".join(result["messages"]))
