"""Make a new profile in one step: its folder and CLAUDE.md, the T3 project, and its god.

    python new_profile.py <name> [god] [--agent]

  god      a theme name such as athena or hephaestus (Ares is mars); pick later with Ctrl+Alt+A if left out
  --agent  also write ~/.claude/agents/<name>.md so other chats can hand work to this profile

The profile shows up in T3's sidebar with its god the next time T3 opens from the shortcut.
"""
import json, os, pathlib, shutil, subprocess, sys
from organize import PROFILES

HERE = pathlib.Path(__file__).resolve().parent
HOME = pathlib.Path.home()
GODS = HERE / "gods.json"
args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args or not args[0].replace("-", "").isalnum():
    sys.exit(__doc__)
name, god = args[0].lower(), (args[1].lower() if len(args) > 1 else None)
title = name.capitalize()  # how T3 names it in the sidebar, and the key in gods.json
if god and not (HERE / "themes" / f"pantheon-{god}.json").exists():
    sys.exit(f"No god theme called {god}. Pick one of: "
             + ", ".join(p.stem[9:] for p in sorted((HERE / "themes").glob("pantheon-*.json"))))

folder = pathlib.Path(PROFILES) / name
if (folder / "CLAUDE.md").exists():
    print(f"{folder} already has a CLAUDE.md; keeping it")
else:
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / "profile-template" / "CLAUDE.md", folder / "CLAUDE.md")
    print(f"created {folder}; rewrite its CLAUDE.md for the role")

t3 = HOME / ".t3" / "bin" / "t3.cmd"
r = subprocess.run(["cmd", "/c", str(t3), "project", "add", "--title", title, folder.as_posix()],
                   capture_output=True, text=True)
print(f"added {title} to T3" if r.returncode == 0 else f"T3 didn't add the project: {(r.stderr or r.stdout).strip()}")

if god:
    gods = json.loads(GODS.read_text(encoding="utf-8")) if GODS.exists() else {}
    gods[title] = god
    GODS.write_text(json.dumps(gods, indent=2) + "\n", encoding="utf-8")
    print(f"{title} is now under {god}")

if "--agent" in sys.argv:
    agent = HOME / ".claude" / "agents" / f"{name}.md"
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_text(f"---\nname: {name}\ndescription: The {title} profile. Hand it work that belongs to "
                     f"{title}.\n---\n\nRead {folder.as_posix()}/CLAUDE.md and follow it.\n", encoding="utf-8")
    print(f"wrote {agent}")
