"""Local sources: council & WMCA meetings (ModernGov), policing (data.police.uk),
constituency profile (Nomis/ONS), local news RSS, office diary and gallery."""
import csv, io, json, os, re, time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from common import (CONFIG, DATA, NOW_UTC, NOW_UK, TODAY, UK, SESSION, BROWSER_UA,
                    get, get_json, load, save, strip_html, iso_date)


# ======================================================== ModernGov meetings
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
_DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?,?\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{4})", re.I)
_TIME_RE = re.compile(r"(\d{1,2}[.:]\d{2}\s*[ap]\.?m\.?)", re.I)


def _mg_fetch(url):
    try:
        r = get(url, accept="text/html", tries=2, browser_ua=True)
        if "ieListDocuments" in r.text or "mgCalendar" in r.text:
            return r.text
    except Exception:
        pass
    return ""


def _mg_parse(html, base, yr, mo):
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for a in soup.find_all("a", href=re.compile(r"ieListDocuments", re.I)):
        href, text = a.get("href", ""), a.get_text(" ", strip=True)
        title_att = a.get("title", "") or ""
        mdate = None
        dm = re.search(r"\bon\s+(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", text + " " + title_att)
        if dm:
            d, m = int(dm.group(1)), int(dm.group(2))
            y = int(dm.group(3)) if dm.group(3) else yr
            y = y + 2000 if y < 100 else y
            if not dm.group(3) and mo == 12 and m == 1:
                y += 1
            try:
                mdate = date(y, m, d)
            except ValueError:
                pass
        if not mdate:
            for prev in a.find_all_previous(string=_DATE_RE, limit=1):
                hm = _DATE_RE.search(prev)
                try:
                    mdate = date(int(hm.group(3)), _MONTHS[hm.group(2).lower()], int(hm.group(1)))
                except Exception:
                    pass
        if not mdate:
            continue
        tm = _TIME_RE.search(text) or _TIME_RE.search(title_att)
        title = re.sub(r"^(PROVISIONAL\s*-\s*|Meeting of\s*)", "", text or title_att, flags=re.I)
        title = re.sub(r",?\s*\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4}.*$", "", title)
        title = re.sub(r"\s*\bon\s+\d{1,2}/\d{1,2}.*$", "", title).strip(" -,")
        if not title:
            continue
        mid = re.search(r"MId=(\d+)", href, re.I)
        found.append({"date": mdate.isoformat(), "dateDisplay": mdate.strftime("%a %-d %b"),
                      "time": re.sub(r"\s+", " ", tm.group(1)) if tm else "",
                      "title": title, "url": urljoin(base + "/", href),
                      "key": mid.group(1) if mid else f"{mdate}{title}"})
    return found


def _months():
    y, m = TODAY.year, TODAY.month
    return [(y, m), (y + 1, 1) if m == 12 else (y, m + 1)]


def _discover_moderngov(page_url):
    """Find a ModernGov base URL linked from the council's meetings page."""
    try:
        html = get(page_url, accept="text/html", tries=2, browser_ua=True).text
    except Exception as e:
        print("   discover:", e)
        return []
    bases = []
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        h = a["href"]
        if re.search(r"(mgCalendar|ieListDocuments|mgCommittee|ieDocHome|mgListCommittees)", h, re.I):
            u = urlparse(urljoin(page_url, h))
            path = u.path.rsplit("/", 1)[0]
            bases.append(f"{u.scheme}://{u.netloc}{path}")
    print("   discovered:", bases[:3])
    return list(dict.fromkeys(bases))


def _moderngov(candidates, days=30):
    cutoff = TODAY + timedelta(days=days)
    for base in candidates:
        base = base.rstrip("/")
        meetings, seen, ok = [], set(), False
        for yr, mo in _months():
            for url in [f"{base}/mgCalendarAgendaView.aspx?M={mo}&DD={yr}&CID=0&OT=&C=-1&MR=1",
                        f"{base}/mgCalendarMonthView.aspx?M={mo}&DD={yr}&CID=0&OT=&C=-1&MR=0&GL=1"]:
                html = _mg_fetch(url)
                if not html:
                    continue
                ok = True
                items = _mg_parse(html, base, yr, mo)
                for it in items:
                    if TODAY.isoformat() <= it["date"] <= cutoff.isoformat() and it["key"] not in seen:
                        seen.add(it["key"])
                        meetings.append(it)
                if items:
                    break
        if ok:
            meetings.sort(key=lambda m: (m["date"], m["time"]))
            return base, meetings
    raise RuntimeError("no ModernGov calendar reachable at: " + ", ".join(candidates))


