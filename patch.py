"""Add T3 Olympus (god art, profile gods, buttons, hover cards) to the installed T3 Code app.

    python patch.py            patch T3 (close T3 first)
    python patch.py --restore  put the original server.asar back

T3 serves its UI from resources/server.asar. The patch marks the UI's index.html
as "unpacked" in that archive's header and writes a copy with one extra
<link> into server.asar.unpacked, next to olympus.css and olympus.js. Nothing else in the
archive changes. A T3 update replaces server.asar, so re-run this afterwards.
"""
import base64, json, pathlib, shutil, struct, sys
from background_patch import lean_titles, sqlite_sidecars

HERE = pathlib.Path(__file__).parent
ART = HERE / "art"
RES = pathlib.Path.home() / "AppData/Local/Programs/t3code/resources"
ASAR = RES / "server.asar"
BACKUP = RES / "server.asar.olympus-orig"
CLIENT = ["apps", "server", "dist", "client"]
LINK = '<link rel="stylesheet" href="/olympus.css" data-olympus>\n  <script src="/olympus.js" defer></script>'
# A split-view pane (split.js) is T3 in a frame; the desktop app only gives its bridge to the
# top window, so a frame borrows it before T3's own code starts.
# It also keeps the frame's errors, so split.js can say why a pane stayed blank.
FRAME = ("<script>if (window !== top) { if (!window.desktopBridge) window.desktopBridge = top.desktopBridge; "
         "const e = window.olympusFrameErrors = []; "
         "addEventListener('error', (x) => e.push(String(x.message || x.error || 'failed to load ' + (x.target && (x.target.src || x.target.href)))), true); "
         "addEventListener('unhandledrejection', (x) => e.push(String((x.reason && x.reason.message) || x.reason))); }</script>")
OUT = RES / "server.asar.unpacked" / pathlib.Path(*CLIENT)
GODS = sorted(p.name[:-len("-top.png")] for p in ART.glob("*-top.png"))


def uri(god, slot):
    return "data:image/png;base64," + base64.b64encode((ART / f"{god}-{slot}.png").read_bytes()).decode()


# Where each piece of god art goes: the statue atop the sidebar, the collage at its foot, the big hero.
SLOTS = [('[data-slot="sidebar-inner"]::before', "top"),
         ('[data-slot="sidebar-inner"]::after', "bottom"),
         ('[class*="group/draft-hero"]::before', "hero")]


def theme_mode(god):
    """A god's one look ("dark" or "light"), or None when its light and dark palettes differ:
    then it follows T3's own appearance setting and has light art, art/<god>-<slot>-light.png."""
    theme = json.loads((HERE / "themes" / f"pantheon-{god}.json").read_text(encoding="utf-8"))
    variants = theme.get("variants", {})
    return theme["appearance"] if variants.get("light") == variants.get("dark") else None


def theme_css(god):
    T = f':root[data-theme-id="pantheon-{god}"]'
    looks = [(T, "")]
    if theme_mode(god) is None:  # T3 takes the "dark" class off the page in light mode
        looks.append((f"{T}:not(.dark)", "-light"))
    return "".join(f'\n{sel} {el} {{ background-image: url("{uri(god, slot + suffix)}"); }}'
                   for sel, suffix in looks for el, slot in SLOTS)


