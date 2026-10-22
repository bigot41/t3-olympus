"""Open T3 Code with T3 Olympus, re-adding it first if an update removed it,
sorting newly imported chats into the profiles, clearing leftover temporary chats,
and starting the buttons helper.

The Start Menu and Desktop "T3 Olympus" shortcuts run this with pythonw (no console).
"""
import os, subprocess, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import organize, patch, temporary

EXE = patch.RES.parent / "T3 Code (Beta).exe"

running = "T3 Code (Beta).exe" in subprocess.run(
    ["tasklist", "/FI", "IMAGENAME eq T3 Code (Beta).exe", "/NH"],
    capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout
# the archive is locked while T3 runs; patch only when it's closed
if running:
    try:
        patch.refresh()  # the unpacked files can still be updated
    except BaseException as e:
        (pathlib.Path(__file__).parent / "launch-error.txt").write_text(repr(e), encoding="utf-8")
else:
    try:
        if not patch.is_patched():
            patch.patch()
        temporary.ensure()
        temporary.sweep()  # T3 is closed, so no temporary chat is open
        temporary.scrub()  # and its database can be cleaned of deleted temporary chats
        if os.path.isdir(organize.PROFILES):
            organize.main(dry=False)  # sort newly imported chats into the profiles
    except BaseException as e:  # never block opening T3 over the art or sorting (incl. sys.exit)
        (pathlib.Path(__file__).parent / "launch-error.txt").write_text(repr(e), encoding="utf-8")
# the helper behind the Continue elsewhere / Send to cloud buttons (exits if already running)
subprocess.Popen([sys.executable, str(pathlib.Path(__file__).parent / "helper.py")], close_fds=True,
                 creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
subprocess.Popen([str(EXE), *sys.argv[1:]], close_fds=True)