CMIS_APPT = re.compile(r'\\?"id\\?":(\d+),\\?"visible\\?":true,\\?"subject\\?":\\?"([^"\\]*)\\?".*?\\?"start\\?":\\?"(\d{4}/\d{2}/\d{2}) (\d{2}:\d{2})', re.S)


def _cmis_parse(html, base):
    out = {}
    for mid, subject, d, t in CMIS_APPT.findall(html):
        subject = subject.replace("\\u0026", "&").replace("&amp;", "&")
        title = re.sub(r"^\d{1,2}:\d{2}\s*", "", subject)
        title, _, room = title.partition(" : ")
        day = date.fromisoformat(d.replace("/", "-"))
        out[mid] = {"date": day.isoformat(), "dateDisplay": day.strftime("%a %-d %b"),
                    "time": datetime.strptime(t, "%H:%M").strftime("%-I.%M%p").lower(),
                    "title": title.strip(), "location": room.strip(),
                    "url": f"{base}/Meetings.aspx", "key": mid}
    return out


def _cmis(base, days=30):
    """Dudley uses CMIS (Telerik scheduler). The month's meetings are embedded
    as JSON in the page; the next month needs a click, so use a real browser
    when available and fall back to plain HTTP (current month only)."""
    found = {}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = b.new_context(user_agent=BROWSER_UA, locale="en-GB").new_page()
            pg.goto(f"{base}/Meetings.aspx", wait_until="networkidle", timeout=60000)
            found.update(_cmis_parse(pg.content(), base))
            nxt = pg.locator(".rsNextDay, .rsArrowRight, a[title*='Next']").first
            if nxt.count():
                nxt.click()
                pg.wait_for_timeout(4000)
                found.update(_cmis_parse(pg.content(), base))
            b.close()
        print(f"    CMIS via browser: {len(found)} meetings")
    except Exception as e:
        print("    CMIS browser:", e)
    if not found:
        found = _cmis_parse(get(f"{base}/Meetings.aspx", accept="text/html", browser_ua=True).text, base)
        print(f"    CMIS via HTTP: {len(found)} meetings")
    if not found:
        raise RuntimeError("CMIS calendar returned no meetings")
    cutoff = (TODAY + timedelta(days=days)).isoformat()
    return sorted([m for m in found.values() if TODAY.isoformat() <= m["date"] <= cutoff],
                  key=lambda m: (m["date"], m["time"]))


def fetch_council_meetings():
    c = CONFIG["council"]
    if c.get("cmisBase"):
        items = _cmis(c["cmisBase"].rstrip("/"))
        return {"items": items, "system": "CMIS", "calendarUrl": c["cmisBase"].rstrip("/") + "/Meetings.aspx",
                "note": "" if items else "No meetings are listed for the next 30 days."}
    cands = _discover_moderngov(c["meetingsPage"]) + c["moderngovCandidates"]
    base, items = _moderngov(list(dict.fromkeys(cands)))
    return {"items": items, "system": base, "calendarUrl": base + "/mgCalendarMonthView.aspx",
            "note": "" if items else "No meetings are listed for the next 30 days."}


def fetch_wmca_meetings():
    base, items = _moderngov(CONFIG["combinedAuthority"]["moderngovCandidates"])
    return {"items": items, "system": base, "calendarUrl": base + "/mgCalendarMonthView.aspx",
            "note": "" if items else "No WMCA meetings are listed for the next 30 days."}


# ===================================================================== Police
PAPI = "https://data.police.uk/api"
CAT = {"anti-social-behaviour": "Anti-social behaviour", "bicycle-theft": "Bicycle theft",
       "burglary": "Burglary", "criminal-damage-arson": "Criminal damage & arson",
       "drugs": "Drugs", "other-theft": "Other theft", "possession-of-weapons": "Possession of weapons",
       "public-order": "Public order", "robbery": "Robbery", "shoplifting": "Shoplifting",
       "theft-from-the-person": "Theft from the person", "vehicle-crime": "Vehicle crime",
       "violent-crime": "Violence & sexual offences", "other-crime": "Other crime"}