# Shared layout, the same places the Pantheon theme uses in Hermes: a statue at the top of the
# sidebar, a collage at its foot, and the big statue above the empty-chat heading.
P = ':root[data-theme-id^="pantheon-"]'
BASE = f"""
{P} [data-slot="sidebar-inner"] {{ position: relative; isolation: isolate; }}
{P} [data-slot="sidebar-inner"]::before,
{P} [data-slot="sidebar-inner"]::after {{
  content: ''; position: absolute; z-index: -1; left: 0; right: 0;
  background-repeat: no-repeat; image-rendering: pixelated; pointer-events: none;
}}
{P} [data-slot="sidebar-inner"]::before {{
  top: 0; height: 150px; background-position: center 0; background-size: 100% auto;
  -webkit-mask-image: linear-gradient(to bottom, #000 60%, transparent);
  mask-image: linear-gradient(to bottom, #000 60%, transparent);
}}
{P} [data-slot="sidebar-inner"]::after {{
  bottom: 40px; height: 150px; background-position: center bottom; background-size: 100% auto;
  border-top: 1px dotted color-mix(in srgb, currentColor 35%, transparent);
}}
/* no wordmark: the god stands where "T3 Code" was, and the list starts below it */
{P} [data-slot="sidebar-inner"] > div:first-child a[href="/#/"] {{ visibility: hidden; }}
{P} [data-slot="sidebar-inner"] > div:nth-child(2) {{ margin-top: 128px; }}
/* the thread list ends where the collage turns solid, so rows never sit on the art */
{P} [data-slot="sidebar-inner"] > [role="presentation"] {{ margin-bottom: 158px; }}
{P} [data-slot="sidebar-inner"] {{ border-right: 1px dotted color-mix(in srgb, currentColor 30%, transparent); }}

{P} [class*="group/draft-hero"]::before {{
  content: ''; position: absolute; z-index: -1; left: 50%; bottom: calc(100% - 40px);
  width: min(720px, 100%); height: min(360px, 34vh); transform: translateX(-50%);
  background: center bottom / contain no-repeat; image-rendering: pixelated; pointer-events: none;
}}
{P} [data-slot="composer-host"] {{ border: 1px dashed color-mix(in srgb, currentColor 45%, transparent); }}

/* Continue elsewhere / Send to cloud pop-up (olympus.js), in every theme */
#olympus-toast {{
  position: fixed; z-index: 9999; right: 20px; bottom: 20px; max-width: 460px; padding: 12px 34px 12px 14px;
  border-radius: 8px; font-size: 13px; line-height: 1.5; overflow-wrap: anywhere;
  background: var(--popover, Canvas); color: var(--foreground, CanvasText);
  border: 1px solid color-mix(in srgb, currentColor 30%, transparent); box-shadow: 0 6px 24px rgb(0 0 0 / .35);
}}
#olympus-toast a {{ text-decoration: underline; }}
#olympus-toast [data-close] {{ position: absolute; top: 6px; right: 8px; background: none; border: 0; color: inherit; cursor: pointer; font-size: 16px; }}
#olympus-toast [data-start], #olympus-toast .olympus-ask button {{ margin-top: 8px; padding: 3px 10px; border: 0; border-radius: 6px;
  cursor: pointer; font: inherit; background: var(--primary, Highlight); color: var(--primary-foreground, HighlightText); }}
#olympus-toast .olympus-ask {{ display: flex; gap: 6px; }}
#olympus-toast .olympus-ask [data-deny] {{ background: transparent; color: inherit; border: 1px solid color-mix(in srgb, currentColor 30%, transparent); }}
"""


def read_asar(path):
    raw = path.read_bytes()
    pickle_size = struct.unpack("<I", raw[4:8])[0]
    json_len = struct.unpack("<I", raw[12:16])[0]
    return json.loads(raw[16:16 + json_len]), raw[8 + pickle_size:]


def write_asar(path, header, data):
    j = json.dumps(header, separators=(",", ":")).encode()
    pad = (4 - len(j) % 4) % 4
    body = struct.pack("<I", len(j)) + j + b"\0" * pad
    path.write_bytes(struct.pack("<II", 4, len(body) + 4) + struct.pack("<I", len(body)) + body + data)


def node(header, parts):
    for p in parts:
        header = header["files"][p]
    return header


