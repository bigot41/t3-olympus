"""Desktop pets: one small god per profile that sits on your desktop, like ChatGPT's pets.

    pythonw pets.pyw    the T3 Olympus shortcut starts it; one copy runs at a time

Each pet is its profile's god on a round medallion, showing what that profile's chats are doing
(read from T3's database):

  idle      sits still
  working   floats gently, with a "..." badge, while a chat in the profile runs
  done      hops and chimes, with a sun badge, until you open that chat (also when T3 is minimised)
  needs you a pulsing "!" badge while Claude waits for you (an approval or a question)

Click a pet to bring T3 forward on that profile's chat (a new one if it has none). Drag to move
it (it remembers where). Hover for the profile's name, right-click for more. The pets leave when
T3 closes; the helper starts them again whenever T3 is open, however it was opened.

Right-click > Hide pets, or Ctrl+Alt+P in T3, turns them off until you press Ctrl+Alt+P again
(local/pets-off is there while they're off).
"""
import ctypes, datetime, json, math, os, pathlib, socket, sqlite3, subprocess, sys, threading, time
import tkinter as tk
from tkinter import ttk, messagebox
from ctypes import wintypes
from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from organize import PROFILES

HOME = pathlib.Path.home()
DB = HOME / ".t3" / "userdata" / "statev2.sqlite"
EXE = HOME / "AppData" / "Local" / "Programs" / "t3code" / "T3 Code (Beta).exe"
LOCAL = HERE / "local"
PLACES = LOCAL / "pets-v2.json"    # where you left each pet
OPEN = LOCAL / "pets-open.json"    # a chat a pet asked T3 to open (pets.js picks it up through the helper)
SEEN = LOCAL / "pets-seen.json"    # the chat T3 shows now (written by the helper for pets.js)
OFF = LOCAL / "pets-off"           # there while you've turned the pets off (the helper's PETS_OFF)
PORT = 47834                       # held while a copy runs, so a second copy exits
SETTINGS = LOCAL / "pets-settings.json"