def _browser_json(url, post=None):
    """Fallback: fetch JSON from inside headless Chromium (some CDNs block datacentre IPs)."""
    try:
        from playwright.sync_api import sync_playwright
        from urllib.parse import urlencode
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = b.new_context(user_agent=BROWSER_UA, locale="en-GB").new_page()
            pg.goto(f"{PAPI}/forces", wait_until="domcontentloaded", timeout=30000)
            res = pg.evaluate("""async ([u, body]) => { const r = await fetch(u, body ?
                {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body} : {});
                return {s: r.status, t: await r.text()}; }""", [url, urlencode(post) if post else None])
            b.close()
        if res["s"] == 200:
            return json.loads(res["t"])
    except Exception as e:
        print("    browser fallback:", e)
    return None


def papi(path, params=None):
    url = f"{PAPI}/{path}"
    try:
        return get_json(url, params=params, tries=2)
    except Exception as e:
        print("    police API:", e)
        if params:
            from urllib.parse import urlencode
            url += "?" + urlencode(params)
        return _browser_json(url)


def _crimes(poly, month):
    url = f"{PAPI}/crimes-street/all-crime"
    try:
        r = SESSION.post(url, data={"poly": poly, "date": month}, timeout=60)
        print(f"    POST crimes {month} -> {r.status_code}")
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print("    POST crimes:", e)
    return _browser_json(url, {"poly": poly, "date": month})


def _prev_month(ym):
    y, m = int(ym[:4]), int(ym[5:7]) - 1
    return f"{y - 1}-12" if m == 0 else f"{y}-{m:02d}"


