"""Set up T3 Olympus: the 30 god themes, your config files, the "T3 Olympus" shortcut,
a Startup entry that runs the buttons helper when you sign in to Windows,
and the next-step card in each profile.

    python install.py              install (safe to run again: never overwrites config.json or gods.json)
    python install.py --uninstall  remove the shortcuts, the Startup entry, the themes, the next-step card and the Temporary project
"""
import pathlib, shutil, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
THEMES = pathlib.Path.home() / ".t3/userdata/themes"
T3 = pathlib.Path.home() / "AppData/Local/Programs/t3code/T3 Code (Beta).exe"
# (folder, shortcut name, script it runs)
SHORTCUTS = [("Programs", "T3 Olympus.lnk", "launch.pyw"), ("Desktop", "T3 Olympus.lnk", "launch.pyw"),
             ("Startup", "T3 Olympus helper.lnk", "helper.py")]


def powershell(script):
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


if "--uninstall" in sys.argv:
    powershell("\n".join(f"Remove-Item -ErrorAction SilentlyContinue "
                         f"(Join-Path ([Environment]::GetFolderPath('{d}')) '{n}')" for d, n, _ in SHORTCUTS))
    for theme in THEMES.glob("pantheon-*.json"):
        theme.unlink()
    import organize
    for folder in pathlib.Path(organize.PROFILES).glob("*"):
        if folder.is_dir():
            subprocess.run(["claude", "mcp", "remove", "-s", "local", "olympus"], cwd=folder, capture_output=True)
    import temporary  # the hidden Temporary project and its folder
    if temporary.project_id():
        temporary.t3("project", "remove", temporary.DIR.replace("\\", "/"))
    shutil.rmtree(temporary.DIR, ignore_errors=True)
    print("removed the shortcuts, the Startup entry, the themes, the next-step card and the Temporary project.")
    print("Close T3, then run: python patch.py --restore")
    sys.exit()

if not T3.exists():
    sys.exit(f"T3 Code isn't installed at {T3}. Install it from https://t3.codes first.")

THEMES.mkdir(parents=True, exist_ok=True)
for theme in (HERE / "themes").glob("*.json"):
    shutil.copy2(theme, THEMES / theme.name)
print(f"copied {len(list((HERE / 'themes').glob('*.json')))} themes to {THEMES}")

for name in ("config", "gods"):
    if not (HERE / f"{name}.json").exists():
        shutil.copy2(HERE / f"{name}.example.json", HERE / f"{name}.json")
        print(f"created {name}.json from the example")

pythonw = pathlib.Path(sys.executable).with_name("pythonw.exe")
powershell("$sh = New-Object -ComObject WScript.Shell\n" + "\n".join(f"""
$s = $sh.CreateShortcut((Join-Path ([Environment]::GetFolderPath('{d}')) '{n}'))
$s.TargetPath = '{pythonw}'
$s.Arguments = '"{HERE / script}"'
$s.WorkingDirectory = '{HERE}'
$s.IconLocation = '{T3},0'
$s.Save()""" for d, n, script in SHORTCUTS))
print('added the "T3 Olympus" shortcut to the Start Menu and Desktop')
print("added the helper to Startup, so the buttons work however T3 is opened")

# the next-step card (wrapup_mcp.py) in every profile folder that exists now; new_profile.py adds it to new ones
import organize, wrapup_mcp
for folder in sorted(p for p in pathlib.Path(organize.PROFILES).glob("*") if p.is_dir()):
    wrapup_mcp.register(folder)
print("Close T3, then open it from the T3 Olympus shortcut.")
