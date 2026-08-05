"""
scrape_historical_practice.py

Scrapes the four practice sessions of the 2000-2003 era (two on Friday, two on
Saturday) from newsonf1.com and writes them into the fridaypractice1/2 and
saturdaypractice1/2 columns of GrandPrixResults.

These are separate from the existing practice1-4 columns, which are generic
session slots filled from formula1.com and which, for this era, hold only a
partial and inconsistent subset of the four real sessions. Nothing here reads or
modifies practice1-4.

Two page shapes exist, because the site's layout changed between seasons:

    2000       one combined page per race, each session an anchored <h3> section
               https://www.newsonf1.com/2000/races/00<slug>res.htm
    2001-2003  one page per session under a race directory
               https://www.newsonf1.com/<year>/races/<slug>/{f1res,f2res,s1res,s2res}.htm

Sessions are always identified by their printed label, never by URL, because in
2003 f2res.htm is "Friday Qualifying" rather than a second Friday practice (F1
switched to single-lap knockout qualifying that year). 2003 therefore has no
Friday Practice 2 at all and those columns stay NULL for the whole season.

Run standalone to backfill an existing database:

    python scrape_historical_practice.py --dry-run
    python scrape_historical_practice.py --year 2002 --grandprix Australian
    python scrape_historical_practice.py
"""

#TODO: Wet-condition times are stored as ordinary times. The source distinguishes them; the schema has nowhere to record session conditions, so that distinction is lost. 
import argparse
import difflib
import random
import re
import sqlite3
import time
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

BASE_URL = "https://www.newsonf1.com"

THOUSANDTH = Decimal("0.001")

SESSION_KEYS = ["thursday1", "thursday2", "friday1", "friday2", "saturday1", "saturday2"]

COLUMN_PREFIX = {
    "thursday1": "thursdaypractice1",
    "thursday2": "thursdaypractice2",
    "friday1": "fridaypractice1",
    "friday2": "fridaypractice2",
    "saturday1": "saturdaypractice1",
    "saturday2": "saturdaypractice2",
}

# (column suffix, SQL type) — no 'laps', newsonf1 never publishes a lap count.
SUB_COLUMNS = [
    ("position", "INTEGER"),
    ("time", "TEXT"),
    ("gap", "TEXT"),
    ("interval", "REAL"),
    ("timeinseconds", "REAL"),
]

# The 2000 season uses its own URL slugs, unrelated to the 2001+ ones.
SEASON_2000_SLUGS = {
    "Australian": "ozres",
    "Brazilian": "brares",
    "San Marino": "sanmanres",
    "British": "britishres",
    "Spanish": "spanishres",
    "European": "europeres",
    "Monaco": "monacores",
    "Canadian": "canadares",
    "French": "franceres",
    "Austrian": "austriares",
    "German": "germanres",
    "Hungarian": "hungaryres",
    "Belgian": "belres",
    "Italian": "itares",
    "United States": "usres",
    "Japanese": "japres",
    "Malaysian": "malres",
}

SEASON_2001_2003_SLUGS = {
    "Australian": "australia",
    "Malaysian": "malaysia",
    "Brazilian": "brazil",
    "San Marino": "sanmarino",
    "Spanish": "spain",
    "Austrian": "austria",
    "Monaco": "monaco",
    "Canadian": "canada",
    "European": "europe",
    "French": "france",
    "British": "britain",
    "German": "germany",
    "Hungarian": "hungary",
    "Belgian": "belgium",
    "Italian": "italy",
    "United States": "usa",
    "Japanese": "japan",
}

# Anchored at the start of the label so prose that merely mentions "Practice"
# (e.g. the "Results - Summary ... from Practice, Qualifying and the Race"
# heading) cannot be mistaken for a session heading. Order matters: the
# "second ..." patterns must be tried before the looser ones.
SESSION_PATTERNS = [
    (re.compile(r"^second\s+thursday\s+practice\b"), "thursday2"),
    (re.compile(r"^(?:first\s+)?thursday\s+practice\b"), "thursday1"),
    (re.compile(r"^second\s+friday\s+practice\b"), "friday2"),
    (re.compile(r"^(?:first\s+)?friday\s+practice\b"), "friday1"),
    (re.compile(r"^second\s+saturday\s+practice\b"), "saturday2"),
    (re.compile(r"^(?:first\s+)?saturday\s+practice\b"), "saturday1"),
]

