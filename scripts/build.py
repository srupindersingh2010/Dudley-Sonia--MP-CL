"""Render index.html and privacy.html from templates + data/*.json."""
import json
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UK = ZoneInfo("Europe/London")


def load(name, default=None):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def section(key):
    d = load(f"{key}.json", None)
    if not d:
        d = {"status": "pending", "items": []}
    d.setdefault("items", [])
    return d


def nice_date(s, fmt="%-d %b %Y"):
    try:
        return date.fromisoformat(str(s)[:10]).strftime(fmt)
    except Exception:
        return s or ""


def nice_dt(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(UK)
        return dt.strftime("%a %-d %b, %-I:%M%p").replace("AM", "am").replace("PM", "pm")
    except Exception:
        return s or ""


def build():
    cfg = json.loads((ROOT / "config" / "site.json").read_text(encoding="utf-8"))
    content = json.loads((ROOT / "config" / "content.json").read_text(encoding="utf-8"))
    keys = ["profile", "whatson", "votes", "speeches", "questions", "edms", "bills", "interests",
            "petitions", "council", "wmca", "police", "police_news", "stats", "news", "diary", "gallery"]
    d = {k: section(k) for k in keys}
    status = load("status.json", {})
    photo = ROOT / cfg["mp"]["photo"]
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                      autoescape=select_autoescape(["html", "j2"]), trim_blocks=True, lstrip_blocks=True)
    env.filters["nicedate"] = nice_date
    env.filters["nicedt"] = nice_dt
    env.filters["num"] = lambda n: f"{n:,}" if isinstance(n, (int, float)) else (n or "")
    ctx = dict(cfg=cfg, c=content, d=d, status=status, has_photo=photo.exists(),
               built=datetime.now(UK).strftime("%-d %B %Y, %H:%M"),
               today=datetime.now(UK).date().isoformat())
    for tpl, out in [("index.html.j2", "index.html"), ("privacy.html.j2", "privacy.html")]:
        html = env.get_template(tpl).render(**ctx)
        (ROOT / out).write_text(html, encoding="utf-8")
        print(f"Built {out} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    build()
