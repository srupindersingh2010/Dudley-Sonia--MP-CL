"""UK Parliament data: Members, What's On, Votes, Hansard, Written Questions,
Early Day Motions, Bills, Register of Interests and Petitions."""
import time
from datetime import timedelta, date

from common import CONFIG, TODAY, NOW_UTC, get_json, strip_html, iso_date

MID = CONFIG["mp"]["memberId"]
ONS = CONFIG["mp"]["onsCode"]
MEMBERS = "https://members-api.parliament.uk/api"


def fmt(d):
    try:
        return date.fromisoformat(iso_date(d)).strftime("%-d %b %Y")
    except Exception:
        return ""


# ---------------------------------------------------------------- 1. Profile
def fetch_profile():
    m = get_json(f"{MEMBERS}/Members/{MID}")["value"]
    out = {
        "name": m.get("nameDisplayAs"),
        "party": (m.get("latestParty") or {}).get("name"),
        "constituency": (m.get("latestHouseMembership") or {}).get("membershipFrom"),
        "memberSince": iso_date((m.get("latestHouseMembership") or {}).get("membershipStartDate")),
        "memberSinceDisplay": fmt((m.get("latestHouseMembership") or {}).get("membershipStartDate")),
        "status": ((m.get("latestHouseMembership") or {}).get("membershipStatus") or {}).get("statusDescription"),
        "profileUrl": f"https://members.parliament.uk/member/{MID}",
    }
    try:
        out["synopsis"] = strip_html(get_json(f"{MEMBERS}/Members/{MID}/Synopsis").get("value"))
    except Exception as e:
        print("   synopsis:", e)
    try:
        er = get_json(f"{MEMBERS}/Members/{MID}/LatestElectionResult")["value"]
        cands = []
        for c in er.get("candidates") or []:
            cands.append({"name": c.get("name"),
                          "party": (c.get("party") or {}).get("name"),
                          "votes": c.get("votes"), "share": c.get("voteShare")})
        out["election"] = {
            "name": er.get("electionTitle"), "date": iso_date(er.get("electionDate")),
            "majority": er.get("majority"), "electorate": er.get("electorate"),
            "turnout": er.get("turnout"), "result": er.get("result"),
            "candidates": sorted(cands, key=lambda c: -(c.get("votes") or 0)),
        }
    except Exception as e:
        print("   election:", e)
    roles = []
    try:
        bio = get_json(f"{MEMBERS}/Members/{MID}/Biography")["value"]
        for kind, label in [("governmentPosts", "Government"), ("oppositionPosts", "Opposition"),
                            ("otherPosts", "Other role"), ("committeeMemberships", "Committee")]:
            for p in bio.get(kind) or []:
                if p.get("endDate"):
                    continue
                roles.append({"type": label, "name": p.get("name"),
                              "since": fmt(p.get("startDate"))})
        past = []
        for p in bio.get("committeeMemberships") or []:
            if p.get("endDate"):
                past.append({"name": p.get("name"), "from": fmt(p.get("startDate")),
                             "to": fmt(p.get("endDate"))})
        out["pastCommittees"] = past
    except Exception as e:
        print("   biography:", e)
    out["roles"] = roles
    try:
        contacts = get_json(f"{MEMBERS}/Members/{MID}/Contact").get("value") or []
        out["contacts"] = [{"type": c.get("type"), "line1": c.get("line1"), "line2": c.get("line2"),
                            "postcode": c.get("postcode"), "phone": c.get("phone"),
                            "email": c.get("email"), "web": c.get("line1") if c.get("isWebAddress") else None}
                           for c in contacts]
    except Exception as e:
        print("   contact:", e)
    return out


# ---------------------------------------------------------- 4. What's on
def fetch_whatson():
    start = TODAY
    end = TODAY + timedelta(days=7)
    raw = get_json("https://whatson-api.parliament.uk/calendar/events/list.json", params={
        "queryParameters.startDate": start.isoformat(),
        "queryParameters.endDate": end.isoformat(),
        "queryParameters.house": "Commons"})
    events = raw if isinstance(raw, list) else (raw.get("events") or raw.get("Events") or [])
    items = []
    for e in events:
        g = lambda *k: next((e.get(x) for x in k if e.get(x)), None)
        members = g("Members", "members") or []
        mine = any((mm.get("Id") or mm.get("id")) == MID for mm in members if isinstance(mm, dict))
        items.append({
            "date": iso_date(g("StartDate", "startDate")),
            "time": (g("StartTime", "startTime") or "")[:5],
            "category": g("Category", "category") or "",
            "type": g("Type", "type") or "",
            "title": strip_html(g("Description", "description") or g("Type", "type") or ""),
            "location": g("Location", "location") or "",
            "involvesMp": mine,
        })
    items = [i for i in items if i["date"]]
    items.sort(key=lambda i: (i["date"], i["time"]))
    days = {}
    for i in items:
        days.setdefault(i["date"], []).append(i)
    out_days = [{"date": d, "display": date.fromisoformat(d).strftime("%A %-d %B"),
                 "events": v[:25]} for d, v in sorted(days.items())]
    return {"days": out_days, "count": len(items),
            "note": "" if items else "No Commons business is listed for the next 7 days (the House may be in recess)."}