# Separators are typed inconsistently on this site — "1:32.738", "1.34.935" and
# "1:21:744" all occur — so any of . : , is accepted in either position. The
# shape (minutes, two-digit seconds, up to three-digit thousandths) is still
# enforced strictly, so a genuinely malformed value still fails loudly.
LAP_TIME_RE = re.compile(r"^(\d+)[:.,](\d{2})[:.,](\d{1,3})$")
DRIVER_NAME_RE = re.compile(r"^([A-Za-z])\.\s*(.+)$")

# Footnote markers trail both names and times: a bare "*" (a substitute driver,
# or a time set in the wet) or a numbered "*1" where a page carries several
# notes. The note itself is prose we have nowhere to keep.
FOOTNOTE_RE = re.compile(r"\s*\*+\s*\d*\s*$")


def strip_footnote_marker(text):
    return FOOTNOTE_RE.sub("", text).strip()


def normalize_name(name):
    """
    Normalizes a name for comparison by converting to lowercase and decomposing
    unicode characters. e.g., 'José' becomes 'jose'.

    Duplicated from writedb.py rather than imported: writedb.py has no
    __main__ guard, so importing from it would run the entire scraper.
    """
    if not name:
        return ""
    if name.lower() == "gianmaria bruni":
        return "gimmi bruni"
    elif name.lower() == "zhou guanyu":
        return "guanyu zhou"
    return unicodedata.normalize('NFKD', name.lower()).encode('ascii', 'ignore').decode('ascii').replace('-', ' ')


def clean_text(tag):
    """
    Collapses all whitespace in a cell to single spaces.

    get_text(strip=True) leaves the newlines the source wraps mid-cell in
    place, so "P.\\nde la Rosa" would survive as-is. str.split() also treats
    the &nbsp; these tables are littered with as whitespace.
    """
    return " ".join(tag.get_text(" ").split())


def classify_session_label(label):
    """Maps a printed session label to a session key, or None if not one of ours."""
    text = " ".join(label.lower().split())
    if "qualifying" in text:
        # 2003 labels its second Friday session "Friday Qualifying".
        return None
    for pattern, key in SESSION_PATTERNS:
        if pattern.search(text):
            return key
    return None


def parse_lap_time(text):
    """
    Parses a newsonf1 lap time into exact Decimal seconds, or None for a
    driver who set no time.

    Both "1:32.738" and "1.34.935" occur, sometimes within one table. Decimal
    is built straight from the digit strings so no float ever touches the value
    — gaps and intervals are derived by subtraction, where binary floating
    point visibly corrupts the result (88.821 - 87.276 = 1.5450000000000017).
    """
    text = " ".join(text.split())
    # The site phrases a missing time several ways ("No Time", "No timed laps",
    # "-"). A real lap time always contains digits, so a digit-free cell means
    # the driver set no time; anything containing digits must still parse.
    if not any(character.isdigit() for character in text):
        return None
    # A footnote marker here means "a time under wet conditions" (e.g. the 2000
    # British GP). The lap time itself is valid, and we have nowhere to record
    # session conditions, so keep the time.
    text = strip_footnote_marker(text)
    # Typos in hand-entered times: a stray space ("1: 19.247") or a doubled
    # separator ("1:.19.247"). Collapse both, keeping the first character of a
    # separator run, before the strict shape check below.
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[:.,]{2,}", lambda run: run.group(0)[0], text)
    match = LAP_TIME_RE.match(text)
    if not match:
        raise ValueError(f"Unparseable newsonf1 lap time: {text!r}")
    minutes, seconds, millis = match.groups()
    return Decimal(minutes) * 60 + Decimal(seconds) + Decimal(millis.ljust(3, "0")) / 1000


