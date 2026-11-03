# Dudley MP information site – Sonia Kumar MP

An independent, automatically updated public information site about the MP for Dudley. It's modelled on the Lower Stoke ward site.

> **Status:** This is an independent prototype. It has **not** been agreed with or endorsed by Sonia Kumar MP or her office. The footer says so on every page.

- **Live site (once Pages is switched on):** https://srupindersingh2010.github.io/Dudley-Sonia--MP-CL/
- **Updates:** every day at 07:00 UK time (GitHub Actions → `.github/workflows/daily-update.yml`)
- **Hosting:** GitHub Pages, free. There are no servers, databases, cookies or forms.

---

## 1. Switch on GitHub Pages (one-off)

1. On GitHub, open the repo and go to **Settings → Pages**.
2. Under *Build and deployment*, choose **Source: Deploy from a branch**.
3. Pick **Branch: `main`** and folder **`/ (root)`**, then press **Save**.
4. After a minute or two, the site appears at the address above.

To fill the site with real data straight away, go to **Actions → Daily data update → Run workflow**.

**Custom domain (optional):** put the domain in *Settings → Pages → Custom domain* and point a DNS `CNAME` record at `srupindersingh2010.github.io`. Then update `site.baseUrl` in `config/site.json`.

---

## 2. What the MP's office does to add events to the diary

Pick **one** of these options. Both are free and take about 5 minutes to set up.

### Option A – Google Calendar (recommended)

1. In Google Calendar, create a new calendar called **"Sonia Kumar MP – public diary"**. Only put **public** events in it.
2. Go to **Settings → (this calendar) → Integrate calendar** and copy the **Secret address in iCal format** (it ends in `.ics`).
   - You don't need to make the calendar public. The secret address works privately.
3. Send that address privately to whoever runs the GitHub repo. Don't email it around or post it anywhere. They add it in GitHub under **Settings → Secrets and variables → Actions → New repository secret**:
   - Name: `DIARY_ICS_URL`
   - Value: the `.ics` address
4. From then on, anything added to that calendar appears on the site the next morning. To show it immediately, use **Actions → Run workflow**.

**How to write an event so it displays well:**

| Field | What to put | Example |
|---|---|---|
| Title | Start with the type in square brackets | `[Surgery] Advice surgery – Sedgley` |
| Types | `[Surgery]`, `[Coffee morning]`, `[Visit]`, `[Public meeting]`, `[Event]` | |
| Location | Venue name and town (no private addresses) | `Sedgley Library, Ladies Walk` |
| Description | How to attend or book | `By appointment – email the office to book` |
| Visibility | Set the event to **Private** to hide it from the website | |

Events from the next 30 days appear in the diary. Past events are kept in an archive automatically.

### Option B – Google Sheet

1. Create a Google Sheet with these column headings in row 1:
   `date | start | end | type | title | location | description | booking | public`
   - **date**: `14/11/2026`
   - **start** and **end**: `10:30`
   - **type**: Surgery, Coffee morning, Visit, Event
   - **public**: `yes` or `no`
2. Go to **File → Share → Publish to web**, choose the sheet, select **CSV**, then **Publish**, and copy the link.
3. Add the link as a repository secret called `DIARY_SHEET_CSV_URL`.

### Photo gallery

- **Easiest way:** upload photos to the `assets/gallery/` folder on GitHub (**Add file → Upload files**). Name each file descriptively, e.g. `sedgley-coffee-morning-nov-2026.jpg`. The file name becomes the caption.
- For proper alt text and credits, add an entry in `data/manual/gallery.json`.
- **Only use photos the office has supplied or approved.** You also need permission from anyone who can be identified in a photo, especially children.
- **Sonia's own photo:** save the photo the office supplies as `assets/img/mp-photo.jpg` (square, at least 600×600). Then fill in `mp.photoCredit` in `config/site.json`. Until that file exists, the site shows a styled placeholder.

---

## 3. Data sources

| # | Section | Source | Notes |
|---|---|---|---|
| 1 | Profile, roles, majority | Members API (`members-api.parliament.uk`, member ID **5274**) | APPGs aren't in any API, so the site links to the official register |
| 3 | Diary | Office's Google Calendar (ICS) or Sheet | Secrets: `DIARY_ICS_URL` / `DIARY_SHEET_CSV_URL` |
| 4 | This week in the Commons | What's On API | |
| 5 | Votes & attendance | Commons Votes API | Attendance = divisions voted in ÷ all divisions since 4 Jul 2024 |
| 6 | Speeches | Hansard API | |
| 7 | Written questions | Written Questions API | |
| 8 | Early Day Motions | Oral Questions & Motions API | |
| 9 | Bills | Bills API | Usually empty for a backbencher |
| 10 | Register of interests | Interests API | |
| 11 | Petitions | petition.parliament.uk JSON | Ranked by signatures from constituency **E14001204** (Dudley, 2024 boundaries) |
| 12 | Council / WMCA meetings | Dudley: CMIS (dudley.cmis.uk.com); WMCA: ModernGov | |
| 13 | Policing | data.police.uk + Google News RSS | Neighbourhoods are found from 8 sample points across the constituency |
| 14 | Constituency profile | ONS via Nomis (Claimant Count, Census 2021) | Links to the Commons Library dashboards |
| 15 | Local news | Google News RSS searches for "Sonia Kumar" and "Dudley MP" | The MP's own site, Express & Star, Black Country Radio and Dudley Council feeds were unavailable to the server |
| 16–17 | Events & useful links | Fixed lists in `config/content.json` | Edit freely |

**If a feed fails,** that section keeps its last good data and shows the date it was retrieved. If it has never worked, the section shows a friendly "fills at the next update" note with a link to the source. A failure never stops the rest of the update. The footer lists the status of every source.

**Dudley Council** uses CMIS (https://dudley.cmis.uk.com), not ModernGov. The script reads the meetings embedded in its calendar page (clicking on to next month with a headless browser). If Dudley ever moves to ModernGov, delete `council.cmisBase` from `config/site.json` and the ModernGov code takes over.

**Maintenance tool:** *Actions → Probe URLs* fetches any URLs from GitHub's servers and prints what came back – useful when a source changes.

---

## 4. Files

```
config/site.json        MP details, contact info, sources, police sample points
config/content.json     Useful links, community events, newsletter setting
scripts/fetch_all.py    Runs every fetcher (keep-last-good logic in common.py)
scripts/parliament.py   UK Parliament APIs
scripts/local.py        Council, WMCA, police, ONS, news, diary, gallery
scripts/build.py        Renders index.html and privacy.html from templates/
templates/              Page templates (Jinja2)
assets/                 CSS, JS, self-hosted font (Atkinson Hyperlegible) and Leaflet
data/                   JSON written by the daily job (data/manual/ is edited by hand)
```

Run it locally with: `pip install -r requirements.txt && python scripts/fetch_all.py && python scripts/build.py`

## 5. Rules this site follows

- The footer and the top ribbon both say it's **independent**, not the MP's official site, and who runs it.
- There's **no portcullis logo, no party logos and no campaigning content**. The automatic sections are factual and neutral.
- It has **no casework form**. People are directed to the official contact route. A form must not be added unless the office approves it and GDPR is handled.
- **No API keys** are stored in the code. Anything private lives in GitHub Secrets.
- It aims for **WCAG 2.2 AA**: contrast, a skip link, keyboard-operable tabs, visible focus, charts readable as tables, reduced-motion support and a highly legible font.
- It has **no tracking**. The map loads OpenStreetMap tiles only when someone presses the button.