# ----------------------------------------------------------------- 5. Votes
def fetch_votes():
    base = "https://commonsvotes-api.parliament.uk/data/divisions.json"
    since = CONFIG["mp"]["elected"]
    records, skip = [], 0
    while skip < 3000:
        page = get_json(f"{base}/membervoting", params={
            "queryParameters.memberId": MID, "queryParameters.skip": skip,
            "queryParameters.take": 25})
        if not page:
            break
        records.extend(page)
        if len(page) < 25:
            break
        skip += 25
        time.sleep(0.2)
    total = get_json(f"{base}/searchTotalResults", params={"queryParameters.startDate": since})
    voted = [r for r in records if iso_date((r.get("PublishedDivision") or {}).get("Date")) >= since]
    recent = []
    for r in sorted(voted, key=lambda r: (r.get("PublishedDivision") or {}).get("Date") or "", reverse=True)[:25]:
        d = r.get("PublishedDivision") or {}
        recent.append({
            "id": d.get("DivisionId"), "number": d.get("Number"),
            "date": iso_date(d.get("Date")), "dateDisplay": fmt(d.get("Date")),
            "title": d.get("Title"), "ayes": d.get("AyeCount"), "noes": d.get("NoCount"),
            "vote": "Teller" if r.get("MemberWasTeller") else ("Aye" if r.get("MemberVotedAye") else "No"),
            "url": f"https://votes.parliament.uk/votes/commons/division/{d.get('DivisionId')}",
        })
    total = int(total) if str(total).isdigit() else None
    rate = round(100 * len(voted) / total) if total else None
    return {"items": recent, "votedCount": len(voted), "totalDivisions": total,
            "attendanceRate": rate, "since": since,
            "note": "Attendance = divisions in which the MP voted (or acted as teller) as a share of all Commons divisions since election. MPs may be absent for many reasons, including ministerial, committee or constituency duties, illness or pairing."}


# --------------------------------------------------------------- 6. Hansard
def fetch_speeches():
    raw = get_json("https://hansard-api.parliament.uk/search/contributions/Spoken.json", params={
        "queryParameters.memberId": MID, "queryParameters.take": 20,
        "queryParameters.orderBy": "SittingDateDesc"})
    items = []
    for c in raw.get("Results") or []:
        d = iso_date(c.get("SittingDate"))
        text = strip_html(c.get("ContributionTextFull") or c.get("ContributionText") or "")
        sect = c.get("DebateSectionExtId")
        url = (f"https://hansard.parliament.uk/{c.get('House') or 'Commons'}/{d}/debates/{sect}/"
               f"Debate#contribution-{c.get('ContributionExtId')}") if sect else \
              f"https://hansard.parliament.uk/search/MemberContributions?memberId={MID}"
        items.append({"date": d, "dateDisplay": fmt(d), "debate": c.get("DebateSection") or c.get("Section"),
                      "excerpt": (text[:280] + "…") if len(text) > 280 else text, "url": url})
    return {"items": items, "total": raw.get("TotalContributions") or raw.get("TotalResultCount"),
            "allUrl": f"https://hansard.parliament.uk/search/MemberContributions?memberId={MID}"}


# ------------------------------------------------------- 7. Written questions
def fetch_questions():
    raw = get_json("https://questions-statements-api.parliament.uk/api/writtenquestions/questions",
                   params={"askingMemberId": MID, "take": 20, "skip": 0})
    items = []
    for r in raw.get("results") or []:
        v = r.get("value") or {}
        tabled = iso_date(v.get("dateTabled"))
        ans = strip_html(v.get("answerText") or "")
        items.append({
            "uin": v.get("uin"), "heading": v.get("heading"),
            "department": v.get("answeringBodyName"),
            "question": strip_html(v.get("questionText"))[:400],
            "answer": (ans[:400] + "…") if len(ans) > 400 else ans,
            "tabled": tabled, "tabledDisplay": fmt(tabled),
            "answered": fmt(v.get("dateAnswered")),
            "url": f"https://questions-statements.parliament.uk/written-questions/detail/{tabled}/{v.get('uin')}",
        })
    items.sort(key=lambda i: i["tabled"], reverse=True)
    return {"items": items, "total": raw.get("totalResults")}