def format_lap_time(total_seconds):
    """Formats Decimal seconds as the canonical 'M:SS.mmm' used elsewhere in the table."""
    minutes = int(total_seconds // 60)
    remainder = (total_seconds - minutes * 60).quantize(THOUSANDTH)
    return f"{minutes}:{remainder:06.3f}"


def parse_session_table(table, context):
    """
    Extracts one results table.

    Columns are resolved by header text, never by index: 2003 inserts a Tyre
    column between Team and Best Lap, and the header reads "Pos." on some pages
    and "Position" on others. The Tyre value itself is discarded — it is only
    Michelin vs Bridgestone, already recorded in GrandPrixResults.tyre.
    """
    header_map = {}
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        texts = [clean_text(cell).lower() for cell in cells]
        if not any("driver" in text for text in texts):
            continue
        for index, text in enumerate(texts):
            if "pos" in text and "position" not in header_map:
                header_map["position"] = index
            elif "driver" in text and "driver" not in header_map:
                header_map["driver"] = index
            elif "team" in text and "team" not in header_map:
                header_map["team"] = index
            elif ("lap" in text or "time" in text) and "time" not in header_map:
                header_map["time"] = index
        break

    missing = {"position", "driver", "team", "time"} - set(header_map)
    if missing:
        raise RuntimeError(f"Could not resolve columns {sorted(missing)} in {context}")

    rows = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) <= max(header_map.values()):
            continue
        printed_position = clean_text(cells[header_map["position"]])
        # The header row and the leader's row are both bold on some pages, so
        # bold tags cannot be used to spot the header. A numeric first cell can.
        if not printed_position.isdigit():
            continue
        # Positions are hand-typed and occasionally malformed — the 2000
        # Malaysian GP prints "112" for 11. These tables are always listed in
        # order, and the printed value agrees with the row's ordinal in every
        # other session of this era, so the ordinal is authoritative. Any
        # disagreement is reported rather than silently corrected.
        position = len(rows) + 1
        if int(printed_position) != position:
            print(
                f"    ! {context}: position reads {printed_position!r} for "
                f"{clean_text(cells[header_map['driver']])!r}; using {position} from row order"
            )
        rows.append({
            "position": position,
            # A footnote marker on a name flags a substitution (e.g. "L. Burti *"
            # — replacing the injured Eddie Irvine at the 2000 Austrian GP). The
            # entrant list already records who drove, so the marker is dropped.
            "raw_driver": strip_footnote_marker(clean_text(cells[header_map["driver"]])),
            "raw_team": clean_text(cells[header_map["team"]]),
            "time_seconds": parse_lap_time(clean_text(cells[header_map["time"]])),
        })

    if not rows:
        raise RuntimeError(f"No result rows found in {context}")
    return rows


def compute_session_columns(rows):
    """Derives the time string, gap to leader, and interval to the car ahead."""
    rows = sorted(rows, key=lambda row: row["position"])
    timed = [row for row in rows if row["time_seconds"] is not None]
    leader_row = timed[0] if timed else None
    previous = None

    for row in rows:
        seconds = row["time_seconds"]
        if seconds is None:
            row["time_str"] = None
            row["gap_str"] = None
            row["interval"] = None
            continue
        row["time_str"] = format_lap_time(seconds)
        if row is leader_row:
            row["gap_str"] = None
        else:
            gap = (seconds - leader_row["time_seconds"]).quantize(THOUSANDTH, rounding=ROUND_HALF_UP)
            row["gap_str"] = f"+{gap}s"
        if previous is None:
            row["interval"] = None
        else:
            row["interval"] = (seconds - previous).quantize(THOUSANDTH, rounding=ROUND_HALF_UP)
        previous = seconds
    return rows


def fetch(session, url, attempts=4, allow_missing=False):
    """
    Fetches and parses a page, raising loudly rather than returning None.

    Retries cover dropped connections and read timeouts as well as bad status
    codes — this is an old, slow server that intermittently stalls — but an
    exhausted retry budget still raises. A 404 is deterministic, so it is not
    retried; pass allow_missing to probe for a page that may not exist.
    """
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(url, headers=HEADERS, timeout=60)
            if response.status_code == 200:
                return BeautifulSoup(response.content, "html.parser")
            if response.status_code == 404:
                if allow_missing:
                    return None
                raise RuntimeError(f"Not found: {url}")
            problem = f"status {response.status_code}"
        except requests.RequestException as error:
            problem = f"{type(error).__name__}: {error}"
        if attempt == attempts:
            raise RuntimeError(f"Failed to fetch {url} after {attempts} attempts ({problem})")
        time.sleep(2 ** attempt)