def _dpi_scale():
    """Draw at the screen's real pixel density (125% scaling draws everything 1.25x larger)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96
    except Exception:
        return 1.0


def dpi_of(hwnd):
    """The scaling of the monitor a window is on (follows changes in Settings and monitor moves)."""
    try:
        return ctypes.windll.user32.GetDpiForWindow(hwnd) / 96 or SYSTEM_SCALE
    except Exception:
        return SYSTEM_SCALE


def set_scale(scale):
    """Size everything for a screen scaling (1.0 = 100%, 1.5 = 150%...). Pictures are drawn fresh at
    that size, never stretched, so every scaling gets crisp edges."""
    global SCALE, COIN, BADGE, GLOW, SPRITE_W, SPRITE_H, LIFT_ROOM, W, H
    SCALE = scale
    COIN = round(78 * SCALE)           # medallion diameter, in screen pixels
    BADGE = round(30 * SCALE)          # badge diameter
    GLOW = round(6 * SCALE)            # room around a badge for its glow or shadow
    SPRITE_W = SPRITE_H = COIN + 2 * round(COIN * 0.12) + round(20 * SCALE)  # medallion, shadow, badge
    LIFT_ROOM = round(14 * SCALE)      # room above for the bounce
    W = SPRITE_W + round(44 * SCALE)   # window: wide enough for the name plaque
    H = LIFT_ROOM + SPRITE_H + round(26 * SCALE)


SYSTEM_SCALE = _dpi_scale()
set_scale(SYSTEM_SCALE)
ENDED = {"completed", "failed", "interrupted", "cancelled", "canceled"}
WAIT_FOR_T3 = 90                   # seconds to wait for T3 to open before giving up

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetDpiForWindow.argtypes = [wintypes.HWND]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def monitor_workarea(hwnd):
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    monitor = user32.MonitorFromWindow(hwnd, 2)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise ctypes.WinError()
    area = info.rcWork
    return (area.left, area.top, area.right, area.bottom)


def pet_settings():
    settings = read_json(SETTINGS, {})
    if not isinstance(settings, dict):
        settings = {}
    selected = settings.get("selected")
    sizes = settings.get("sizes", {})
    return {"selected": selected if isinstance(selected, list) else None,
            "size": valid_size(settings.get("size", 100)),
            "sizes": {name: valid_size(size) for name, size in sizes.items()}
            if isinstance(sizes, dict) else {}}


def valid_size(value):
    return max(50, min(150, value)) if type(value) in (int, float) and math.isfinite(value) else 100


def place_on_monitor(place, area, index, cell=None):
    left, top, right, bottom = area
    cell_width, cell_height = cell or (W, H)
    if (not isinstance(place, (list, tuple)) or len(place) != 2 or
            not all(type(value) in (int, float) and math.isfinite(value) for value in place) or
            not (left <= place[0] < right and top <= place[1] < bottom)):
        columns = max(1, (right - left - 40) // (cell_width + 6))
        column, row = index % columns, index // columns
        place = (right - (column + 1) * (cell_width + 6) - 20,
                 bottom - H - 16 - row * (cell_height + 6))
    return (round(max(left, min(place[0], right - W))),
            round(max(top, min(place[1], bottom - H))))


def configure_pets():
    pythonw = pathlib.Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pythonw if pythonw.exists() else sys.executable), str(HERE / "pets.pyw"),
                      "--settings"], cwd=HERE, close_fds=True)


def settings_dialog():
    root = tk.Tk()
    root.title("Desktop pets")
    root.minsize(440, 360)
    settings = pet_settings()
    content = ttk.Frame(root, padding=20)
    content.pack(fill="both", expand=True)
    ttk.Label(content, text="Your desktop companions", font=("Segoe UI", 15, "bold")).pack(anchor="w")
    ttk.Label(content, text="Choose which profiles appear. Changes apply when you save.").pack(anchor="w", pady=(6, 14))
    enabled = tk.BooleanVar(value=not OFF.exists())
    ttk.Checkbutton(content, text="Show desktop pets", variable=enabled).pack(anchor="w")
    size = tk.IntVar(value=round(settings["size"]))
    size_label = ttk.Label(content, text=f"Default size: {size.get()}%")
    size_label.pack(anchor="w", pady=(14, 0))
    tk.Scale(content, from_=50, to=150, resolution=5, orient="horizontal", variable=size,
             showvalue=False, highlightthickness=0,
             command=lambda value: size_label.configure(text=f"Default size: {int(float(value))}%")).pack(fill="x")
    frame = ttk.Frame(content)
    frame.pack(fill="both", expand=True)
    canvas = tk.Canvas(frame, height=240, highlightthickness=0)
    scroll = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    rows = ttk.Frame(canvas)
    ttk.Label(rows, text="Visible profiles").grid(row=0, column=0, sticky="w", pady=(10, 6))
    ttk.Label(rows, text="Size override").grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(10, 6))
    window = canvas.create_window((0, 0), window=rows, anchor="nw")
    rows.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
    choices, overrides = {}, {}
    try:
        available = profiles()
    except sqlite3.Error as error:
        messagebox.showerror("Desktop pets", f"Couldn't read T3's profiles. Try again.\n{error}", parent=root)
        root.destroy()
        return
    for index, info in enumerate(available, start=1):
        name = info["name"]
        choices[name] = tk.BooleanVar(value=settings["selected"] is None or name in settings["selected"])
        override = settings["sizes"].get(name)
        overrides[name] = tk.StringVar(value=f"{override:g}%" if override is not None else "Default")
        ttk.Checkbutton(rows, text=name, variable=choices[name]).grid(row=index, column=0, sticky="w", pady=4)
        ttk.Combobox(rows, textvariable=overrides[name], values=("Default", "50%", "75%", "100%", "125%", "150%"),
                     state="readonly", width=9).grid(row=index, column=1, padx=(12, 0))
    rows.columnconfigure(0, weight=1)
    actions = ttk.Frame(content)
    actions.pack(fill="x", pady=(12, 0))
    ttk.Button(actions, text="Select all", command=lambda: [value.set(True) for value in choices.values()]).pack(side="left")
    ttk.Button(actions, text="Select none", command=lambda: [value.set(False) for value in choices.values()]).pack(side="left", padx=6)

    def save():
        selected = [name for name in settings["selected"] or [] if name not in choices]
        selected.extend(name for name, value in choices.items() if value.get())
        sizes = dict(settings["sizes"])
        for name, value in overrides.items():
            sizes.pop(name, None)
            if value.get() != "Default":
                sizes[name] = float(value.get().rstrip("%"))
        try:
            write_json(SETTINGS, {"selected": selected, "size": size.get(), "sizes": sizes})
            if enabled.get():
                OFF.unlink(missing_ok=True)
                subprocess.Popen([sys.executable, str(HERE / "pets.pyw")], cwd=HERE, close_fds=True,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                OFF.touch()
        except OSError as error:
            messagebox.showerror("Desktop pets", str(error), parent=root)
            return
        root.destroy()

    ttk.Button(actions, text="Save", command=save).pack(side="right")
    ttk.Button(actions, text="Cancel", command=root.destroy).pack(side="right", padx=6)
    root.bind("<Escape>", lambda event: root.destroy())
    root.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
    windows = t3_windows()
    left, top, right, bottom = monitor_workarea(windows[0] if windows else None)
    root.update_idletasks()
    user32.SetWindowPos(int(root.wm_frame(), 16), 0,
                        left + max(0, (right - left - root.winfo_width()) // 2),
                        top + max(0, (bottom - top - root.winfo_height()) // 2), 0, 0, 0x15)
    root.mainloop()


def when(stamp):
    """An ISO time from T3's database as epoch seconds (0 when missing)."""
    if not stamp:
        return 0.0
    try:
        return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


