"""Set up T3 Olympus: the 18 god themes, your config files, and the "T3 Olympus" shortcut.

    python install.py

Safe to run again: it never overwrites your config.json or gods.json.
"""
import pathlib, shutil, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
THEMES = pathlib.Path.home() / ".t3/userdata/themes"
T3 = pathlib.Path.home() / "AppData/Local/Programs/t3code/T3 Code (Beta).exe"

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
ps = f"""
$sh = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {{
  $s = $sh.CreateShortcut((Join-Path $dir 'T3 Olympus.lnk'))
  $s.TargetPath = '{pythonw}'
  $s.Arguments = '"{HERE / "launch.pyw"}"'
  $s.WorkingDirectory = '{HERE}'
  $s.IconLocation = '{T3},0'
  $s.Save()
}}"""
subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
print('added the "T3 Olympus" shortcut to the Start Menu and Desktop')
print("Close T3, then open it from the T3 Olympus shortcut.")