def fetch_police():
    pc = CONFIG["police"]
    nbhs = {}
    for pt in pc["samplePoints"]:
        loc = papi("locate-neighbourhood", {"q": f"{pt['lat']},{pt['lng']}"})
        if isinstance(loc, dict) and loc.get("neighbourhood"):
            nbhs.setdefault(loc["neighbourhood"], {"id": loc["neighbourhood"], "force": loc["force"],
                                                   "places": []})["places"].append(pt["name"])
        time.sleep(0.15)
    if not nbhs:
        raise RuntimeError("could not resolve any neighbourhoods")
    last = papi("crime-last-updated") or {}
    month = str(last.get("date", ""))[:7] or (NOW_UTC - timedelta(days=62)).strftime("%Y-%m")
    months = [month]
    for _ in range(5):
        months.append(_prev_month(months[-1]))
    teams, map_points, boundaries = [], [], []
    trend = {m: 0 for m in months}
    latest_counts = {}
    for nid, n in nbhs.items():
        path = f"{n['force']}/{nid}"
        info = papi(path) or {}
        people = papi(f"{path}/people") or []
        pris = papi(f"{path}/priorities") or []
        events = papi(f"{path}/events") or []
        bnd = papi(f"{path}/boundary") or []
        pts = [[float(b["latitude"]), float(b["longitude"])] for b in bnd if b.get("latitude")]
        step = max(1, len(pts) // 120)
        boundaries.append({"name": info.get("name") or nid, "points": pts[::step]})
        poly = ":".join(f"{a:.5f},{b:.5f}" for a, b in pts[::max(1, len(pts) // 400)])
        n_latest = 0
        for m in months:
            crimes = _crimes(poly, m) if poly else None
            if crimes is None:
                continue
            trend[m] += len(crimes)
            if m == month:
                n_latest = len(crimes)
                for c in crimes:
                    cat = c.get("category", "other-crime")
                    latest_counts[cat] = latest_counts.get(cat, 0) + 1
                    loc = c.get("location") or {}
                    try:
                        map_points.append([round(float(loc["latitude"]), 5), round(float(loc["longitude"]), 5), cat])
                    except Exception:
                        pass
            time.sleep(0.2)
        contact = info.get("contact_details") or {}
        teams.append({
            "id": nid, "name": info.get("name") or nid, "places": n["places"],
            "url": info.get("url_force") or f"https://www.police.uk/pu/your-area/west-midlands-police/",
            "email": contact.get("email"), "phone": contact.get("telephone") or "101",
            "officers": [{"name": strip_html(p.get("name")), "rank": p.get("rank")} for p in people][:12],
            "priorities": [{"issue": strip_html(p.get("issue")), "action": strip_html(p.get("action")),
                            "date": iso_date(p.get("issue-date"))} for p in pris if p.get("issue")][:5],
            "events": [{"title": strip_html(e.get("title")), "start": e.get("start_date"),
                        "address": strip_html(e.get("address"))} for e in events
                       if str(e.get("start_date", ""))[:10] >= TODAY.isoformat()][:6],
            "crimesLatest": n_latest,
        })
    md = lambda ym: datetime.strptime(ym, "%Y-%m").strftime("%B %Y")
    cats = [{"category": CAT.get(k, k), "slug": k, "count": v}
            for k, v in sorted(latest_counts.items(), key=lambda kv: -kv[1])]
    save("police_map.json", {"month": md(month), "boundaries": boundaries,
                             "points": map_points, "categories": CAT})
    return {"month": month, "monthDisplay": md(month), "total": sum(latest_counts.values()),
            "categories": cats,
            "trend": [{"month": md(m), "count": trend[m]} for m in reversed(months)],
            "teams": teams,
            "note": "Crime figures are for the police neighbourhoods that cover the Dudley constituency, "
                    "whose boundaries do not exactly match the constituency. Locations on the map are "
                    "approximate (snapped to nearby points to protect privacy). Data.police.uk publishes "
                    "monthly, usually about two months behind."}


def _rss(url, days=60):
    r = get(url, accept="application/rss+xml, application/xml, text/xml", tries=2, browser_ua=True)
    root = ET.fromstring(r.content)
    cutoff = NOW_UTC - timedelta(days=days)
    out = []
    for it in root.iter("item"):
        title = strip_html(it.findtext("title"))
        pub = it.findtext("pubDate") or ""
        try:
            dt = parsedate_to_datetime(pub)
            dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if dt < cutoff:
            continue
        src = (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        out.append({"title": title, "url": (it.findtext("link") or "").strip(),
                    "summary": strip_html(it.findtext("description"))[:240],
                    "publisher": src, "published": dt.isoformat(),
                    "publishedDisplay": dt.astimezone(UK).strftime("%-d %b %Y")})
    return out


def fetch_police_news():
    q = CONFIG["police"]["newsQuery"]
    from urllib.parse import quote
    items = _rss(f"https://news.google.com/rss/search?q={quote(q + ' when:21d')}&hl=en-GB&gl=GB&ceid=GB:en", 21)
    items.sort(key=lambda i: i["published"], reverse=True)
    return {"items": items[:10]}


# ============================================================ Local news
def fetch_news():
    terms = CONFIG["news"]["filterTerms"]
    items, errors, seen = [], [], set()
    for f in CONFIG["news"]["feeds"]:
        try:
            for it in _rss(f["url"]):
                hay = (it["title"] + " " + it["summary"]).lower()
                if f["filter"] and not any(t in hay for t in terms):
                    continue
                key = re.sub(r"\W+", "", it["title"].lower())[:60]
                if key in seen:
                    continue
                seen.add(key)
                it["feed"] = f["name"]
                it["publisher"] = it["publisher"] or f["name"]
                items.append(it)
        except Exception as e:
            errors.append(f"{f['name']}: {e}"[:120])
    if not items and len(errors) == len(CONFIG["news"]["feeds"]):
        raise RuntimeError("; ".join(errors))
    items.sort(key=lambda i: i["published"], reverse=True)
    return {"items": items[:15], "feedErrors": errors,
            "feeds": [{"name": f["name"]} for f in CONFIG["news"]["feeds"]]}


# ===================================================== Constituency profile
NOMIS = "https://www.nomisweb.co.uk/api/v01/dataset"


def _codes(js):
    cl = js["structure"]["codelists"]
    if not cl:
        return []
    cl = cl["codelist"]
    cl = cl[0] if isinstance(cl, list) else cl
    codes = cl.get("code") or []
    return codes if isinstance(codes, list) else [codes]


def _ann(code, title):
    for a in (code.get("annotations") or {}).get("annotation") or []:
        if a.get("annotationtitle") == title:
            return str(a.get("annotationtext"))
    return ""


_GEO = {}


def nomis_geos(ds):
    """Nomis needs its own numeric geography IDs: find the Dudley 2024 constituency and England."""
    if ds in _GEO:
        return _GEO[ds]
    ons = CONFIG["mp"]["onsCode"]
    types = _codes(get_json(f"{NOMIS}/{ds}/geography/TYPE.def.sdmx.json"))
    t = next((c["value"] for c in types if "july 2024" in c["description"]["value"].lower()
              and "westminster" in c["description"]["value"].lower()), None)
    if t is None:
        raise RuntimeError(f"{ds}: no 2024 constituency geography")
    local = next((c["value"] for c in _codes(get_json(f"{NOMIS}/{ds}/geography/{t if str(t).startswith('TYPE') else 'TYPE' + str(t)}.def.sdmx.json"))
                  if _ann(c, "GeogCode") == ons), None)
    if local is None:
        raise RuntimeError(f"{ds}: {ons} not found in TYPE{t}")
    eng = next((c["value"] for c in _codes(get_json(f"{NOMIS}/{ds}/geography.def.sdmx.json"))
                if _ann(c, "GeogCode") == "E92000001"), 2092957699)
    _GEO[ds] = (str(local), str(eng))
    print(f"    Nomis {ds}: Dudley={local} England={eng}")
    return _GEO[ds]


def _nomis_census(code, geos):
    """Return {category: {geo: percent}} for a Census 2021 TS table."""
    defs = get_json(f"{NOMIS}/def.sdmx.json", params={"search": f"*{code}*"})
    kfs = defs["structure"]["keyfamilies"]["keyfamily"]
    kfs = kfs if isinstance(kfs, list) else [kfs]
    ds = next(k["id"] for k in kfs if code.lower() in json.dumps(k.get("name", "")).lower())
    loc, eng = nomis_geos(ds)
    r = get(f"{NOMIS}/{ds}.data.csv", params={"geography": f"{loc},{eng}", "measures": "20301"},
            accept="text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    if not rows:
        raise RuntimeError(f"{code}: no rows")
    skip = {"GEOGRAPHY_NAME", "DATE_NAME", "MEASURES_NAME", "OBS_STATUS_NAME", "RECORD_OFFSET",
            "RECORD_COUNT", "OBS_CONF_NAME", "URBAN_RURAL_NAME"}
    dim = max((c for c in rows[0] if c.endswith("_NAME") and c not in skip),
              key=lambda c: len({r[c] for r in rows}))
    out = {}
    for row in rows:
        try:
            g = geos[0] if (row.get("GEOGRAPHY") == loc or row.get("GEOGRAPHY_CODE") == geos[0]) else geos[1]
            out.setdefault(row[dim], {})[g] = round(float(row["OBS_VALUE"]), 1)
        except Exception:
            pass
    return ds, out


def fetch_profile_stats():
    ons = CONFIG["mp"]["onsCode"]
    geos = [ons, "E92000001"]
    stats, notes = [], []
    # Claimant count (monthly)
    try:
        loc, eng = nomis_geos("NM_162_1")
        r = get(f"{NOMIS}/NM_162_1.data.csv", params={
            "geography": f"{loc},{eng}", "date": "latest", "gender": "0", "age": "0",
            "measure": "1,2", "measures": "20100"}, accept="text/csv")
        rows = list(csv.DictReader(io.StringIO(r.text)))
        val = {(ons if (x.get("GEOGRAPHY") == loc or x.get("GEOGRAPHY_CODE") == ons) else "E92000001", x["MEASURE_NAME"]): x["OBS_VALUE"] for x in rows}
        cnt = next((v for (g, m), v in val.items() if g == ons and "count" in m.lower()), None)
        rate = next((v for (g, m), v in val.items() if g == ons and "residents" in m.lower()), None)
        eng = next((v for (g, m), v in val.items() if g == "E92000001" and "residents" in m.lower()), None)
        if cnt:
            stats.append({"group": "Work & benefits", "label": "People claiming unemployment-related benefits",
                          "value": f"{int(float(cnt)):,}", "detail": f"{rate}% of residents aged 16–64 (England {eng}%)"
                          if rate else "", "period": rows[0].get("DATE_NAME"),
                          "source": "ONS Claimant Count via Nomis", "url": "https://www.nomisweb.co.uk/sources/cc"})
    except Exception as e:
        notes.append(f"Claimant count: {e}"[:150])
    tables = [
        ("TS001", "People", "Usual residents (Census 2021)", None),
        ("TS037", "Health", "General health (Census 2021)", ["Very good health", "Good health", "Bad health", "Very bad health"]),
        ("TS054", "Housing", "Housing tenure (Census 2021)", None),
        ("TS066", "Work & benefits", "Economic activity, residents 16+ (Census 2021)", None),
    ]
    charts = []
    for code, group, label, keep in tables:
        try:
            ds, data = _nomis_census(code, geos)
            if code == "TS001":
                r = get(f"{NOMIS}/{ds}.data.csv", params={"geography": nomis_geos(ds)[0], "measures": "20100"}, accept="text/csv")
                rows = list(csv.DictReader(io.StringIO(r.text)))
                tot = max(float(x["OBS_VALUE"]) for x in rows)
                stats.append({"group": group, "label": "Population (Census 2021)", "value": f"{int(tot):,}",
                              "detail": "usual residents", "period": "March 2021",
                              "source": "ONS Census 2021 via Nomis", "url": "https://www.nomisweb.co.uk/sources/census_2021"})
                continue
            bars = []
            for cat, g in data.items():
                if cat.lower().startswith("total") or ons not in g:
                    continue
                if keep and not any(k.lower() == cat.lower() for k in keep):
                    continue
                bars.append({"label": cat, "local": g.get(ons), "england": g.get("E92000001")})
            bars = sorted(bars, key=lambda b: -(b["local"] or 0))[:7]
            if bars:
                charts.append({"group": group, "title": label, "bars": bars, "dataset": ds,
                               "source": "ONS Census 2021 via Nomis"})
        except Exception as e:
            notes.append(f"{code}: {e}"[:150])
    if not stats and not charts:
        raise RuntimeError("; ".join(notes))
    return {"stats": stats, "charts": charts, "notes": notes,
            "libraryUrl": "https://commonslibrary.parliament.uk/constituency-dashboards/"}


# ============================================================= Office diary
def _parse_dt(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UK)
    return datetime(v.year, v.month, v.day, tzinfo=UK)


def _category(title, cats=""):
    t = f"{title} {cats}".lower()
    for k, lab in [("surgery", "Surgery"), ("coffee", "Coffee morning"), ("visit", "Visit"),
                   ("meeting", "Public meeting"), ("event", "Event")]:
        if k in t:
            return lab
    return "Event"


def _event(title, start, end, loc, desc, all_day, cats="", booking=""):
    m = re.match(r"\s*\[([^\]]+)\]\s*(.*)", title or "")
    cat = m.group(1).strip().capitalize() if m else _category(title, cats)
    title = m.group(2) if m else title
    return {"title": (title or "Event").strip(), "category": cat,
            "start": start.isoformat(), "end": end.isoformat() if end else None,
            "date": start.date().isoformat(),
            "dateDisplay": start.strftime("%a %-d %b %Y"),
            "time": "" if all_day else start.strftime("%-I:%M%p").lower() + (
                "–" + end.strftime("%-I:%M%p").lower() if end else ""),
            "location": (loc or "").strip(), "description": strip_html(desc)[:400],
            "booking": booking}


def fetch_diary():
    ics_url = os.environ.get(CONFIG["diary"]["icsSecret"], "").strip()
    sheet_url = os.environ.get(CONFIG["diary"]["sheetSecret"], "").strip()
    events, sources = [], []
    window_start, window_end = TODAY - timedelta(days=120), TODAY + timedelta(days=30)
    if ics_url:
        import icalendar, recurring_ical_events
        cal = icalendar.Calendar.from_ical(get(ics_url, accept="text/calendar").content)
        for ev in recurring_ical_events.of(cal).between(window_start, window_end + timedelta(days=1)):
            if str(ev.get("CLASS", "PUBLIC")).upper() in ("PRIVATE", "CONFIDENTIAL"):
                continue
            ds = ev.get("DTSTART").dt
            de = ev.get("DTEND").dt if ev.get("DTEND") else None
            all_day = not isinstance(ds, datetime)
            s = _parse_dt(ds).astimezone(UK)
            e = _parse_dt(de).astimezone(UK) if de else None
            events.append(_event(str(ev.get("SUMMARY", "")), s, e, str(ev.get("LOCATION", "")),
                                 str(ev.get("DESCRIPTION", "")), all_day, str(ev.get("CATEGORIES", "") or "")))
        sources.append("Google Calendar")
    if sheet_url:
        rows = csv.DictReader(io.StringIO(get(sheet_url, accept="text/csv").text))
        for row in rows:
            r = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if r.get("public", "yes").lower() in ("no", "n", "false"):
                continue
            try:
                d = datetime.strptime(r.get("date", ""), "%d/%m/%Y").date() if "/" in r.get("date", "") \
                    else date.fromisoformat(r.get("date", ""))
            except Exception:
                continue
            def t(x):
                m = re.match(r"(\d{1,2})[:.](\d{2})", x or "")
                return (int(m.group(1)), int(m.group(2))) if m else None
            st, en = t(r.get("start")), t(r.get("end"))
            s = datetime(d.year, d.month, d.day, *(st or (0, 0)), tzinfo=UK)
            e = datetime(d.year, d.month, d.day, *en, tzinfo=UK) if en else None
            title = r.get("title", "")
            if r.get("type"):
                title = f"[{r['type']}] {title}"
            events.append(_event(title, s, e, r.get("location"), r.get("description"), not st,
                                 booking=r.get("booking", "")))
        sources.append("Google Sheet")
    manual = load("manual/diary.json", {}) or {}
    for m in manual.get("events", []):
        try:
            s = datetime.fromisoformat(m["start"]).replace(tzinfo=UK)
            e = datetime.fromisoformat(m["end"]).replace(tzinfo=UK) if m.get("end") else None
            events.append(_event(m.get("title", ""), s, e, m.get("location"), m.get("description"),
                                 len(m["start"]) == 10, booking=m.get("booking", "")))
            if "manual file" not in sources:
                sources.append("manual file")
        except Exception as ex:
            print("   manual diary entry skipped:", ex)
    upcoming = sorted([e for e in events if window_end.isoformat() >= e["date"] >= TODAY.isoformat()],
                      key=lambda e: e["start"])
    # Past archive: merge with existing archive so events are never lost
    arch = {a["start"] + a["title"]: a for a in (load("diary_archive.json", {}) or {}).get("items", [])}
    for e in events:
        if e["date"] < TODAY.isoformat():
            arch[e["start"] + e["title"]] = e
    past = sorted(arch.values(), key=lambda e: e["start"], reverse=True)[:300]
    save("diary_archive.json", {"items": past})
    status = "ok" if sources else "not-configured"
    return {"_status": status, "items": upcoming, "past": past[:40], "sources": sources,
            "note": "" if sources else "The office diary has not been connected yet."}


# ================================================================== Gallery
def fetch_gallery():
    items = list((load("manual/gallery.json", {}) or {}).get("photos", []))
    url = os.environ.get(CONFIG["gallery"]["sheetSecret"], "").strip()
    if url:
        for row in csv.DictReader(io.StringIO(get(url, accept="text/csv").text)):
            r = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if r.get("image") and r.get("alt"):
                items.append({"src": r["image"], "alt": r["alt"], "caption": r.get("caption", ""),
                              "date": r.get("date", ""), "credit": r.get("credit", "")})
    # Any photo dropped into assets/gallery/ is picked up automatically; the file
    # name becomes the alt text/caption unless gallery.json describes it.
    known = {i.get("src") for i in items}
    gdir = DATA.parent / "assets" / "gallery"
    if gdir.exists():
        for f in sorted(gdir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
            if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            src = f"assets/gallery/{f.name}"
            if src in known:
                continue
            words = re.sub(r"[-_]+", " ", f.stem).strip()
            items.append({"src": src, "alt": words.capitalize(), "caption": words.capitalize(), "date": "", "credit": ""})
    items = [i for i in items if i.get("src") and i.get("alt")]
    return {"_status": "ok" if items else "not-configured", "items": items[:24]}