seen_at = {}  # chat id -> when you last looked at it in T3 with T3 as your active window
frozen = {}   # chat id -> T3's "last visited" when you left T3 with that chat on screen


def profiles():
    """[{name, god, state, thread, title}] for each profile T3 knows, from its database."""
    seen = read_json(SEEN, {})
    fresh = time.time() - seen.get("time", 0) < 6
    showing = seen.get("thread") if fresh else None   # the chat on T3's screen
    looking = bool(fresh and seen.get("focus"))       # T3 is the window you're using
    if showing and looking:
        seen_at[showing] = time.time()
    gods = read_json(HERE / "gods.json", {})
    root = os.path.normcase(os.path.normpath(PROFILES))
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=1)
    try:
        projects = [(pid, title) for pid, title, folder in con.execute(
            "select project_id, title, workspace_root from projection_projects where deleted_at is null")
            if os.path.normcase(os.path.dirname(os.path.normpath(folder))) == root]
        latest = {t: (status, done) for t, status, done in con.execute(
            "select thread_id, status, completed_at from orchestration_v2_projection_runs r "
            "where ordinal = (select max(ordinal) from orchestration_v2_projection_runs where thread_id = r.thread_id)")}
        waiting = {t for (t,) in con.execute(
            "select distinct thread_id from orchestration_v2_projection_runtime_requests where resolved_at is null")}
        result = []
        for pid, name in sorted(projects, key=lambda p: p[1].lower()):
            chats = con.execute(
                "select thread_id, title, updated_at, payload_json from orchestration_v2_projection_threads "
                "where project_id = ? and deleted_at is null and archived_at is null", (pid,)).fetchall()
            best = None  # (rank, time, thread, title, state): needs > working > done > idle, newest first
            for thread, title, updated, payload in chats:
                run = latest.get(thread)
                db_visit = when(json.loads(payload or "{}").get("lastVisitedAt"))
                if thread == showing and not looking:
                    # T3 keeps marking the chat on screen as visited even while it's minimised or
                    # behind other windows; only count the time you were actually looking at it
                    visited = seen_at.get(thread) or frozen.setdefault(thread, db_visit)
                else:
                    frozen.pop(thread, None)
                    visited = max(db_visit, seen_at.get(thread, 0))
                if thread in waiting:
                    state = "needs"
                elif run and run[0] not in ENDED and not run[1]:
                    state = "working"
                elif run and run[0] == "completed" and when(run[1]) > visited:
                    state = "done"
                else:
                    state = "idle"
                rank = {"needs": 3, "working": 2, "done": 1, "idle": 0}[state]
                key = (rank, when(run[1]) if run and run[1] else when(updated))
                if best is None or key > best[:2]:
                    best = (*key, thread, title, state)
            result.append({"name": name, "god": gods.get(name, "olympus"),
                           "state": best[4] if best else "idle",
                           "thread": best[2] if best else None, "title": best[3] if best else ""})
        return result
    finally:
        con.close()


# --- T3's window, found through Windows directly (fast; no new T3 process per click) ---

def _exe_of(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(520), wintypes.DWORD(520)
        return buf.value if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)) else ""
    finally:
        kernel32.CloseHandle(h)


def t3_windows():
    """T3's top-level windows that have a title (its main window, shown or minimised)."""
    found, exe = [], str(EXE).lower()
    cache = {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if user32.GetWindowTextLengthW(hwnd) and user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in cache:
                cache[pid.value] = _exe_of(pid.value).lower() == exe
            if cache[pid.value]:
                found.append(hwnd)
        return True

    user32.EnumWindows(each, 0)
    return found


def t3_running():
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXE.name}", "/NH"], capture_output=True,
                         text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    return EXE.name in out


def open_t3(thread=None, profile=None):
    """Bring T3 forward on that chat, or on a new chat in the profile when it has none yet."""
    if thread or profile:
        write_json(OPEN, {"thread": thread, "profile": profile, "time": time.time()})
    windows = t3_windows()
    if windows:
        hwnd = windows[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)  # allowed: the pet was just clicked
    elif t3_running():
        subprocess.Popen([str(EXE)], close_fds=True)  # window hidden: T3 shows it again
    else:
        pythonw = pathlib.Path(sys.executable).with_name("pythonw.exe")
        subprocess.Popen([str(pythonw), str(HERE / "launch.pyw")], close_fds=True, cwd=HERE)