def fetch_race_entry(session, race):
    """
    Opens a race's entry page, trying each known filename.

    Race directories are almost all main.htm, but at least one (the 2001
    Japanese GP) is main.shtml instead.
    """
    for url in race["entry_urls"]:
        soup = fetch(session, url, allow_missing=True)
        if soup is not None:
            return soup, url
    raise RuntimeError(
        f"No entry page for {race['gp_name']}; tried {', '.join(race['entry_urls'])}"
    )


def find_session_heading(soup):
    """Returns (session_key, heading_tag) for the first heading that names one of our sessions."""
    for heading in soup.find_all("h3"):
        key = classify_session_label(clean_text(heading))
        if key:
            return key, heading
    return None, None


def discover_sessions_2000(soup):
    """2000: every session is an anchored <h3> section on one combined page."""
    found = {}
    for heading in soup.find_all("h3"):
        key = classify_session_label(clean_text(heading))
        if not key or key in found:
            continue
        table = heading.find_next("table")
        if table is None:
            raise RuntimeError(f"No table after heading {clean_text(heading)!r}")
        found[key] = table
    return found


def discover_sessions_2001_2003(session, soup, entry_url, delay_range):
    """
    2001-2003: follow main.htm's navigation table, classifying each row's label
    cell to find that session's real page.

    Going through the labels rather than guessing f1res/f2res/s1res/s2res is
    what keeps 2003's "Friday Qualifying" out of the practice columns. Each
    session page is also self-describing, so its own heading is used as a
    cross-check.
    """
    links = {}
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        key = classify_session_label(clean_text(cells[0]))
        if not key or key in links:
            continue
        link = row.find("a", href=True)
        if link is None:
            raise RuntimeError(
                f"Navigation row labelled {clean_text(cells[0])!r} has no link on {entry_url}"
            )
        links[key] = urljoin(entry_url, link["href"])

    found = {}
    for key in SESSION_KEYS:
        if key not in links:
            continue
        time.sleep(random.uniform(*delay_range))
        page = fetch(session, links[key])
        page_key, heading = find_session_heading(page)
        if page_key != key:
            raise RuntimeError(
                f"Session label mismatch for {links[key]}: navigation says {key!r} "
                f"but the page's own heading says {page_key!r}. Refusing to guess."
            )
        table = heading.find_next("table")
        if table is None:
            raise RuntimeError(f"No table after heading on {links[key]}")
        found[key] = table
    return found


def build_race_index():
    """The 67 races of 2000-2003, in chronological-ish season order."""
    races = []
    for name, slug in SEASON_2000_SLUGS.items():
        races.append({
            "year": 2000,
            "gp_name": f"2000 {name} Grand Prix",
            "entry_urls": [f"{BASE_URL}/2000/races/00{slug}.htm"],
        })
    for year in (2001, 2002, 2003):
        for name, slug in SEASON_2001_2003_SLUGS.items():
            if year == 2003 and name == "Belgian":
                # The 2003 Belgian GP was cancelled; absent from our DB and from newsonf1.
                continue
            directory = f"{BASE_URL}/{year}/races/{slug}"
            races.append({
                "year": year,
                "gp_name": f"{year} {name} Grand Prix",
                "entry_urls": [f"{directory}/main.htm", f"{directory}/main.shtml"],
            })
    return races


def ensure_columns(cur):
    """Adds any missing practice columns. Safe to re-run."""
    existing = {row[1] for row in cur.execute("PRAGMA table_info(GrandPrixResults)")}
    added = []
    for prefix in COLUMN_PREFIX.values():
        for suffix, sql_type in SUB_COLUMNS:
            column = f"{prefix}{suffix}"
            if column not in existing:
                cur.execute(f"ALTER TABLE GrandPrixResults ADD COLUMN {column} {sql_type}")
                added.append(column)
    if added:
        print(f"Added {len(added)} columns to GrandPrixResults.")
    return added


def get_roster(cur, grandprix_id):
    cur.execute(
        "SELECT driverid, driver, team FROM GrandPrixResults WHERE grandprixid = ?",
        (grandprix_id,),
    )
    return [{"driverid": row[0], "driver": row[1], "team": row[2]} for row in cur.fetchall()]


