"""
Daily data update for the Dudley MP information site.

Run by GitHub Actions every day at 07:00 UK time (also runnable by hand:
`python scripts/fetch_all.py && python scripts/build.py`).

Every section is fetched independently. If a source fails, the previous good
data is kept and marked 'stale' with its original retrieval date, so one broken
feed never blanks a section or stops the rest of the update.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common import CONFIG, STATUS, NOW_UTC, save, uk_display, run_section  # noqa: E402
import parliament as P  # noqa: E402
import local as L  # noqa: E402

MID = CONFIG["mp"]["memberId"]
S = [
    ("profile", "MP profile & roles", "UK Parliament Members API",
     f"https://members.parliament.uk/member/{MID}", P.fetch_profile),
    ("whatson", "In Parliament this week", "UK Parliament What's On",
     "https://whatson.parliament.uk/commons/", P.fetch_whatson),
    ("votes", "Votes", "Commons Votes API", f"https://members.parliament.uk/member/{MID}/voting", P.fetch_votes),
    ("speeches", "Speeches", "Hansard API",
     f"https://hansard.parliament.uk/search/MemberContributions?memberId={MID}", P.fetch_speeches),
    ("questions", "Written questions", "Written Questions API",
     f"https://questions-statements.parliament.uk/written-questions?AskingMemberId={MID}", P.fetch_questions),
    ("edms", "Early Day Motions", "Early Day Motions API",
     f"https://edm.parliament.uk/member/{MID}", P.fetch_edms),
    ("bills", "Bills", "Bills API", f"https://bills.parliament.uk/?SearchTerm=&Member={MID}", P.fetch_bills),
    ("interests", "Register of Members' Financial Interests", "Register of Interests API",
     f"https://members.parliament.uk/member/{MID}/registeredinterests", P.fetch_interests),
    ("petitions", "Petitions", "UK Parliament Petitions", "https://petition.parliament.uk/petitions",
     P.fetch_petitions),
    ("council", "Dudley Council meetings", "Dudley Council committee calendar",
     CONFIG["council"]["meetingsPage"], L.fetch_council_meetings),
    ("wmca", "WMCA meetings", "WMCA governance calendar",
     "https://governance.wmca.org.uk/mgCalendarMonthView.aspx", L.fetch_wmca_meetings),
    ("police", "Policing & safety", "data.police.uk (Home Office open data)",
     "https://www.police.uk/pu/your-area/west-midlands-police/", L.fetch_police),
    ("police_news", "Police news", "Google News search", "https://news.google.com/", L.fetch_police_news),
    ("stats", "Constituency profile", "ONS via Nomis", "https://www.nomisweb.co.uk/", L.fetch_profile_stats),
    ("news", "Local news", "RSS feeds (see list)", "https://news.google.com/", L.fetch_news),
    ("diary", "Meetings & events diary", "MP's office diary", "", L.fetch_diary),
    ("gallery", "Photo gallery", "Supplied by the MP's office", "", L.fetch_gallery),
]

if __name__ == "__main__":
    only = set(sys.argv[1:])
    for key, label, source, url, fn in S:
        if only and key not in only:
            continue
        run_section(key, label, source, url, fn)
    save("status.json", {"updated": NOW_UTC.isoformat(), "updatedDisplay": uk_display(), "sections": STATUS})
    print("\nSummary:")
    for s in STATUS:
        print(f"  {s['status']:15} {s['label']}  {s['error'] or ''}")
    sys.exit(0)  # never fail the workflow because a feed is down