# ------------------------------------------------------------------ 8. EDMs
def fetch_edms():
    raw = get_json("https://oralquestionsandmotions-api.parliament.uk/EarlyDayMotions/list", params={
        "parameters.memberId": MID, "parameters.take": 25,
        "parameters.orderBy": "DateTabledDesc"})
    items = []
    for e in raw.get("Response") or []:
        sponsor = e.get("PrimarySponsor") or {}
        items.append({
            "id": e.get("Id"), "uin": e.get("UIN"), "title": e.get("Title"),
            "date": iso_date(e.get("DateTabled")), "dateDisplay": fmt(e.get("DateTabled")),
            "role": "Tabled" if sponsor.get("MnisId") == MID else "Signed",
            "sponsor": sponsor.get("Name"),
            "signatures": e.get("SponsorsCount") or e.get("SignaturesCount"),
            "url": f"https://edm.parliament.uk/early-day-motion/{e.get('Id')}",
        })
    total = (raw.get("PagingInfo") or {}).get("Total")
    return {"items": items, "total": total}


# ----------------------------------------------------------------- 9. Bills
def fetch_bills():
    raw = get_json("https://bills-api.parliament.uk/api/v1/Bills", params={
        "SponsorMemberId": MID, "SortOrder": "DateUpdatedDescending", "Take": 20})
    items = []
    for b in raw.get("items") or []:
        stage = b.get("currentStage") or {}
        items.append({"id": b.get("billId"), "title": b.get("shortTitle"),
                      "stage": stage.get("description"), "house": b.get("currentHouse"),
                      "updated": fmt(b.get("lastUpdate")),
                      "act": b.get("isAct"), "defeated": b.get("isDefeated"),
                      "url": f"https://bills.parliament.uk/bills/{b.get('billId')}"})
    return {"items": items, "total": raw.get("totalResults"),
            "note": "" if items else "Sonia Kumar is not currently listed as a sponsor of any bill."}


# ------------------------------------------------------------- 10. Interests
def fetch_interests():
    raw = get_json("https://interests-api.parliament.uk/api/v1/Interests",
                   params={"MemberId": MID, "Take": 100, "SortOrder": "PublishingDateDescending"})
    items = []
    for i in raw.get("items") or []:
        items.append({"category": (i.get("category") or {}).get("name"),
                      "summary": i.get("summary"),
                      "registered": fmt(i.get("registrationDate")),
                      "published": fmt(i.get("publishedDate")),
                      "url": f"https://interests-api.parliament.uk/api/v1/Interests/{i.get('id')}"})
    cats = {}
    for i in items:
        cats.setdefault(i["category"] or "Other", []).append(i)
    return {"items": items, "byCategory": [{"category": k, "items": v} for k, v in cats.items()],
            "total": raw.get("totalResults"),
            "registerUrl": f"https://members.parliament.uk/member/{MID}/registeredinterests"}


# ------------------------------------------------------------- 11. Petitions
def fetch_petitions():
    base = "https://petition.parliament.uk"
    open_list = []
    for page in range(1, 5):
        data = get_json(f"{base}/petitions.json", params={"state": "open", "page": page})
        rows = data.get("data") or []
        open_list.extend(rows)
        if len(rows) < 50:
            break
        time.sleep(0.3)
    open_list.sort(key=lambda p: -(p.get("attributes", {}).get("signature_count") or 0))
    ranked = []
    for p in open_list[:80]:
        try:
            det = get_json(f"{base}/petitions/{p['id']}.json")["data"]["attributes"]
        except Exception as e:
            print("   petition", p.get("id"), e)
            continue
        local = next((c for c in det.get("signatures_by_constituency") or []
                      if c.get("ons_code") == ONS), None)
        if not local:
            continue
        ranked.append({"id": p["id"], "title": det.get("action"),
                       "local": local.get("signature_count"),
                       "total": det.get("signature_count"),
                       "state": det.get("state"),
                       "response": bool(det.get("government_response")),
                       "debate": bool(det.get("debate")),
                       "url": f"{base}/petitions/{p['id']}"})
        time.sleep(0.15)
    ranked.sort(key=lambda r: -(r["local"] or 0))
    return {"items": ranked[:12], "checked": min(80, len(open_list)),
            "note": "Ranked by signatures from people who gave a postcode in the Dudley constituency. "
                    "Based on the 80 most-signed open petitions."}