def parse_newsonf1_driver(raw):
    """'M. Schumacher' -> ('m', 'schumacher'); 'P. de la Rosa' -> ('p', 'de la rosa')."""
    match = DRIVER_NAME_RE.match(raw)
    if not match:
        raise ValueError(f"Unparseable newsonf1 driver name: {raw!r}")
    return normalize_name(match.group(1)), normalize_name(match.group(2))


def match_driver_to_roster(raw_driver, raw_team, roster, context):
    """
    Resolves a scraped driver against that Grand Prix's entrant list.

    Every driver who ran a practice session already has a GrandPrixResults row
    for that weekend, third and substitute drivers included, so failing to
    match is always a defect rather than a driver we may skip.
    """
    initial, surname = parse_newsonf1_driver(raw_driver)
    candidates = [
        entry for entry in roster
        if normalize_name(entry["driver"]).startswith(initial)
        and normalize_name(entry["driver"]).endswith(surname)
    ]

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        team = raw_team.lower()
        narrowed = [
            entry for entry in candidates
            if team and (team in entry["team"].lower() or entry["team"].lower() in team)
        ]
        if len(narrowed) == 1:
            return narrowed[0]
        raise RuntimeError(
            f"Ambiguous driver match in {context}: {raw_driver!r} ({raw_team!r}) matches "
            f"{[entry['driver'] + ' / ' + entry['team'] for entry in candidates]}"
        )

    hint = difflib.get_close_matches(
        f"{initial} {surname}", [normalize_name(entry["driver"]) for entry in roster], n=3, cutoff=0.4
    )
    raise RuntimeError(
        f"No driver match in {context}: {raw_driver!r} ({raw_team!r}). "
        f"Closest roster names: {hint or 'none'}. "
        f"Roster: {sorted(entry['driver'] for entry in roster)}"
    )


def apply_session_row(cur, grandprix_id, driverid, prefix, row):
    assignments = ", ".join(f"{prefix}{suffix} = ?" for suffix, _ in SUB_COLUMNS)
    values = (
        row["position"],
        row["time_str"],
        row["gap_str"],
        float(row["interval"]) if row["interval"] is not None else None,
        float(row["time_seconds"]) if row["time_seconds"] is not None else None,
    )
    cur.execute(
        f"UPDATE GrandPrixResults SET {assignments} WHERE grandprixid = ? AND driverid = ?",
        values + (grandprix_id, driverid),
    )
    # (grandprixid, driverid) has no UNIQUE constraint, so verify rather than assume.
    if cur.rowcount != 1:
        raise RuntimeError(
            f"Expected to update exactly 1 row for grandprixid={grandprix_id} "
            f"driverid={driverid}, but updated {cur.rowcount}"
        )


def backfill_one_race(cur, session, race, dry_run, delay_range):
    gp_name = race["gp_name"]
    cur.execute("SELECT ID FROM GrandsPrix WHERE GrandPrixName = ?", (gp_name,))
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"No GrandsPrix row named {gp_name!r}")
    grandprix_id = row[0]

    roster = get_roster(cur, grandprix_id)
    if not roster:
        raise RuntimeError(f"No GrandPrixResults rows for {gp_name!r} (grandprixid={grandprix_id})")

    entry_soup, entry_url = fetch_race_entry(session, race)
    if race["year"] == 2000:
        sessions = discover_sessions_2000(entry_soup)
    else:
        sessions = discover_sessions_2001_2003(session, entry_soup, entry_url, delay_range)

    summary = {"gp": gp_name, "updated": 0, "found": [], "missing": []}
    pending = []

    for key in SESSION_KEYS:
        table = sessions.get(key)
        if table is None:
            summary["missing"].append(key)
            continue
        context = f"{gp_name} / {key}"
        rows = compute_session_columns(parse_session_table(table, context))
        summary["found"].append(f"{key}({len(rows)})")
        for entry in rows:
            matched = match_driver_to_roster(
                entry["raw_driver"], entry["raw_team"], roster, context
            )
            pending.append((COLUMN_PREFIX[key], matched["driverid"], entry))

    # Only reached once every session of this race matched cleanly.
    if not dry_run:
        for prefix, driverid, entry in pending:
            apply_session_row(cur, grandprix_id, driverid, prefix, entry)
    summary["updated"] = len(pending)
    return summary


