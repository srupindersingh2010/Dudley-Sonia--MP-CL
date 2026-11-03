"""Shared helpers for the daily fetch: HTTP, JSON storage, keep-last-good logic."""
import json, re, time, traceback
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
CONFIG = json.loads((ROOT / "config" / "site.json").read_text(encoding="utf-8"))

UK = ZoneInfo("Europe/London")
NOW_UTC = datetime.now(timezone.utc)
NOW_UK = NOW_UTC.astimezone(UK)
TODAY = NOW_UK.date()

UA = ("Mozilla/5.0 (compatible; DudleyMPInfoBot/1.0; "
      "+https://github.com/" + CONFIG["site"]["repo"] + ")")
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"})


def uk_display(dt=None):
    dt = dt or NOW_UK
    return dt.astimezone(UK).strftime("%-d %B %Y, %H:%M")


def get(url, params=None, timeout=30, accept="application/json", tries=3, browser_ua=False):
    """GET with retries. Returns a Response (status 200) or raises."""
    headers = {"Accept": accept}
    if browser_ua:
        headers["User-Agent"] = BROWSER_UA
    last = None
    for attempt in range(tries):
        try:
            r = SESSION.get(url, params=params, headers=headers, timeout=timeout)
            print(f"    GET {r.url[:110]} -> {r.status_code}")
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code in (404, 400, 401, 403):
                break
        except Exception as e:  # network error
            last = f"{type(e).__name__}: {e}"
            print(f"    GET {url[:110]} -> {last}")
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url[:80]} failed: {last}")


def get_json(url, params=None, **kw):
    return get(url, params=params, **kw).json()


def load(name, default=None):
    p = DATA / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(name, obj):
    p = DATA / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
    return re.sub(r"\s+", " ", s).strip()


def iso_date(s):
    """'2026-10-30T00:00:00' -> '2026-10-30' (or '' )."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(s or ""))
    return m.group(1) if m else ""


STATUS = []


def run_section(key, label, source, source_url, func, required=True):
    """
    Run one fetcher. On success write data/<key>.json with status 'ok'.
    On failure keep the previous good file (status 'stale') so the site never
    shows a blank section; if there is no previous file, write 'pending'.
    """
    print(f"\n== {label} ==")
    fname = f"{key}.json"
    prev = load(fname)
    started = time.time()
    try:
        payload = func()
        if payload is None:
            raise RuntimeError("no data returned")
        out = {
            "key": key, "label": label, "source": source, "sourceUrl": source_url,
            "status": payload.pop("_status", "ok"),
            "retrieved": NOW_UTC.isoformat(), "retrievedDisplay": uk_display(),
            "lastAttempt": NOW_UTC.isoformat(),
        }
        out.update(payload)
        save(fname, out)
        print(f"  OK in {time.time() - started:.1f}s")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:300]
        print(f"  FAILED: {err}")
        traceback.print_exc()
        if prev and prev.get("status") in ("ok", "stale", "not-configured"):
            prev["status"] = "stale" if prev.get("status") != "not-configured" else "not-configured"
            prev["lastAttempt"] = NOW_UTC.isoformat()
            prev["lastError"] = err
            out = prev
        else:
            out = {"key": key, "label": label, "source": source, "sourceUrl": source_url,
                   "status": "pending", "retrieved": None, "retrievedDisplay": None,
                   "lastAttempt": NOW_UTC.isoformat(), "lastError": err, "items": []}
        save(fname, out)
    STATUS.append({"key": key, "label": label, "status": out["status"],
                   "retrievedDisplay": out.get("retrievedDisplay"),
                   "error": out.get("lastError") if out["status"] != "ok" else None})
    return out