# --- drawing: everything is drawn with PIL at 4x and shrunk, then shown with true per-pixel
# transparency (a Windows layered window), so every edge is smooth on any background ---

FONTS = pathlib.Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
FPS, CYCLE = 30, 1.8               # animation frame rate; seconds per working / done loop
FRAMES = round(FPS * CYCLE)
SS = 4                             # supersampling: draw this many times larger, then shrink
GOLD, GOLD_LIGHT, GOLD_DARK = (226, 184, 92), (250, 226, 160), (138, 98, 36)


def palette(god):
    """(medallion background, rim accent, text on the accent) from the god's T3 theme."""
    colors = read_json(HERE / "themes" / f"pantheon-{god}.json", {}).get("colors", {})
    return colors.get("canvas", "#e9e2d4"), colors.get("accent", "#6b5a3e"), colors.get("accentForeground", "#ffffff")


def rgb(colour):
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def font(size):
    """Palatino bold (ships with Windows): carved-inscription capitals; Georgia if it's missing."""
    from PIL import ImageFont
    for name in ("palab.ttf", "georgiab.ttf"):
        try:
            return ImageFont.truetype(str(FONTS / name), size)
        except OSError:
            pass
    return ImageFont.load_default()


def disc(d, cx, cy, r, inner, outer, steps=24):
    """A filled circle shaded from a light upper-left to its edge colour, like polished metal."""
    for i in range(steps, 0, -1):
        t = i / steps
        rr = r * t
        ox, oy = -r * 0.28 * (1 - t), -r * 0.32 * (1 - t)  # the highlight sits up and to the left
        d.ellipse((cx + ox - rr, cy + oy - rr, cx + ox + rr, cy + oy + rr), fill=mix(inner, outer, t))


def shadow(size, box, blur, alpha):
    from PIL import ImageFilter
    s = Image.new("L", size, 0)
    ImageDraw.Draw(s).ellipse(box, fill=alpha)
    return s.filter(ImageFilter.GaussianBlur(blur))