def files():
    """What the patch puts in T3's UI folder: index.html with one extra line, and our two files."""
    header, data = read_asar(BACKUP)
    entry = node(header, CLIENT)["files"]["index.html"]
    start = int(entry["offset"])
    html = data[start:start + entry["size"]].decode("utf-8").replace("</head>", f"  {LINK}\n  </head>", 1)
    html = html.replace("<head>", f"<head>\n    {FRAME}", 1)
    hook = "<script>" + (HERE / "olympus-hook.js").read_text(encoding="utf-8") + "</script>\n  "
    html = html.replace('<script type="module"', hook + '<script type="module"', 1)  # runs before T3's own code
    gods = (HERE / "gods.json").read_text(encoding="utf-8") if (HERE / "gods.json").exists() else "{}"
    gods = json.dumps(json.loads(gods))
    # gods with one look, which olympus.js pins the window buttons to; the rest follow T3's setting
    modes = json.dumps({g: m for g in GODS if (m := theme_mode(g))})
    js = ((HERE / "olympus.js").read_text(encoding="utf-8").replace("/*GODS*/ {}", gods).replace("/*MODES*/ {}", modes)
          + "".join("\n" + (HERE / f).read_text(encoding="utf-8") for f in
                    ("cards.js", "turnlogic.js", "turnbox.js", "panel.js", "temporary.js", "split.js", "voice.js", "compact.js", "usage.js", "pets.js")))
    return {"index.html": html, "olympus.css": BASE + "".join(theme_css(g) for g in GODS), "olympus.js": js}


def server_files():
    """Return the version-checked server overlay for lightweight title requests."""
    header, data = read_asar(BACKUP)
    parts = ["apps", "server", "dist"]
    for name, entry in node(header, parts)["files"].items():
        if not name.startswith("binCli-") or not name.endswith(".mjs"):
            continue
        start = int(entry["offset"])
        source = data[start:start + entry["size"]].decode("utf-8")
        if 'return fromRunner("ClaudeTextGeneration",' in source:
            return {pathlib.Path(*parts, name): sqlite_sidecars(lean_titles(source))}
    raise ValueError("Unsupported T3 version: Claude title-generation module not found")


def stage_server():
    """Write the server overlay without modifying the archive of a running T3."""
    for relative, text in server_files().items():
        path = pathlib.Path(str(ASAR) + ".unpacked") / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")


def is_unpacked():
    return "unpacked" in node(read_asar(ASAR)[0], CLIENT)["files"]["index.html"]


def patch():
    # an unpatched server.asar (first run, or a T3 update) becomes the new backup
    if not BACKUP.exists() or not is_unpacked():
        shutil.copy2(ASAR, BACKUP)
    header, data = read_asar(BACKUP)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in files().items():
        (OUT / name).write_text(text, encoding="utf-8")
        node(header, CLIENT)["files"][name] = {"size": len(text.encode()), "unpacked": True}
    stage_server()
    for relative, text in server_files().items():
        node(header, list(relative.parts[:-1]))["files"][relative.name] = {"size": len(text.encode()), "unpacked": True}
    write_asar(ASAR, header, data)
    print(f"patched {ASAR} ({len(GODS)} gods)")


def refresh():
    """Rewrite stale files in T3's unpacked UI folder. Works while T3 runs (server.asar is untouched)."""
    if not is_unpacked():
        return False
    stage_server()
    wrote = False
    for name, text in files().items():
        path = OUT / name
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
            wrote = True
    return wrote


def is_patched():
    """True when T3 has the current art, buttons, cards and gods.json map."""
    try:
        header = read_asar(ASAR)[0]
        server_ready = all(node(header, list(relative.parts)).get("unpacked") and
                           (pathlib.Path(str(ASAR) + ".unpacked") / relative).read_text(encoding="utf-8") == text
                           for relative, text in server_files().items())
        return server_ready and is_unpacked() and all((OUT / n).read_text(encoding="utf-8") == t for n, t in files().items())
    except OSError:
        return False


def restore():
    shutil.copy2(BACKUP, ASAR)
    for name in ("index.html", "olympus.css", "olympus.js"):
        (OUT / name).unlink(missing_ok=True)
    for relative in server_files():
        (pathlib.Path(str(ASAR) + ".unpacked") / relative).unlink(missing_ok=True)
    print("restored the original server.asar")


if __name__ == "__main__":
    restore() if "--restore" in sys.argv else patch()