def is_already_backfilled(cur, grandprix_id):
    """
    Saturday Practice 1 is the only session all 67 races share, so it is the
    safe completion marker: fridaypractice2 is legitimately NULL for the whole
    of 2003, and both Friday columns are NULL at Monaco, which practised on
    Thursday instead.
    """
    cur.execute(
        "SELECT 1 FROM GrandPrixResults "
        "WHERE grandprixid = ? AND saturdaypractice1position IS NOT NULL LIMIT 1",
        (grandprix_id,),
    )
    return cur.fetchone() is not None


def scrape_historical_practice_sessions(
    years=None,
    grandprix_names=None,
    force=False,
    dry_run=False,
    db_path="sessionresults.db",
    delay_range=(3, 8),
):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    ensure_columns(cur)
    con.commit()

    races = build_race_index()
    if years is not None:
        races = [race for race in races if race["year"] in years]
    if grandprix_names is not None:
        wanted = [name.lower() for name in grandprix_names]
        races = [
            race for race in races
            if any(name in race["gp_name"].lower() for name in wanted)
        ]

    if not races:
        print("No races matched the given filters.")
        con.close()
        return {"processed": [], "skipped": [], "total_updated": 0}

    http = requests.Session()
    report = {"processed": [], "skipped": [], "failed": [], "total_updated": 0}
    print(f"{len(races)} race(s) to consider.{' (dry run)' if dry_run else ''}\n")

    for race in races:
        gp_name = race["gp_name"]
        cur.execute("SELECT ID FROM GrandsPrix WHERE GrandPrixName = ?", (gp_name,))
        row = cur.fetchone()
        if row is not None and not force and not dry_run and is_already_backfilled(cur, row[0]):
            report["skipped"].append(gp_name)
            print(f"  - {gp_name}: already backfilled, skipping")
            continue

        # A race is all-or-nothing: backfill_one_race writes only once every
        # session in it has matched, so a failure leaves nothing partial behind.
        # Failures are collected rather than raised immediately so that one
        # malformed race does not hide problems in every race after it; the run
        # still fails loudly at the end.
        try:
            summary = backfill_one_race(cur, http, race, dry_run, delay_range)
        except (RuntimeError, ValueError) as error:
            con.rollback()
            report["failed"].append((gp_name, str(error)))
            print(f"  ! {gp_name}: {error}")
            time.sleep(random.uniform(*delay_range))
            continue

        if not dry_run:
            con.commit()
        report["processed"].append(summary)
        report["total_updated"] += summary["updated"]
        missing = f"  missing: {', '.join(summary['missing'])}" if summary["missing"] else ""
        print(f"  + {gp_name}: {summary['updated']} rows  [{', '.join(summary['found'])}]{missing}")
        time.sleep(random.uniform(*delay_range))

    con.close()

    print(
        f"\nDone. Races processed: {len(report['processed'])}, "
        f"skipped: {len(report['skipped'])}, failed: {len(report['failed'])}, "
        f"rows updated: {report['total_updated']}"
        f"{' (dry run — nothing written)' if dry_run else ''}"
    )

    if report["failed"]:
        detail = "\n".join(f"  {name}: {error}" for name, error in report["failed"])
        raise RuntimeError(
            f"{len(report['failed'])} race(s) failed and wrote nothing. "
            f"Fix these and re-run; completed races are skipped:\n{detail}"
        )
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Backfill 2000-2003 Friday/Saturday practice sessions from newsonf1.com"
    )
    parser.add_argument("--year", type=int, action="append", dest="years",
                        help="restrict to a season (repeatable)")
    parser.add_argument("--grandprix", action="append", dest="grandprix",
                        help="restrict to Grand Prix names containing this text (repeatable)")
    parser.add_argument("--force", action="store_true",
                        help="re-scrape races that already have data")
    parser.add_argument("--dry-run", action="store_true",
                        help="scrape and match, but write nothing")
    parser.add_argument("--delay", nargs=2, type=float, metavar=("MIN", "MAX"),
                        default=(3.0, 8.0),
                        help="seconds to pause between requests (default: 3 8)")
    args = parser.parse_args()

    scrape_historical_practice_sessions(
        years=set(args.years) if args.years else None,
        grandprix_names=args.grandprix,
        force=args.force,
        dry_run=args.dry_run,
        delay_range=tuple(args.delay),
    )


if __name__ == "__main__":
    main()