def coin_image(god):
    """The god's head filling a round medallion: a polished rim in the theme colour with a fine gold
    inner line, and a soft shadow under it (RGBA, COIN + room for the shadow). The art is cut off at
    its top edge, so the circle starts a little inside the hair and its edge frames the whole head."""
    path = HERE / "art" / f"{god}-top.png"
    if not path.exists():
        path = HERE / "art" / "olympus-top.png"
    back, accent = rgb(palette(god)[0]), rgb(palette(god)[1])
    art = Image.open(path).convert("RGBA")
    l, t, r, b = art.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox() or (0, 0, *art.size)
    side, cx, top = round((b - t) * 0.86), (l + r) // 2, t + 2
    big = COIN * SS
    rim = max(3, round(big * 0.055))
    face = Image.new("RGBA", art.size, back)
    face.alpha_composite(art)
    face = face.crop((cx - side // 2, top, cx + side // 2, top + side)).resize((big - 2 * rim, big - 2 * rim), Image.NEAREST)
    coin = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(coin)
    disc(d, big / 2, big / 2, big / 2, mix(accent, (255, 255, 255), 0.45), mix(accent, (0, 0, 0), 0.25))  # the rim
    mask = Image.new("L", face.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, face.width - 1, face.height - 1), fill=255)
    coin.paste(face, (rim, rim), mask)
    g = rim * 0.35
    d.ellipse((rim - g, rim - g, big - rim + g, big - rim + g), outline=GOLD, width=max(2, round(SS * 0.9)))
    d.ellipse((1, 1, big - 2, big - 2), outline=mix(accent, (0, 0, 0), 0.45), width=max(2, SS // 2))  # crisp outer edge
    coin = coin.resize((COIN, COIN), Image.LANCZOS)
    pad = round(COIN * 0.12)
    out = Image.new("RGBA", (COIN + 2 * pad, COIN + 2 * pad), (0, 0, 0, 0))
    out.putalpha(shadow(out.size, (pad + 4 * SCALE, pad + 8 * SCALE, pad + COIN - 4 * SCALE, pad + COIN + 4 * SCALE),
                        5 * SCALE, 120))
    out.paste((20, 14, 10), mask=out.getchannel("A"))
    out.alpha_composite(coin, (pad, pad))
    return out


SUN_RAY, SUN_DARK, SUN_LIGHT, SUN_EDGE = (250, 230, 150), (176, 84, 26), (226, 140, 52), (120, 52, 16)


def flame(d, c, r, angle, r0, r1, width, waves, sway, phase):
    """One ray: a ribbon that starts wide at the centre and narrows to a point, curving in a wave
    that travels outward (phase 0..1), so the ray seems to shimmer like heat off the sun."""
    left, right, steps = [], [], 28
    for k in range(steps + 1):
        t = k / steps
        rad = r0 + (r1 - r0) * t
        bend = sway * math.sin(2 * math.pi * (waves * t - phase)) * t ** 0.9  # grows toward the tip
        ang = angle + bend * r / rad
        px, py = c + rad * math.cos(ang), c + rad * math.sin(ang)
        w = width * (1 - t) ** 0.85 + r * 0.008
        nx, ny = -math.sin(ang), math.cos(ang)
        left.append((px + nx * w, py + ny * w))
        right.append((px - nx * w, py - ny * w))
    d.polygon(left + right[::-1], fill=SUN_RAY)


def spiral_sun(img, c, r, phase):
    """The done badge: a sun painted on a glazed clay disc. Pale yellow rays, long wavy flames
    with short ones between, radiate from a still spiral; only the rays move, shimmering outward."""
    import random
    from PIL import ImageFilter, ImageChops
    d = ImageDraw.Draw(img)
    disc(d, c, c, r, GOLD_LIGHT, GOLD_DARK)
    d.ellipse((c - r * 0.93, c - r * 0.93, c + r * 0.93, c + r * 0.93), fill=SUN_EDGE)
    disc(d, c, c, r * 0.905, SUN_LIGHT, SUN_DARK)
    # a mottled, painted finish: soft blotches, the same every frame
    clip = Image.new("L", img.size, 0)
    ImageDraw.Draw(clip).ellipse((c - r * 0.9, c - r * 0.9, c + r * 0.9, c + r * 0.9), fill=255)
    rng = random.Random(11)
    blot = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(blot)
    for _ in range(40):
        a, dist = rng.uniform(0, 2 * math.pi), r * 0.9 * math.sqrt(rng.random())
        x, y, s = c + dist * math.cos(a), c + dist * math.sin(a), r * rng.uniform(0.06, 0.16)
        bd.ellipse((x - s, y - s, x + s, y + s), fill=rng.choice(((110, 44, 10, 34), (255, 190, 110, 26))))
    blot = blot.filter(ImageFilter.GaussianBlur(r * 0.05))
    blot.putalpha(ImageChops.multiply(blot.getchannel("A"), clip))
    img.alpha_composite(blot)
    d = ImageDraw.Draw(img)
    # the rays: 6 long wavy flames and 6 short ones between them, each with its own timing
    for i in range(6):
        base = -math.pi / 2 + 2 * math.pi * i / 6
        reach = 0.8 + 0.03 * math.sin(2 * math.pi * (phase + i / 6))  # a gentle pulse, ray by ray
        flame(d, c, r, base, r * 0.38, r * reach, r * 0.1, 1.4, 0.1, phase + i * 0.17)
        short = base + math.pi / 6
        flame(d, c, r, short, r * 0.41, r * (0.6 + 0.02 * math.sin(2 * math.pi * (phase + i / 6 + 0.5))),
              r * 0.07, 1.0, 0.06, phase + 0.5 + i * 0.13)
    # the heart: a bold spiral that stays still
    stroke = r * 0.05
    for k in range(600):
        t = k / 599
        ang = -math.pi / 2 + 2 * math.pi * 1.35 * t
        rad = r * (0.03 + 0.24 * t)
        x, y = c + rad * math.cos(ang), c + rad * math.sin(ang)
        d.ellipse((x - stroke, y - stroke, x + stroke, y + stroke), fill=SUN_RAY)
    # a soft gloss, like glazed clay
    gloss = Image.new("L", img.size, 0)
    ImageDraw.Draw(gloss).ellipse((c - r * 0.75, c - r * 0.92, c + r * 0.3, c - r * 0.3), fill=55)
    gloss = gloss.filter(ImageFilter.GaussianBlur(r * 0.14))
    shine = Image.new("RGBA", img.size, (255, 255, 255, 0))
    shine.putalpha(ImageChops.multiply(gloss, clip))
    img.alpha_composite(shine)


def badge(state, phase):
    """A badge (RGBA, BADGE px plus room for its glow) at a point (0..1) in its loop.
    working: an amber gem with three dots that swell in turn; done: a painted sun whose rays shimmer
    outward around a still spiral, with a breathing glow; needs: a crimson gem with a carved "!"."""
    size = round(BADGE * (1.1 if state == "done" else 1)) + 2 * GLOW
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    c, r = S / 2, (size - 2 * GLOW) * SS / 2
    if state == "done":  # a soft golden halo that breathes
        glow = 0.5 + 0.5 * math.sin(2 * math.pi * phase)
        from PIL import ImageFilter
        halo = Image.new("L", (S, S), 0)
        ImageDraw.Draw(halo).ellipse((c - r * 1.15, c - r * 1.15, c + r * 1.15, c + r * 1.15), fill=round(70 + 60 * glow))
        halo = halo.filter(ImageFilter.GaussianBlur(GLOW * SS * 0.45))
        layer = Image.new("RGBA", (S, S), GOLD_LIGHT + (0,))
        layer.putalpha(halo)
        img.alpha_composite(layer)
    else:
        img.putalpha(shadow((S, S), (c - r * 0.9, c - r * 0.75, c + r * 0.9, c + r * 1.15), SS * 2 * SCALE, 110))
    d = ImageDraw.Draw(img)
    ring = r * 0.13
    if state == "working":
        d.ellipse((c - r, c - r, c + r, c + r), fill=(255, 250, 240))
        disc(d, c, c, r - ring, (247, 205, 120), (196, 132, 34))
        for i in range(3):
            swell = 0.5 + 0.5 * math.sin(2 * math.pi * phase - i * 1.1)  # each dot follows the one before
            dr = r * (0.11 + 0.07 * swell)
            x, y = c + (i - 1) * r * 0.42, c - r * 0.08 * swell
            d.ellipse((x - dr, y - dr, x + dr, y + dr), fill=(255, 255, 255, round(170 + 85 * swell)))
    elif state == "done":
        spiral_sun(img, c, r, phase)
    elif state == "needs":
        swell = 0.5 + 0.5 * math.sin(2 * math.pi * phase)
        rr = r * (0.94 + 0.06 * swell)
        d.ellipse((c - rr, c - rr, c + rr, c + rr), fill=(255, 250, 240))
        disc(d, c, c, rr - ring, (232, 112, 96), (160, 40, 32))
        d.text((c, c + r * 0.06), "!", font=font(round(r * 1.25)), fill="white", anchor="mm")
    return img.resize((size, size), Image.LANCZOS)


def label_image(text, accent, ink):
    """The name as spaced Palatino capitals on a polished plaque in the god's colour (RGBA)."""
    f = font(round(11 * SCALE * SS))
    text = text.upper()
    track = 1.7 * SCALE * SS  # letter spacing, like a carved inscription
    widths = [f.getlength(ch) for ch in text]
    w = round(sum(widths) + track * (len(text) - 1) + 24 * SCALE * SS)
    h = round(20 * SCALE * SS)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    a = rgb(accent)
    d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=mix(a, (0, 0, 0), 0.35))
    d.rounded_rectangle((SS, SS, w - 1 - SS, h - 1 - SS), h // 2 - SS, fill=a)
    inset = round(2.4 * SCALE * SS)
    d.rounded_rectangle((inset, inset, w - 1 - inset, h - 1 - inset), h // 2 - inset, outline=GOLD + (210,),
                        width=max(2, round(SCALE * SS * 0.8)))
    x = 12 * SCALE * SS
    for ch, cw in zip(text, widths):
        d.text((x, h / 2 + SS), ch, font=f, fill=ink, anchor="lm")
        x += cw + track
    return img.resize((round(w / SS), round(h / SS)), Image.LANCZOS)


def pet_frames(god):
    """Every picture a pet shows, drawn once: {state: [frames]}, the badge on the medallion."""
    coin = coin_image(god)
    frames = {"idle": [_with_badge(coin, None, 0)]}
    for state in ("working", "done", "needs"):
        frames[state] = [_with_badge(coin, state, i / FRAMES) for i in range(FRAMES)]
    return frames


def _with_badge(coin, state, phase):
    img = Image.new("RGBA", (SPRITE_W, SPRITE_H), (0, 0, 0, 0))
    img.alpha_composite(coin, (0, SPRITE_H - coin.height))
    if state:
        b = badge(state, phase)
        pad = (coin.width - COIN) // 2
        # the badge's centre sits on the rim at about one o'clock
        bx = pad + round(COIN / 2 + COIN * 0.36) - b.width // 2
        by = SPRITE_H - coin.height + pad + round(COIN / 2 - COIN * 0.36) - b.height // 2
        img.alpha_composite(b, (bx, by))
    return img


# --- the pet windows: Tk windows that Windows draws from our pictures with per-pixel alpha ---

class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte), ("AlphaFormat", ctypes.c_byte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


gdi32 = ctypes.windll.gdi32
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wintypes.HANDLE, wintypes.DWORD]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_void_p, ctypes.POINTER(wintypes.SIZE),
                                       wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
                                       ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]


def premultiplied(img):
    """BGRA bytes with colour premultiplied by alpha, as UpdateLayeredWindow wants."""
    from PIL import Image, ImageChops
    r, g, b, a = img.split()
    return Image.merge("RGBA", (ImageChops.multiply(b, a), ImageChops.multiply(g, a),
                                ImageChops.multiply(r, a), a)).tobytes()


class Layered:
    """Shows a picture in a Tk window with true per-pixel transparency."""

    def __init__(self, win):
        win.update_idletasks()
        self.hwnd = int(win.wm_frame(), 16)
        style = user32.GetWindowLongW(self.hwnd, -20)  # GWL_EXSTYLE
        user32.SetWindowLongW(self.hwnd, -20, style | 0x80000 | 0x80)  # LAYERED | TOOLWINDOW (no taskbar button)
        self.keep_on_top()

    def keep_on_top(self):
        user32.SetWindowPos(self.hwnd, -1, 0, 0, 0, 0, 0x13)  # HWND_TOPMOST; no move, size or focus

    def show(self, data, w, h):
        screen = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen)
        info = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        bmp = gdi32.CreateDIBSection(mem, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
        try:
            ctypes.memmove(bits, data, len(data))
            old = gdi32.SelectObject(mem, bmp)
            blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, full opacity, per-pixel alpha
            user32.UpdateLayeredWindow(self.hwnd, screen, None, ctypes.byref(wintypes.SIZE(w, h)), mem,
                                       ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend), 2)  # ULW_ALPHA
            gdi32.SelectObject(mem, old)
        finally:
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(None, screen)


