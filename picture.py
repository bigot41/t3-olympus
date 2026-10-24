"""A picture or DXF drawing, served as a page the T3 browser pane can mark up.

The pane's pen only exists on a web page. A render is wrapped in a small page.
A DXF is drawn to SVG first. The file on disk is left as it is.
"""
import os, secrets, time
import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, layout, svg

IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".svg", ".ico"}
DRAWINGS = {".dxf"}
MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".gif": "image/gif", ".avif": "image/avif", ".svg": "image/svg+xml", ".ico": "image/x-icon",
}
MAX_BYTES = 80 * 1024 * 1024
TTL = 30 * 60
pages = {}  # token -> (expires, kind, path, svg or None)


def locate(root, raw):
    """The file inside root named by the breadcrumb path, or raise ValueError."""
    root = os.path.realpath(root)
    text = (raw or "").replace("\\", "/").strip()
    if text.startswith("/") or (len(text) >= 2 and text[1] == ":"):
        full = os.path.realpath(text)
        try:
            inside = os.path.commonpath([os.path.normcase(root), os.path.normcase(full)]) == os.path.normcase(root)
        except ValueError:
            inside = False
        if not inside:
            raise ValueError("Choose a file in this project.")
        text = os.path.relpath(full, root).replace("\\", "/")
    if not text or text.startswith("/") or ":" in text.split("/")[0]:
        raise ValueError("Choose a file in this project.")
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("Choose a file in this project.")
    base = os.path.basename(root.rstrip("\\/"))
    options = ["/".join(parts)]
    if parts and parts[0].lower() == base.lower():
        options.append("/".join(parts[1:]))
    for rel in options:
        if not rel:
            continue
        full = os.path.realpath(os.path.join(root, *rel.split("/")))
        try:
            inside = os.path.commonpath([os.path.normcase(root), os.path.normcase(full)]) == os.path.normcase(root)
        except ValueError:
            inside = False
        if not inside or not os.path.isfile(full):
            continue
        ext = os.path.splitext(full)[1].lower()
        if ext not in IMAGES and ext not in DRAWINGS:
            raise ValueError("This pane can open a picture or a DXF drawing.")
        if os.path.getsize(full) > MAX_BYTES:
            raise ValueError("That file is too large to open here.")
        return ("drawing" if ext in DRAWINGS else "image", full)
    raise ValueError("That file isn't in this project.")


def dxf_svg(path):
    """An SVG drawing of a DXF model, or raise ValueError."""
    try:
        doc = ezdxf.readfile(path)
    except Exception:
        raise ValueError("This DXF couldn't be read.")
    layouts = [doc.modelspace()]
    layouts.extend(layout for layout in doc.layouts if layout.name != "Model")
    for space in layouts:
        backend = svg.SVGBackend()
        try:
            Frontend(RenderContext(doc), backend).draw_layout(space, finalize=True)
            box = backend.player().bbox()
            # a flat line has no area, and a zero-height page draws nothing
            if not box.has_data:
                continue
            span = max(box.size.x, box.size.y, 1.0)
            page = layout.Page(max(box.size.x, span * 0.02), max(box.size.y, span * 0.02))
            out = backend.get_string(page, xml_declaration=False)
        except Exception:
            continue
        start = out.find("<svg")
        if start >= 0 and any(tag in out for tag in ("<path", "<line", "<circle", "<polygon", "<polyline", "<text", "<ellipse")):
            return out[start:]
    raise ValueError("This DXF has nothing to draw.")


def mint(kind, path, drawing=None):
    token = secrets.token_urlsafe(24)
    pages[token] = (time.time() + TTL, kind, path, drawing)
    return token


def drop_expired():
    now = time.time()
    for token, (expires, *_) in list(pages.items()):
        if expires <= now:
            pages.pop(token, None)


def page(token):
    """(kind, path, svg) for a live token, or None."""
    drop_expired()
    row = pages.get(token)
    if not row:
        return None
    expires, kind, path, drawing = row
    pages[token] = (time.time() + TTL, kind, path, drawing)
    return kind, path, drawing


def html(token, kind, drawing):
    body = drawing if kind == "drawing" else f'<img alt="" src="/picture/{token}/file">'
    sheet = "background:#f7f6f3" if kind == "drawing" else "background:#111"
    return f"""<!doctype html>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'">
<style>
html, body {{ margin: 0; height: 100%; {sheet}; }}
body {{ display: flex; align-items: center; justify-content: center; }}
img, svg {{ max-width: 100%; max-height: 100%; }}
</style>
{body}
"""
