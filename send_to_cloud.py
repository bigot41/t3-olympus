"""Move a T3 chat to a Claude Code cloud session. The helper runs this in a terminal.

    python send_to_cloud.py <session id> <title>

A cloud session can't see this computer, so Claude first writes a handoff note from a
copy of the chat (the chat itself is left as it is). The note is saved in handoffs/
and becomes the first message of a new cloud session (claude --cloud).
"""
import datetime, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT = """Write a handoff note so a fresh Claude Code session in the cloud can continue this work.
That session has no access to this computer, its files or this conversation. Include:
the goal, what is done, the current state, decisions made and why, the exact file names,
commands and short code or text it needs, and the next steps. If the work needs files that
only exist on this computer, say which. Plain markdown, under 1000 words. Output only the note."""

sid, title = sys.argv[1], sys.argv[2]
print(f"Writing a handoff note for: {title}\n(about a minute)\n")
out = subprocess.run(["claude", "-p", "--resume", sid, "--fork-session", "--no-session-persistence", PROMPT],
                     capture_output=True, text=True, encoding="utf-8", errors="replace")
note = out.stdout.strip()
if out.returncode or not note:
    print("Couldn't write the note:\n" + (out.stderr or out.stdout))
    input("\nPress Enter to close.")
    sys.exit(1)

os.makedirs(os.path.join(HERE, "handoffs"), exist_ok=True)
slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "chat"
path = os.path.join(HERE, "handoffs", f"{datetime.datetime.now():%Y-%m-%d-%H%M}-{slug}.md")
with open(path, "w", encoding="utf-8") as f:
    f.write(note + "\n")
print(note + f"\n\nSaved to {path}\n")

print("Starting the cloud session...\n")
cloud = subprocess.run(["claude", "--cloud", f"Continue this work from a local session ({title}).\n\n{note}"])
print("\nThe cloud session started. Find it at claude.ai/code." if cloud.returncode == 0 else
      f"\nThe cloud session didn't start (claude exited with {cloud.returncode}). The note is saved above.")
input("Press Enter to close.")