class Pet:
    def __init__(self, app, info, place, scale):
        self.app, self.name = app, info["name"]
        self.scale = scale
        set_scale(scale)
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.geometry(f"{W}x{H}")
        frame = tk.Frame(self.win, width=W, height=H, cursor="hand2")
        frame.pack()
        self.layer = Layered(self.win)
        user32.SetWindowPos(self.layer.hwnd, 0, *place, 0, 0, 0x15)
        self.god, self.state, self.thread, self.title = None, None, None, ""
        self.bounce_until, self.hover, self.last = 0.0, False, None
        self.cache = {}  # (frame, lift, hover) -> premultiplied bytes
        for widget in (self.win, frame):
            for seq, fn in (("<ButtonPress-1>", self.press), ("<B1-Motion>", self.drag),
                            ("<ButtonRelease-1>", self.release), ("<Button-3>", self.menu),
                            ("<Enter>", lambda e: setattr(self, "hover", True)),
                            ("<Leave>", lambda e: setattr(self, "hover", False))):
                widget.bind(seq, fn)
        self.update(info)

    def update(self, info):
        set_scale(self.scale)
        if info["god"] != self.god:
            self.god = info["god"]
            self.frames = pet_frames(self.god)
            _, accent, ink = palette(self.god)
            self.plaque = label_image(self.name, accent, ink)
            if self.plaque.width > W:
                self.plaque = self.plaque.resize((W, round(self.plaque.height * W / self.plaque.width)), Image.LANCZOS)
            self.cache.clear()
        if info["state"] == "done" and self.state not in (None, "done"):
            self.bounce_until = time.time() + 1.4
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
            except Exception:
                pass
        self.state, self.thread, self.title = info["state"], info["thread"], info["title"]

    def draw(self, now):
        set_scale(self.scale)
        frames = self.frames.get(self.state) or self.frames["idle"]
        index = int(now * FPS) % len(frames)
        lift = 0
        if self.state == "working":  # a slow, gentle float
            lift = round(3 * SCALE * (0.5 - 0.5 * math.cos(2 * math.pi * now / CYCLE)))
        if now < self.bounce_until:  # two hops that settle
            t = 1 - (self.bounce_until - now) / 1.4
            lift = round(12 * SCALE * abs(math.sin(t * 2 * math.pi)) * (1 - t))
        key = (self.state, index, lift, self.hover)
        if key == self.last:
            return
        self.last = key
        data = self.cache.get(key)
        if data is None:
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            img.alpha_composite(frames[index], ((W - SPRITE_W) // 2, LIFT_ROOM - lift))
            if self.hover:
                img.alpha_composite(self.plaque, ((W - self.plaque.width) // 2, H - self.plaque.height - 2))
            data = premultiplied(img)
            if len(self.cache) < 600:
                self.cache[key] = data
        self.layer.show(data, W, H)

    def press(self, e):
        self.start = (e.x_root, e.y_root, self.win.winfo_x(), self.win.winfo_y())
        self.moved = False

    def drag(self, e):
        dx, dy = e.x_root - self.start[0], e.y_root - self.start[1]
        if abs(dx) + abs(dy) > 4:
            self.moved = True
        if self.moved:
            user32.SetWindowPos(self.layer.hwnd, 0, self.start[2] + dx, self.start[3] + dy, 0, 0, 0x15)

    def release(self, e):
        if self.moved:
            self.app.save_places()
        else:
            open_t3(self.thread, self.name)

    def menu(self, e):
        m = tk.Menu(self.win, tearoff=0)
        m.add_command(label=f"Open {self.name}" + (f": {self.title[:30]}" if self.title else ""),
                      command=lambda: open_t3(self.thread, self.name))
        m.add_command(label=f"New chat in {self.name}", command=lambda: open_t3(None, self.name))
        m.add_separator()
        m.add_command(label="Choose pets and sizes…", command=configure_pets)
        m.add_command(label="Hide pets (Ctrl+Alt+P in T3 brings them back)", command=self.app.hide)
        m.tk_popup(e.x_root, e.y_root)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.pets = {}
        self.places = read_json(PLACES, {})
        if not isinstance(self.places, dict):
            self.places = {}
        self.area = None
        self.started = time.time()
        self.seen_t3 = False
        self.t3_up = True
        threading.Thread(target=self.watch_t3, daemon=True).start()
        self.poll()
        self.animate()

    def watch_t3(self):
        """Leave when T3 closes (or never opens)."""
        while True:
            up = t3_running()
            if up:
                self.seen_t3 = True
            if (self.seen_t3 and not up) or (not self.seen_t3 and time.time() - self.started > WAIT_FOR_T3):
                self.t3_up = False
                return
            time.sleep(1.5)

    def hide(self):
        """Turn the pets off, so the helper doesn't start them again until Ctrl+Alt+P."""
        LOCAL.mkdir(exist_ok=True)
        OFF.touch()
        self.root.destroy()

    def save_places(self):
        self.places.update({n: [p.win.winfo_x(), p.win.winfo_y()] for n, p in self.pets.items()})
        write_json(PLACES, self.places)

    def poll(self):
        if not self.t3_up or OFF.exists():  # T3 closed, or you turned the pets off
            self.root.destroy()
            return
        try:
            found = profiles()
        except sqlite3.Error:
            found = None  # T3 is writing; try again next time
        for pet in self.pets.values():
            pet.layer.keep_on_top()
        windows = t3_windows()
        foreground = user32.GetForegroundWindow()
        hwnd = foreground if foreground in windows else windows[0] if windows else None
        area = monitor_workarea(hwnd) if hwnd else self.area or monitor_workarea(None)
        if area != self.area:
            self.save_places()
            for pet in self.pets.values():
                pet.win.destroy()
            self.pets.clear()
            self.area = area
        settings = pet_settings()
        if found is not None:
            found = [info for info in found if settings["selected"] is None or info["name"] in settings["selected"]]
            dpi = dpi_of(hwnd)
            set_scale(dpi * max((settings["sizes"].get(info["name"], settings["size"])
                                for info in found), default=settings["size"]) / 100)
            cell = (W, H)
            for i, info in enumerate(found):
                name = info["name"]
                scale = dpi * settings["sizes"].get(name, settings["size"]) / 100
                if name in self.pets and abs(self.pets[name].scale - scale) > 0.01:
                    self.save_places()
                    self.pets.pop(name).win.destroy()
                if info["name"] in self.pets:
                    self.pets[info["name"]].update(info)
                else:
                    set_scale(scale)
                    place = place_on_monitor(self.places.get(name), area, i, cell)
                    self.pets[name] = Pet(self, info, place, scale)
            for name in set(self.pets) - {p["name"] for p in found}:
                self.pets.pop(name).win.destroy()
        self.root.after(1000, self.poll)

    def animate(self):
        now = time.time()
        for pet in self.pets.values():
            pet.draw(now)
        self.root.after(1000 // FPS, self.animate)


if __name__ == "__main__":
    if "--settings" in sys.argv:
        settings_lock = socket.socket()
        try:
            settings_lock.bind(("127.0.0.1", PORT + 1))
        except OSError:
            user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            user32.FindWindowW.restype = wintypes.HWND
            hwnd = user32.FindWindowW(None, "Desktop pets")
            if hwnd:
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
            sys.exit(0)
        settings_dialog()
        sys.exit(0)
    if OFF.exists():
        sys.exit(0)  # turned off (Hide pets or Ctrl+Alt+P)
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", PORT))
    except OSError:
        sys.exit(0)  # pets already running
    App().root.mainloop()
