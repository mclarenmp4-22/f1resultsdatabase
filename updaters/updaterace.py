"""
Re-sync the result of one Grand Prix with StatsF1 after it changed.

Results change after the chequered flag: post-race time penalties, disqualifications,
appeals, or StatsF1 correcting its own data. writedb.py only scrapes Grands Prix that
are newer than the last one in the database, so a change to an older race never
reaches it. This script re-scrapes the race (and the sprint, on a sprint weekend)
for a single Grand Prix and rewrites everything that depends on it:

  1. GrandPrixResults  - race/sprint classification, fastest laps, penalties
  2. GrandsPrix        - RaceResultNotes / SprintNotes
  3. InSeasonProgressDrivers / InSeasonProgressConstructors - for this Grand Prix
     and every later Grand Prix of the same season already in the database
  4. DriversChampionship / ConstructorsChampionship - for the season
  5. Derived statistics (Drivers, Constructors, ... , Seasons) via
     updaters/update_stats_alone.py

Standings (3 and 4) are derived from the database, not scraped, for every season in
which all scores count (1991 onwards): the points that changed are applied as deltas,
positions are re-ranked (shared positions for ties in the in-season tables; points then
countback on race finishing positions in the championship tables, which is what StatsF1
does), and the championship's mathematical locks are re-applied. Deltas rather than a
rebuild so that historical deductions (Benetton 1995, McLaren 2000, Racing Point 2020) and
exclusions (Schumacher 1997) stored from StatsF1 survive untouched. Seasons with dropped
scores or top-car-only constructor points (1950-1990) are re-scraped from StatsF1 instead.

Usage:
    python updaters/updaterace.py "2026 Monaco Grand Prix"
    python updaters/updaterace.py "2026 Monaco Grand Prix" --dry-run
    python updaters/updaterace.py "2026 Monaco Grand Prix" --skip-stats
    python updaters/updaterace.py "2026 Monaco Grand Prix" --results-only

Lap-by-lap data, pit stops, sessions and the race report are not touched: they do not
change when a result is reclassified. Refresh the race report separately with
    python writedb.py --updateracereport "2026 Monaco Grand Prix"

The parsing mirrors parse_race_results() in writedb.py so that the columns written
here are shaped exactly like the ones writedb.py writes. Everything runs in a single
transaction; if anything fails, nothing is written.
"""

import argparse
import json
import random
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata
import urllib.request
from decimal import Decimal
from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi import requests

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "sessionresults.db"
STATS_UPDATER = ROOT / "updaters" / "update_stats_alone.py"

STATSF1 = "https://www.statsf1.com"
# Same Next.js build id that writedb.py uses for Motorsport Stats. If their build changes, both break together.
MOTORSPORTSTATS_BUILD = "c2LGT9ym-c6f1pXlf9hjs"
# writedb.py only asks Motorsport Stats for race times/gaps after the 1981 Argentine Grand Prix (ID 344).
FIRST_GRAND_PRIX_WITH_API_TIMES = 344

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.7922.138 Safari/537.36"
    )
}

STATUS_ABBREVIATIONS = {
    "ab": "Did not finish",
    "dsq": "Disqualified",
    "nc": "Not classified",
    "exc": "Excluded",
    "np": "Did not start",
    "f": "Withdrew",
    "nq": "Did not qualify",
    "tf": "Formation lap",
    "npq": "Did not pre-qualify",
    "t": "Substitute, third driver",
}

# Race times on StatsF1 look like "2h 23m 31.243s (+06.271s)"; this is the same regex writedb.py uses.
TIME_REGEX = re.compile(r"(\d+h\s*)?(\d+m\s*)?(\d+(?:\.\d+)?s|\d+:\d{2}(?::\d{2}(?:\.\d+)?)?)")

RACE_COLUMNS = [
    "raceposition", "racelaps", "racetime", "racepoints", "racestatus", "racestatusreason",
    "racetimeinseconds", "racegap", "racegapinseconds", "raceinterval",
]
FASTEST_LAP_COLUMNS = [
    "fastestlap", "fastestlapinseconds", "fastestlapgapinseconds", "fastestlapinterval",
    "fastestlap_time", "fastestlap_gap", "fastestlap_lap",
]
SPRINT_COLUMNS = [
    "sprintposition", "sprintlaps", "sprinttime", "sprintpoints", "sprintstatus", "sprintstatusreason",
    "sprinttimeinseconds", "sprintgap", "sprintgapinseconds", "sprintinterval",
]
SPRINT_FASTEST_LAP_COLUMNS = [
    "sprintfastestlap", "sprintfastestlapinseconds", "sprintfastestlapgapinseconds", "sprintfastestlapinterval",
    "sprintfastestlap_time", "sprintfastestlap_gap", "sprintfastestlap_lap",
]
PENALTY_COLUMNS = ["penalties", "sprint_penalties"]


# ---------------------------------------------------------------------------------------------
# Fetching. Same fingerprint, retries and StatsF1 throttle as writedb.py: be considerate to the sources.
# ---------------------------------------------------------------------------------------------
def fetch_html(url, retries=3):
    last_exception = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, impersonate="chrome", timeout=30)
            if response.status_code == 302 and response.headers.get("location") == "https://www.statsf1.com/errors/GenericErrorPage.htm":
                raise RuntimeError("You have been IP blocked by statsf1.com. Please wait and try again later.")
            response.raise_for_status()
            if "statsf1.com" in url:
                time.sleep(random.uniform(4, 15))
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            last_exception = e
            print(f"Attempt {attempt + 1} failed for URL {url}: {e}")
            if attempt < retries - 1:
                time.sleep(random.expovariate(1 / (5 * (2 ** attempt))))
    raise RuntimeError(f"Failed to open URL {url} after {retries} attempts.") from last_exception


def fetch_json(url, retries=3):
    last_exception = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            return json.loads(urllib.request.urlopen(request).read())
        except Exception as e:
            last_exception = e
            print(f"Attempt {attempt + 1} failed for URL {url}: {e}")
            time.sleep(1)
    raise RuntimeError(f"Failed to open URL {url} after {retries} attempts.") from last_exception


# ---------------------------------------------------------------------------------------------
# Small helpers copied from writedb.py so the values come out byte-for-byte the same.
# ---------------------------------------------------------------------------------------------
def normalize_name(name):
    if not name:
        return ""
    if name.lower() == "gianmaria bruni":
        return "gimmi bruni"
    elif name.lower() == "zhou guanyu":
        return "guanyu zhou"
    return unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode("ascii").replace("-", " ")


def quantize(value):
    return float(Decimal(str(value)).quantize(Decimal("0.001")))


def parse_race_time(time_str):
    """'1h 42m 06.304s' -> 6126.304. Strings without any time component give 0.0, as in writedb.py."""
    h = m = s = 0.0
    time_str = time_str.replace("hr", "h").replace("min", "m")
    match_h = re.search(r"(\d+)\s*h", time_str)
    match_m = re.search(r"(\d+)\s*m", time_str)
    match_s = re.search(r"([\d.]+)\s*s", time_str)
    if match_h:
        h = int(match_h.group(1))
    if match_m:
        m = int(match_m.group(1))
    if match_s:
        s = float(match_s.group(1))
    return quantize(h * 3600 + m * 60 + s)


def tts(t):
    """'1:13.481' -> 73.481, '33:38.998' -> 2018.998, '2.016' -> 2.016, anything else -> None."""
    parts = t.strip().split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return quantize(int(hours) * 3600 + int(minutes) * 60 + float(seconds))
    elif len(parts) == 2:
        minutes, seconds = parts
        return quantize(int(minutes) * 60 + float(seconds))
    elif len(parts) == 1:
        return quantize(float(parts[0])) if parts[0].replace(".", "", 1).isdigit() else None
    return None


def api_time_string(milliseconds):
    """Motorsport Stats millisecond value -> the 'hh:mm.sss' text writedb.py stores for it."""
    h = milliseconds // 3600000
    m = (milliseconds % 3600000) // 60000
    s = (milliseconds % 60000) / 1000
    return f"{h:02d}:{m:02d}.{s:03.0f}s"


def cell_texts(tr):
    return [cell.get_text(strip=True) for cell in tr.find_all("td")]


def gap_from(raw):
    """The '(+06.271s)' part of a StatsF1 time cell, padding included, exactly as writedb.py keeps it."""
    if "(" in raw:
        inner = raw.split("(")[1].replace(")", "")
        if inner.strip().endswith("s"):
            return inner
    return None


def split_time_and_reason(raw):
    """'2h 23m 31.243s (...)' -> ('2:23:31.243s', None); 'Accident' -> (None, 'Accident')."""
    match = TIME_REGEX.search(raw)
    if match:
        return (match.group(0).strip().replace("h ", ":").replace("m ", ":") or None, raw[:match.start()].strip() or None)
    return (None, raw.strip() or None)


# Sprint times are printed as 33'38.998 (colon after normalisation). A disqualified driver's cell carries
# the reason and the time together: "Technical non-compliance30'03.483".
SPRINT_TIME_REGEX = re.compile(r"(?:\d+:)?\d{1,2}:\d{2}\.\d+")


def split_sprint_time_and_reason(text):
    """'30:03.483' -> ('30:03.483', None); 'Technical non-compliance30:03.483' -> ('30:03.483', 'Technical non-compliance'); 'Engine' -> (None, 'Engine')."""
    match = SPRINT_TIME_REGEX.search(text)
    if match:
        return match.group(0), (text[:match.start()].strip() or None)
    return None, (text.strip() or None)


def is_number(text):
    return text.replace(".", "", 1).isdigit()


# ---------------------------------------------------------------------------------------------
# Matching StatsF1 names to GrandPrixResults rows
# ---------------------------------------------------------------------------------------------
def find_row(rows, name, number=None, source=""):
    """
    Return the GrandPrixResults row for a driver as StatsF1 prints them ("Kimi ANTONELLI").
    `number` narrows to one car, which is what tells shared-car drivers apart in the 1950s.
    """
    target = normalize_name(name)
    candidates = [row for row in rows if number is None or row["number"] == number]
    matches = [row for row in candidates if normalize_name(row["driver"]) == target]
    if not matches:
        matches = [row for row in candidates if sorted(normalize_name(row["driver"]).split()) == sorted(target.split())]
    if not matches:
        # writedb.py's rule: the database name is contained in the StatsF1 name (suffixes such as "Jr.").
        matches = [row for row in candidates if normalize_name(row["driver"]) in target]
    names = {row["driver"] for row in matches}
    if len(names) != 1:
        where = f"car #{number}" if number is not None else "any car"
        raise ValueError(
            f"{source}: cannot match '{name}' ({where}) to exactly one GrandPrixResults row; "
            f"candidates were {sorted(names) if names else [row['driver'] for row in candidates]}. "
            "The entry list on StatsF1 no longer matches the database, so this race needs a full re-scrape."
        )
    return matches[0]


def find_by_name(name, names_to_ids, source=""):
    """Map a StatsF1 driver name onto the database's Drivers.Name using the same normalisation."""
    target = normalize_name(name)
    matches = [db_name for db_name in names_to_ids if normalize_name(db_name) == target]
    if not matches:
        matches = [db_name for db_name in names_to_ids if sorted(normalize_name(db_name).split()) == sorted(target.split())]
    if len(matches) != 1:
        raise ValueError(f"{source}: cannot match driver '{name}' to exactly one driver of the season; found {matches}")
    return matches[0]


# ---------------------------------------------------------------------------------------------
# StatsF1 parsers
# ---------------------------------------------------------------------------------------------
def parse_notes(soup):
    notes_div = soup.find("div", id="ctl00_CPH_Main_P_Commentaire")
    return notes_div.text.strip() if notes_div else ""


def parse_penalties(soup, is_sprint):
    penalties = []
    during_table = soup.find("table", id="ctl00_CPH_Main_GV_PenaltyP", class_="datatable")
    if during_table:
        for tr in during_table.find("tbody").find_all("tr"):
            cells = cell_texts(tr)
            if len(cells) == 3:
                penalties.append({"driver": cells[0], "penalty": cells[1], "reason": cells[2], "type": "during_the_race", "is_sprint": is_sprint})
    after_table = soup.find("table", id="ctl00_CPH_Main_GV_PenaltyA", class_="datatable")
    if after_table:
        for tr in after_table.find("tbody").find_all("tr"):
            cells = cell_texts(tr)
            if len(cells) == 4:
                penalties.append({
                    "driver": cells[0], "penalty": cells[1], "reason": cells[2],
                    "lost_position": int(cells[3]) if cells[3].isdigit() else None,
                    "type": "added_after_chequered_flag", "is_sprint": is_sprint,
                })
    return penalties


def classified_race_values(new, cells):
    raw = cells[6]
    time_part = raw.split("(")[0] if "(" in raw else raw
    new["racetimeinseconds"] = parse_race_time(time_part)
    new["racegap"] = gap_from(raw)
    new["racegapinseconds"] = parse_race_time(new["racegap"].replace("+", "")) if new["racegap"] else None
    new["racepoints"] = float(cells[7]) if is_number(cells[7]) else None
    new["racetime"], new["racestatusreason"] = split_time_and_reason(raw)
    new["racestatus"] = "Classified"


def parse_race_classification(soup, rows):
    """
    classement.aspx -> {rowid: {race column: value}}.
    Columns: pos | no | driver | constructor | engine | laps | time (gap) | points.
    A '&' in the position column is a shared car: the driver relieved the previous main row's car.
    """
    table = soup.find("table", class_="datatable")
    if table is None:
        raise ValueError("No classification table found on the StatsF1 race page.")
    updates = {}
    main_number = main_position = main_status = None
    for tr in table.find("tbody").find_all("tr"):
        cells = cell_texts(tr)
        if len(cells) < 8:
            raise ValueError(f"Unexpected number of cells in classification row: {len(cells)}. Expected at least 8.")
        if not cells[1].isdigit() and cells[2] == "":
            continue
        shared = cells[0] == "&"
        if shared:
            if main_number is None:
                raise ValueError("Shared-car row found before any main car row in the classification.")
            number = main_number
        else:
            number = int(cells[1])
        row = find_row(rows, cells[2], number, source="Race classification")
        new = {column: None for column in RACE_COLUMNS}
        raw = cells[6]
        if shared:
            new["raceposition"] = main_position
            new["racelaps"] = int(cells[5]) if cells[5].isdigit() else None
            if main_position is None:
                new["racestatus"] = main_status
                new["racegap"] = gap_from(raw)
                new["racetime"], new["racestatusreason"] = split_time_and_reason(raw)
                new["racepoints"] = 0
            else:
                classified_race_values(new, cells)
        elif cells[0] in STATUS_ABBREVIATIONS:
            new["racelaps"] = int(cells[5]) if cells[5].isdigit() else None
            new["racestatus"] = STATUS_ABBREVIATIONS[cells[0]]
            new["racegap"] = gap_from(raw)
            new["racetime"], new["racestatusreason"] = split_time_and_reason(raw)
            new["racepoints"] = 0
            main_number, main_position, main_status = number, None, new["racestatus"]
        else:
            new["raceposition"] = int(cells[0])
            new["racelaps"] = int(cells[5])
            classified_race_values(new, cells)
            main_number, main_position, main_status = number, new["raceposition"], "Classified"
        if row["rowid"] in updates:
            raise ValueError(f"Race classification lists {row['driver']} (#{number}) twice.")
        updates[row["rowid"]] = new
    if not updates:
        raise ValueError("The StatsF1 race classification is empty.")
    return updates


def parse_sprint_classification(soup, rows):
    """
    sprint.aspx -> {rowid: {sprint column: value}}.
    Columns: pos | driver | constructor | engine | laps | time (gap) | places gained | points.
    There is no car number column, so drivers are matched by name only.
    """
    table = soup.find("table", class_="datatable")
    if table is None:
        raise ValueError("No classification table found on the StatsF1 sprint page.")
    updates = {}
    for tr in table.find("tbody").find_all("tr"):
        cells = cell_texts(tr)
        if len(cells) < 8:
            raise ValueError(f"Unexpected number of cells in sprint row: {len(cells)}. Expected at least 8.")
        if cells[1] == "":
            continue
        row = find_row(rows, cells[1], source="Sprint classification")
        new = {column: None for column in SPRINT_COLUMNS}
        raw = cells[5].replace("'", ":")
        time_part = (raw.split("(")[0] if "(" in raw else raw).strip()
        new["sprintgap"] = gap_from(raw)
        new["sprintgapinseconds"] = parse_race_time(new["sprintgap"].replace("+", "")) if new["sprintgap"] else None
        new["sprinttime"], new["sprintstatusreason"] = split_sprint_time_and_reason(time_part)
        new["sprinttimeinseconds"] = tts(new["sprinttime"]) if new["sprinttime"] else None
        if cells[0] in STATUS_ABBREVIATIONS:
            new["sprintlaps"] = int(cells[4]) if cells[4].isdigit() else None
            new["sprintstatus"] = STATUS_ABBREVIATIONS[cells[0]]
            new["sprintpoints"] = 0
        else:
            new["sprintposition"] = int(cells[0])
            new["sprintlaps"] = int(cells[4])
            new["sprintstatus"] = "Classified"
            new["sprintpoints"] = float(cells[7]) if is_number(cells[7]) else None
        if row["rowid"] in updates:
            raise ValueError(f"Sprint classification lists {row['driver']} twice.")
        updates[row["rowid"]] = new
    if not updates:
        raise ValueError("The StatsF1 sprint classification is empty.")
    return updates


def parse_fastest_laps(soup, rows, updates, prefix):
    """
    meilleur-tour.aspx / sprint.aspx?mt -> fills the (sprint)fastestlap columns of `updates`.
    Columns: pos | driver | constructor | engine | time | gap | lap | speed.
    Every classified row is reset first, so a driver who drops out of the table loses the columns.
    """
    columns = SPRINT_FASTEST_LAP_COLUMNS if prefix == "sprint" else FASTEST_LAP_COLUMNS
    for new in updates.values():
        for column in columns:
            new[column] = None
    table = soup.find("table", class_="datatable")
    if table is None:
        print(f"  No {prefix or 'race'} fastest lap table on StatsF1 (races without a racing lap have none).")
        return
    for tr in table.find("tbody").find_all("tr"):
        cells = cell_texts(tr)
        if len(cells) < 8:
            continue
        row = find_row(rows, cells[1], source=f"{prefix or 'Race'} fastest laps")
        if row["rowid"] not in updates:
            raise ValueError(f"{row['driver']} has a fastest lap on StatsF1 but is not in the {prefix or 'race'} classification.")
        new = updates[row["rowid"]]
        new[f"{prefix}fastestlap"] = int(cells[0]) if cells[0].isdigit() else None
        new[f"{prefix}fastestlap_time"] = cells[4].replace("'", ":")
        new[f"{prefix}fastestlapinseconds"] = tts(new[f"{prefix}fastestlap_time"])
        new[f"{prefix}fastestlap_gap"] = cells[5]
        new[f"{prefix}fastestlapgapinseconds"] = tts(cells[5])
        new[f"{prefix}fastestlap_lap"] = int(cells[6]) if cells[6].isdigit() else None


def apply_api_times(details, rows, updates, prefix):
    """
    Motorsport Stats gives times and gaps for drivers StatsF1 prints none for (retirements,
    lapped cars). Only fills columns that are still empty, in writedb.py's text format.
    """
    time_key, seconds_key = f"{prefix}time", f"{prefix}timeinseconds"
    gap_key, gap_seconds_key = f"{prefix}gap", f"{prefix}gapinseconds"
    for driver in details:
        car_number = int(driver["carNumber"])
        for row in rows:
            if row["number"] != car_number or row["substituteorthirddriver"] or row["rowid"] not in updates:
                continue
            new = updates[row["rowid"]]
            if new[time_key] is None:
                milliseconds = int(driver["time"])
                if milliseconds == 0:
                    continue
                new[time_key] = api_time_string(milliseconds)
                new[seconds_key] = quantize(milliseconds / 1000)
            if new[gap_key] is None:
                milliseconds = int(driver["gap"]["timeToLead"])
                if milliseconds != 0:
                    new[gap_key] = api_time_string(milliseconds)
                    new[gap_seconds_key] = quantize(milliseconds / 1000)


def compute_intervals(rows, updates, position_key, gap_key, interval_key):
    """Gap to the car in front, from the gaps to the leader. Same walk as writedb.py's calculate_intervals."""
    ordered = [updates[row["rowid"]] for row in rows if row["rowid"] in updates and updates[row["rowid"]].get(position_key)]
    ordered.sort(key=lambda new: new[position_key])
    previous_gap = None
    for new in ordered:
        if new.get(gap_key) is not None:
            new[interval_key] = None if previous_gap is None else quantize(new[gap_key] - previous_gap)
            previous_gap = new[gap_key]
        else:
            new[interval_key] = None


def assign_penalties(penalties, rows, updates):
    """Attach the penalty JSON to the first row of each penalised driver; rows without penalties get NULL."""
    for row in rows:
        updates.setdefault(row["rowid"], {})
        updates[row["rowid"]]["penalties"] = None
        updates[row["rowid"]]["sprint_penalties"] = None
    collected = {}
    for penalty in penalties:
        row = find_row(rows, penalty["driver"], source="Penalties")
        key = "sprint_penalties" if penalty["is_sprint"] else "penalties"
        entry = {"penalty": penalty["penalty"], "reason": penalty["reason"], "type": penalty["type"]}
        if "lost_position" in penalty:
            entry["lost_position"] = penalty["lost_position"]
        collected.setdefault((row["rowid"], key), []).append(entry)
    for (rowid, key), entries in collected.items():
        updates[rowid][key] = json.dumps(entries)


def parse_in_season_progress(soup):
    """championnat.aspx -> (drivers, constructors) standings after that Grand Prix."""
    drivers, constructors = [], []
    drivers_div = soup.find("div", id="ctl00_CPH_Main_DIV_ChpPilote")
    if drivers_div and drivers_div.find("table", class_="datatable"):
        for tr in drivers_div.find("table", class_="datatable").find("tbody").find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) == 3:
                position_text = cells[0].get_text(strip=True).replace(".", "")
                drivers.append({
                    "position": int(position_text) if position_text.isdigit() else (drivers[-1]["position"] if drivers else None),
                    "driver": cells[1].get_text(strip=True),
                    "points": float(cells[2].get_text(strip=True)),
                })
    constructors_div = soup.find("div", id="ctl00_CPH_Main_DIV_ChpConstructeur")
    if constructors_div and constructors_div.find("table", class_="datatable"):
        for tr in constructors_div.find("table", class_="datatable").find("tbody").find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) == 3:
                links = cells[1].find_all("a")
                position_text = cells[0].get_text(strip=True).replace(".", "")
                constructors.append({
                    "position": int(position_text) if position_text.isdigit() else (constructors[-1]["position"] if constructors else None),
                    "constructor": links[0].get_text(strip=True) if links else "",
                    "engine": links[1].get_text(strip=True) if len(links) > 1 else (links[0].get_text(strip=True) if links else ""),
                    "points": float(cells[2].get_text(strip=True)),
                })
    return drivers, constructors


def parse_points_cell(text, race_type):
    if text == "-":
        return (0, None, race_type)
    if text == "":
        return (None, None, race_type)
    if text.startswith("(") and text.endswith(")"):
        return (float(text[1:-1].replace(",", ".")), True, race_type)
    return (float(text.replace(",", ".")), False, race_type)


def parse_championship_table(table, identity):
    """
    The season page's drivers or constructors table -> list of standings entries with a
    race-by-race breakdown, in the shape writedb.py stores as RaceByRace JSON.
    """
    trs = table.find_all("tr")
    header = trs[0].find_all("td")
    if header[-1].get_text(strip=True) == "Out of" and header[-2].get_text(strip=True) == "Pts":
        race_headers, has_out_of = header[1:-2], True
    elif header[-1].get_text(strip=True) == "Pts":
        race_headers, has_out_of = header[1:-1], False
    else:
        raise ValueError("Unrecognised championship table header on the StatsF1 season page.")
    standings = []
    for tr in trs[1:]:
        cells = tr.find_all("td")
        # Separator rows span the table with one cell (writedb.py checks colspan == '27', which is only right for 24-race seasons).
        if len(cells) < 3 or cells[0].get("colspan"):
            continue
        position_text = cells[0].get_text(strip=True).replace(".", "")
        entry = {"position": int(position_text) if position_text.isdigit() else standings[-1]["position"]}
        entry.update(identity(cells[1]))
        if has_out_of:
            entry["points"] = float(cells[-2].get_text(strip=True))
            out_of = cells[-1].get_text(strip=True)
            entry["outof"] = float(out_of) if out_of != "" else entry["points"]
            race_cells = cells[2:-2]
        else:
            entry["points"] = float(cells[-1].get_text(strip=True))
            entry["outof"] = None
            race_cells = cells[2:-1]
        race_by_race = {}
        for i, cell in enumerate(race_cells):
            span = race_headers[i].find("span", class_=["codegp", "codesp"])
            race_type = "gp" if span["class"][0] == "codegp" else "sp"
            race_by_race[span["title"]] = parse_points_cell(cell.get_text(strip=True), race_type)
        entry["racebyrace"] = race_by_race
        standings.append(entry)
    return standings


def get_tiebreaker_key(entry):
    results = sorted([data[0] for data in entry["racebyrace"].values() if data[0] is not None], reverse=True)
    return tuple(results)


def apply_mathematical_locks(standings, points_system):
    """Blank the position of anyone who can still move; copied from writedb.py."""
    if not standings:
        return standings
    race_names = list(standings[0]["racebyrace"].keys())
    future_gps = future_sprints = 0
    for race in race_names:
        if all(entry["racebyrace"][race][0] is None for entry in standings):
            if race == "Indianapolis":
                continue
            race_type = standings[0]["racebyrace"][race][2]
            if race_type == "gp":
                future_gps += 1
            elif race_type == "sp":
                future_gps += 1
                future_sprints += 1
    if future_gps == 0 and future_sprints == 0:
        return standings

    gp_scores = points_system.get("grandprix") or {}
    gp_positions = sorted([v for k, v in gp_scores.items() if k.isdigit()], reverse=True)
    max_gp = gp_positions[0] + (gp_positions[1] if len(gp_positions) > 1 else 0) + gp_scores.get("Fastest Lap", 0)
    sp_scores = points_system.get("sprint") or {}
    sp_positions = sorted([v for k, v in sp_scores.items() if k.isdigit()], reverse=True)
    max_sp = 0
    if sp_positions:
        max_sp = sp_positions[0] + (sp_positions[1] if len(sp_positions) > 1 else 0) + sp_scores.get("Fastest Lap", 0)
    total_remaining = (future_gps * max_gp) + (future_sprints * max_sp)

    n = len(standings)
    for i in range(n):
        me = standings[i]
        locked = True
        if i > 0:
            ahead = standings[i - 1]
            my_max = me["points"] + total_remaining
            if my_max > ahead["points"]:
                locked = False
            elif my_max == ahead["points"] and get_tiebreaker_key(me) > get_tiebreaker_key(ahead):
                locked = False
        if i < n - 1:
            behind = standings[i + 1]
            if behind["points"] + total_remaining >= me["points"]:
                locked = False
        if not locked:
            me["position"] = None
    return standings


# ---------------------------------------------------------------------------------------------
# Database steps
# ---------------------------------------------------------------------------------------------
def load_grand_prix(cur, name):
    cur.execute("SELECT ID, Season, GrandPrixName, RoundNumber, SprintWeekend FROM GrandsPrix WHERE lower(GrandPrixName) = lower(?)", (name,))
    found = cur.fetchall()
    if len(found) != 1:
        raise ValueError(f"Expected exactly one Grand Prix named '{name}' in GrandsPrix, found {len(found)}.")
    gp_id, season, gp_name, round_number, sprint_weekend = found[0]
    return {"id": gp_id, "season": season, "name": gp_name, "round": round_number, "sprint": bool(sprint_weekend)}


def load_result_rows(cur, gp_id):
    cur.execute("SELECT rowid, * FROM GrandPrixResults WHERE grandprixid = ? ORDER BY rowid", (gp_id,))
    columns = [d[0] for d in cur.description]
    rows = [dict(zip(columns, values)) for values in cur.fetchall()]
    if not rows:
        raise ValueError(f"No GrandPrixResults rows for Grand Prix ID {gp_id}.")
    return rows


def season_grand_prix_links(season_soup, season):
    gp_div = season_soup.find("div", class_="gpaffiche")
    if gp_div is None:
        raise ValueError(f"No Grand Prix list found on the StatsF1 {season} season page.")
    return [a["href"] for a in BeautifulSoup(str(gp_div), "html.parser").find_all("a")]


def motorsportstats_session_slugs(gp):
    """The Motorsport Stats race and sprint session slugs for this Grand Prix, found the way writedb.py finds them."""
    calendar = fetch_json(f"https://motorsportstats.com/_next/data/{MOTORSPORTSTATS_BUILD}/series/fia-formula-one-world-championship/calendar/{gp['season']}.json")
    events = [
        event["name"].replace("  ", " ")
        for event in calendar["pageProps"]["calendar"]["events"]
        if "season test" not in event["name"].lower() and event.get("status", "").lower() != "cancelled"
    ]
    event_slug = unicodedata.normalize("NFKD", events[gp["round"] - 1].replace(" ", "-").lower().replace("'", "-")).encode("ascii", "ignore").decode("ascii")
    info = fetch_json(f"https://motorsportstats.com/_next/data/{MOTORSPORTSTATS_BUILD}/results/fia-formula-one-world-championship/{gp['season']}/{event_slug}/info.json")
    # Like writedb.py, only sessions Motorsport Stats says have results: the classification endpoint answers an empty body otherwise.
    slugs = [session["session"]["slug"] for session in info["pageProps"]["sessions"] if session["hasResults"] and not session["cancelled"]]
    race = [slug for slug in slugs if slug.endswith("_race")]
    sprint = [slug for slug in slugs if slug.endswith("_sprint")]
    return (race[0] if race else None), (sprint[0] if sprint else None)


def describe(value):
    return "NULL" if value is None else repr(value)


def write_result_updates(cur, rows, updates, label):
    """UPDATE the changed columns of each GrandPrixResults row and print what changed."""
    changed_rows = 0
    for row in rows:
        new = updates.get(row["rowid"])
        if not new:
            continue
        changes = {column: value for column, value in new.items() if value != row[column]}
        if not changes:
            continue
        changed_rows += 1
        print(f"  {row['driver']} (#{row['number']}):")
        for column, value in changes.items():
            print(f"      {column}: {describe(row[column])} -> {describe(value)}")
        assignments = ", ".join(f"{column} = ?" for column in changes)
        cur.execute(f"UPDATE GrandPrixResults SET {assignments} WHERE rowid = ?", (*changes.values(), row["rowid"]))
    print(f"  {label}: {changed_rows} of {len(rows)} rows changed.")


def refresh_in_season_progress(cur, gp, gp_links, season_driver_ids):
    """Re-scrape the standings after this Grand Prix and after every later one of the season in the database."""
    cur.execute("SELECT ID, GrandPrixName, RoundNumber FROM GrandsPrix WHERE Season = ? AND RoundNumber >= ? ORDER BY RoundNumber", (gp["season"], gp["round"]))
    later = cur.fetchall()
    for other_id, other_name, other_round in later:
        if other_round > len(gp_links):
            raise ValueError(f"{other_name} is round {other_round} but StatsF1 lists only {len(gp_links)} Grands Prix for {gp['season']}.")
        soup = fetch_html(STATSF1 + gp_links[other_round - 1].replace(".aspx", "/championnat.aspx"))
        drivers, constructors = parse_in_season_progress(soup)

        cur.execute("SELECT Driver, PositionAtThisPoint, PointsAtThisPoint FROM InSeasonProgressDrivers WHERE GrandPrixID = ?", (other_id,))
        old_drivers = {driver: (position, points) for driver, position, points in cur.fetchall()}
        cur.execute("SELECT Constructor, Engine, PositionAtThisPoint, PointsAtThisPoint FROM InSeasonProgressConstructors WHERE GrandPrixID = ?", (other_id,))
        old_constructors = {(constructor, engine): (position, points) for constructor, engine, position, points in cur.fetchall()}
        if not drivers and old_drivers:
            raise ValueError(f"StatsF1 has no in-season standings for {other_name} but the database does; refusing to delete them.")
        if not drivers:
            print(f"  {other_name}: no in-season standings on StatsF1, nothing to refresh.")
            continue

        cur.execute("DELETE FROM InSeasonProgressDrivers WHERE GrandPrixID = ?", (other_id,))
        cur.execute("DELETE FROM InSeasonProgressConstructors WHERE GrandPrixID = ?", (other_id,))
        changed = []
        for entry in drivers:
            db_name = find_by_name(entry["driver"], season_driver_ids, source=f"In-season standings after {other_name}")
            cur.execute(
                "INSERT INTO InSeasonProgressDrivers (GrandPrix, PositionAtThisPoint, Driver, PointsAtThisPoint, GrandPrixID, DriverID) VALUES (?,?,?,?,?,?)",
                (other_name, entry["position"], db_name, entry["points"], other_id, season_driver_ids[db_name]),
            )
            if old_drivers.get(db_name) != (entry["position"], entry["points"]):
                changed.append(f"{db_name} {old_drivers.get(db_name, ('-', '-'))} -> ({entry['position']}, {entry['points']})")
        for entry in constructors:
            cur.execute("SELECT ID FROM Constructors WHERE ConstructorName = ?", (entry["constructor"],))
            constructor = cur.fetchone()
            cur.execute("SELECT ID FROM Engines WHERE EngineName = ?", (entry["engine"],))
            engine = cur.fetchone()
            if constructor is None or engine is None:
                raise ValueError(f"In-season standings after {other_name}: constructor '{entry['constructor']}' / engine '{entry['engine']}' not found in the database.")
            cur.execute(
                "INSERT INTO InSeasonProgressConstructors (GrandPrix, PositionAtThisPoint, Constructor, Engine, PointsAtThisPoint, GrandPrixID, ConstructorID, EngineID) VALUES (?,?,?,?,?,?,?,?)",
                (other_name, entry["position"], entry["constructor"], entry["engine"], entry["points"], other_id, constructor[0], engine[0]),
            )
            key = (entry["constructor"], entry["engine"])
            if old_constructors.get(key) != (entry["position"], entry["points"]):
                changed.append(f"{entry['constructor']}/{entry['engine']} {old_constructors.get(key, ('-', '-'))} -> ({entry['position']}, {entry['points']})")
        print(f"  {other_name}: rewrote {len(drivers)} driver and {len(constructors)} constructor rows" + (f"; changed: {'; '.join(changed)}" if changed else "; no changes"))


def refresh_championship(cur, gp, season_soup, season_driver_ids):
    """
    Re-parse the season's final/current standings. Only safe when the database holds every Grand
    Prix StatsF1 already has a result for; otherwise the totals would include un-scraped races.
    """
    drivers_table = season_soup.find("table", id="ctl00_CPH_Main_TBL_CHP_Drv")
    constructors_table = season_soup.find("table", id="ctl00_CPH_Main_TBL_CHP_Cst")
    if drivers_table is None:
        raise ValueError(f"No drivers' championship table on the StatsF1 {gp['season']} season page.")

    def driver_identity(cell):
        # The season table abbreviates names ("K. ANTONELLI"): first initial + surname, as writedb.py matches them.
        abbreviated = cell.get_text(strip=True)
        parts = abbreviated.lower().replace(".", "").split()
        if len(parts) < 2:
            raise ValueError(f"Cannot split championship driver name '{abbreviated}'.")
        initial, surname = normalize_name(parts[0][0]), normalize_name(" ".join(parts[1:]))
        matches = [name for name in season_driver_ids if normalize_name(name).startswith(initial) and normalize_name(name).endswith(surname)]
        if not matches:
            cur.execute("SELECT Driver FROM DriversChampionship WHERE Season = ?", (gp["season"],))
            matches = [name for (name,) in cur.fetchall() if normalize_name(name).startswith(initial) and normalize_name(name).endswith(surname)]
        if len(set(matches)) != 1:
            raise ValueError(f"Championship driver '{abbreviated}' matches {sorted(set(matches))} in season {gp['season']}; expected exactly one.")
        return {"driver": matches[0]}

    def constructor_identity(cell):
        links = cell.find_all("a")
        return {"constructor": links[0].get_text(strip=True), "engine": links[1].get_text(strip=True) if len(links) == 2 else links[0].get_text(strip=True)}

    drivers = parse_championship_table(drivers_table, driver_identity)
    constructors = parse_championship_table(constructors_table, constructor_identity) if constructors_table else []

    race_names = list(drivers[0]["racebyrace"].keys())
    completed = [race for race in race_names if any(entry["racebyrace"][race][0] is not None for entry in drivers)]
    cur.execute("SELECT COUNT(*) FROM GrandsPrix WHERE Season = ?", (gp["season"],))
    in_database = cur.fetchone()[0]
    if len(completed) != in_database:
        print(f"  StatsF1 has results for {len(completed)} Grands Prix of {gp['season']} but the database holds {in_database}.")
        print("  DriversChampionship / ConstructorsChampionship were left alone: run writedb.py to scrape the missing Grand Prix; it rewrites the championship tables.")
        return

    cur.execute("SELECT GrandPrixPointsSystemDrivers, SprintPointsSystemDrivers, GrandPrixPointsSystemConstructors, SprintPointsSystemConstructors FROM Seasons WHERE Season = ?", (gp["season"],))
    gp_drivers, sp_drivers, gp_constructors, sp_constructors = [json.loads(value) if value else None for value in cur.fetchone()]
    drivers = apply_mathematical_locks(drivers, {"grandprix": gp_drivers, "sprint": sp_drivers})
    constructors = apply_mathematical_locks(constructors, {"grandprix": gp_constructors, "sprint": sp_constructors})

    cur.execute("SELECT Driver, Position, Points FROM DriversChampionship WHERE Season = ?", (gp["season"],))
    old_drivers = {driver: (position, points) for driver, position, points in cur.fetchall()}
    cur.execute("DELETE FROM DriversChampionship WHERE Season = ?", (gp["season"],))
    changed = []
    for entry in drivers:
        driver_id = season_driver_ids.get(entry["driver"])
        if driver_id is None:
            cur.execute("SELECT ID FROM Drivers WHERE Name = ?", (entry["driver"],))
            driver_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO DriversChampionship (ID, Season, Position, Driver, Points, OutOf, RaceByRace, DriverID) VALUES (?,?,?,?,?,?,?,?)",
            (str(gp["season"]) + entry["driver"], gp["season"], entry["position"], entry["driver"], entry["points"], entry["outof"], json.dumps(entry["racebyrace"]), driver_id),
        )
        if old_drivers.get(entry["driver"]) != (entry["position"], entry["points"]):
            changed.append(f"{entry['driver']} {old_drivers.get(entry['driver'], ('-', '-'))} -> ({entry['position']}, {entry['points']})")
    print(f"  DriversChampionship {gp['season']}: rewrote {len(drivers)} rows" + (f"; changed: {'; '.join(changed)}" if changed else "; no changes"))

    if constructors:
        cur.execute("SELECT Constructor, Engine, Position, Points FROM ConstructorsChampionship WHERE Season = ?", (gp["season"],))
        old_constructors = {(constructor, engine): (position, points) for constructor, engine, position, points in cur.fetchall()}
        cur.execute("DELETE FROM ConstructorsChampionship WHERE Season = ?", (gp["season"],))
        changed = []
        for entry in constructors:
            cur.execute("SELECT ID FROM Constructors WHERE ConstructorName = ?", (entry["constructor"],))
            constructor = cur.fetchone()
            cur.execute("SELECT ID FROM Engines WHERE EngineName = ?", (entry["engine"],))
            engine = cur.fetchone()
            if constructor is None or engine is None:
                raise ValueError(f"Championship {gp['season']}: constructor '{entry['constructor']}' / engine '{entry['engine']}' not found in the database.")
            cur.execute(
                "INSERT INTO ConstructorsChampionship (ID, Season, Position, Constructor, Engine, Points, OutOf, RaceByRace, ConstructorID, EngineID) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (str(gp["season"]) + entry["constructor"] + entry["engine"], gp["season"], entry["position"], entry["constructor"], entry["engine"], entry["points"], entry["outof"], json.dumps(entry["racebyrace"]), constructor[0], engine[0]),
            )
            key = (entry["constructor"], entry["engine"])
            if old_constructors.get(key) != (entry["position"], entry["points"]):
                changed.append(f"{entry['constructor']}/{entry['engine']} {old_constructors.get(key, ('-', '-'))} -> ({entry['position']}, {entry['points']})")
        print(f"  ConstructorsChampionship {gp['season']}: rewrote {len(constructors)} rows" + (f"; changed: {'; '.join(changed)}" if changed else "; no changes"))


# ---------------------------------------------------------------------------------------------
# Standings derived from the database (seasons in which every score counts, 1991 onwards)
# ---------------------------------------------------------------------------------------------
def season_counts_all_scores(cur, season):
    cur.execute("SELECT DriversRacesCounted, ConstructorsRacesCounted, PointsOnlyForTopScoringCar FROM Seasons WHERE Season = ?", (season,))
    drivers_rule, constructors_rule, top_car_only = cur.fetchone()
    return (drivers_rule or "").startswith("All scores") and (constructors_rule or "").startswith("All scores") and not top_car_only


def points_deltas(rows, updates):
    """Change in championship points this run causes, per driver and per constructor/engine."""
    driver_deltas, constructor_deltas = {}, {}
    for row in rows:
        new = updates.get(row["rowid"], {})
        old_points = (row["racepoints"] or 0) + (row["sprintpoints"] or 0)
        new_points = (new.get("racepoints", row["racepoints"]) or 0) + (new.get("sprintpoints", row["sprintpoints"]) or 0)
        delta = quantize(new_points - old_points)
        if delta:
            driver_key, constructor_key = (row["driverid"],), (row["constructorid"], row["engineid"])
            driver_deltas[driver_key] = quantize(driver_deltas.get(driver_key, 0) + delta)
            constructor_deltas[constructor_key] = quantize(constructor_deltas.get(constructor_key, 0) + delta)
    return driver_deltas, constructor_deltas


def competition_positions(points_by_key):
    """In-season convention on StatsF1: tied entities share a position (1, 2, 2, 4)."""
    values = list(points_by_key.values())
    return {key: 1 + sum(1 for other in values if other > points) for key, points in points_by_key.items()}


def refresh_in_season_table(cur, table, id_columns, name_columns, other_id, other_name, deltas, lookup_names):
    """
    Apply point deltas to one in-season standings table for one Grand Prix and re-rank it.
    Only scorers are listed: an entity reaching positive points gets a row, one dropping to zero loses it.
    """
    id_list, name_list = ", ".join(id_columns), ", ".join(name_columns)
    n_ids, n_names = len(id_columns), len(name_columns)
    cur.execute(f"SELECT rowid, {id_list}, {name_list}, PositionAtThisPoint, PointsAtThisPoint FROM {table} WHERE GrandPrixID = ? ORDER BY rowid", (other_id,))
    existing = {}
    for record in cur.fetchall():
        key = tuple(record[1:1 + n_ids])
        if key in existing:
            cur.execute(f"DELETE FROM {table} WHERE rowid = ?", (record[0],))  # duplicate left by an earlier double scrape
            continue
        existing[key] = {"rowid": record[0], "names": tuple(record[1 + n_ids:1 + n_ids + n_names]), "old": (record[-2], record[-1]), "points": record[-1]}
    for key, delta in deltas.items():
        if key in existing:
            existing[key]["points"] = quantize(existing[key]["points"] + delta)
        elif delta > 0:
            existing[key] = {"rowid": None, "names": lookup_names(key), "old": None, "points": quantize(delta)}
    positions = competition_positions({key: entry["points"] for key, entry in existing.items() if entry["points"] > 0})
    changed = []
    for key, entry in existing.items():
        label = "/".join(entry["names"])
        if entry["points"] <= 0:
            if entry["rowid"] is not None:
                cur.execute(f"DELETE FROM {table} WHERE rowid = ?", (entry["rowid"],))
                changed.append(f"{label} {entry['old']} -> removed")
            continue
        new = (positions[key], entry["points"])
        if entry["rowid"] is None:
            placeholders = ", ".join("?" * (4 + n_ids + n_names))
            cur.execute(
                f"INSERT INTO {table} (GrandPrix, PositionAtThisPoint, {name_list}, PointsAtThisPoint, GrandPrixID, {id_list}) VALUES ({placeholders})",
                (other_name, new[0], *entry["names"], new[1], other_id, *key),
            )
            changed.append(f"{label} added -> {new}")
        elif new != entry["old"]:
            cur.execute(f"UPDATE {table} SET PositionAtThisPoint = ?, PointsAtThisPoint = ? WHERE rowid = ?", (new[0], new[1], entry["rowid"]))
            changed.append(f"{label} {entry['old']} -> {new}")
    return changed


def refresh_in_season_progress_from_db(cur, gp, driver_deltas, constructor_deltas):
    """Carry this run's point changes through the standings after this Grand Prix and every later one of the season."""
    if not driver_deltas and not constructor_deltas:
        print("  No championship points changed, so the in-season standings stay as they are.")
        return
    cur.execute("SELECT ID, GrandPrixName FROM GrandsPrix WHERE Season = ? AND RoundNumber >= ? ORDER BY RoundNumber", (gp["season"], gp["round"]))
    for other_id, other_name in cur.fetchall():
        changed = refresh_in_season_table(
            cur, "InSeasonProgressDrivers", ["DriverID"], ["Driver"], other_id, other_name, driver_deltas,
            lambda key: (cur.execute("SELECT Name FROM Drivers WHERE ID = ?", key).fetchone()[0],),
        )
        changed += refresh_in_season_table(
            cur, "InSeasonProgressConstructors", ["ConstructorID", "EngineID"], ["Constructor", "Engine"], other_id, other_name, constructor_deltas,
            lambda key: (
                cur.execute("SELECT ConstructorName FROM Constructors WHERE ID = ?", (key[0],)).fetchone()[0],
                cur.execute("SELECT EngineName FROM Engines WHERE ID = ?", (key[1],)).fetchone()[0],
            ),
        )
        print(f"  {other_name}: " + ("; ".join(changed) if changed else "no changes"))


def countback_key(finishing_positions):
    """StatsF1 breaks championship ties on race results: most wins, then most second places, and so on."""
    return tuple(-finishing_positions.count(place) for place in range(1, 31))


def rank_championship(entries, results_by_key):
    """
    Distinct positions by points, then countback, then the stored order. An entry StatsF1 ranks out of
    points order (a driver excluded from the championship, e.g. Schumacher 1997) keeps its stored position.
    """
    stored = [entry for entry in entries if entry["position"] is not None]
    pinned = {
        entry["key"] for entry in stored
        if any(other["points"] < entry["points"] and other["position"] < entry["position"] for other in stored)
    }
    pool = [entry for entry in entries if entry["key"] not in pinned]
    pool.sort(key=lambda entry: (
        -entry["points"],
        countback_key(results_by_key.get(entry["key"], [])),
        entry["position"] if entry["position"] is not None else 10 ** 6,
        entry["order"],
    ))
    for i, entry in enumerate(pool):
        entry["position"] = i + 1
    return pool, [entry for entry in entries if entry["key"] in pinned]


def refresh_championship_table(cur, gp, table, id_columns, name_columns, result_columns, results_by_key, points_system):
    """
    Reconcile one championship table with GrandPrixResults for this Grand Prix: the RaceByRace cell of
    the race is replaced, the difference is applied to the total, positions are re-ranked and the
    mathematical locks re-applied. Every other race's cell is left exactly as StatsF1 gave it.
    """
    id_list, name_list = ", ".join(id_columns), ", ".join(name_columns)
    n_ids, n_names = len(id_columns), len(name_columns)
    cur.execute(f"SELECT rowid, {id_list}, {name_list}, Position, Points, OutOf, RaceByRace FROM {table} WHERE Season = ? ORDER BY rowid", (gp["season"],))
    records = cur.fetchall()
    if not records:
        print(f"  {table} has no rows for {gp['season']}; nothing to update.")
        return
    entries = []
    for order, record in enumerate(records):
        entries.append({
            "rowid": record[0], "key": tuple(record[1:1 + n_ids]), "label": "/".join(record[1 + n_ids:1 + n_ids + n_names]),
            "position": record[-4], "points": record[-3], "outof": record[-2], "racebyrace": json.loads(record[-1]),
            "order": order, "old": (record[-4], record[-3]),
        })
    race_keys = list(entries[0]["racebyrace"].keys())
    if gp["round"] > len(race_keys):
        raise ValueError(f"{table}: RaceByRace lists {len(race_keys)} races but {gp['name']} is round {gp['round']}.")
    race_key = race_keys[gp["round"] - 1]
    race_type = entries[0]["racebyrace"][race_key][2]
    if (race_type == "sp") != gp["sprint"]:
        raise ValueError(f"{table}: RaceByRace column '{race_key}' (round {gp['round']}) is {'a sprint' if race_type == 'sp' else 'not a sprint'} weekend, unlike {gp['name']}; the round order does not line up.")

    group = ", ".join(result_columns)
    cur.execute(
        f"SELECT {group}, SUM(COALESCE(racepoints, 0) + COALESCE(sprintpoints, 0)) FROM GrandPrixResults "
        f"WHERE grandprixid = ? AND substituteorthirddriver = 0 GROUP BY {group}",
        (gp["id"],),
    )
    scored = {tuple(record[:-1]): quantize(record[-1]) for record in cur.fetchall()}
    for entry in entries:
        old_value = entry["racebyrace"].get(race_key)
        if entry["key"] in scored:
            points = scored.pop(entry["key"])
            new_value = [points, False, race_type] if points > 0 else [0, None, race_type]
        else:
            new_value = [None, None, race_type]
        delta = quantize((new_value[0] or 0) - ((old_value[0] if old_value else None) or 0))
        if delta:
            entry["points"] = quantize(entry["points"] + delta)
            if entry["outof"] is not None:
                entry["outof"] = entry["points"]
        entry["racebyrace"][race_key] = new_value
    for key, points in scored.items():
        if points > 0:
            print(f"  WARNING: {table}: {key} scored {points} at {gp['name']} but has no {gp['season']} row; left out.")

    pool, pinned = rank_championship(entries, results_by_key)
    pool = apply_mathematical_locks(pool, points_system)
    changed = []
    for entry in pool + pinned:
        cur.execute(
            f"UPDATE {table} SET Position = ?, Points = ?, OutOf = ?, RaceByRace = ? WHERE rowid = ?",
            (entry["position"], entry["points"], entry["outof"], json.dumps(entry["racebyrace"]), entry["rowid"]),
        )
        new = (entry["position"], entry["points"])
        if new != entry["old"]:
            changed.append(f"{entry['label']} {entry['old']} -> {new}")
    print(f"  {table} {gp['season']}: " + ("; ".join(changed) if changed else "no changes"))


def refresh_championship_from_db(cur, gp):
    cur.execute("SELECT GrandPrixPointsSystemDrivers, SprintPointsSystemDrivers, GrandPrixPointsSystemConstructors, SprintPointsSystemConstructors FROM Seasons WHERE Season = ?", (gp["season"],))
    gp_drivers, sp_drivers, gp_constructors, sp_constructors = [json.loads(value) if value else None for value in cur.fetchone()]
    cur.execute("SELECT r.driverid, r.constructorid, r.engineid, r.raceposition FROM GrandPrixResults r JOIN GrandsPrix g ON g.ID = r.grandprixid WHERE g.Season = ? AND r.raceposition IS NOT NULL", (gp["season"],))
    driver_results, constructor_results = {}, {}
    for driver_id, constructor_id, engine_id, position in cur.fetchall():
        driver_results.setdefault((driver_id,), []).append(position)
        constructor_results.setdefault((constructor_id, engine_id), []).append(position)
    refresh_championship_table(cur, gp, "DriversChampionship", ["DriverID"], ["Driver"], ["driverid"], driver_results, {"grandprix": gp_drivers, "sprint": sp_drivers})
    refresh_championship_table(cur, gp, "ConstructorsChampionship", ["ConstructorID", "EngineID"], ["Constructor", "Engine"], ["constructorid", "engineid"], constructor_results, {"grandprix": gp_constructors, "sprint": sp_constructors})


def flag_stats_for_update(cur, gp, rows):
    cur.execute("UPDATE Seasons SET needstatsupdate = 1 WHERE Season = ?", (gp["season"],))
    for table, column in [("Drivers", "driverid"), ("Teams", "teamid"), ("Constructors", "constructorid"), ("Chassis", "chassisid"),
                          ("Engines", "engineid"), ("EngineModels", "enginemodelid"), ("Tyres", "tyreid"), ("Nationalities", "nationalityid")]:
        ids = sorted({row[column] for row in rows if row[column] is not None})
        if ids:
            cur.execute(f"UPDATE {table} SET needstatsupdate = 1 WHERE ID IN ({','.join('?' * len(ids))})", ids)


# ---------------------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Re-sync one Grand Prix's result (and everything derived from it) with StatsF1.")
    parser.add_argument("racename", help='Grand Prix name as stored in GrandsPrix, e.g. "2026 Monaco Grand Prix"')
    parser.add_argument("--dry-run", action="store_true", help="scrape and show every change, but write nothing")
    parser.add_argument("--skip-stats", action="store_true", help="do not run updaters/update_stats_alone.py afterwards (entity stats stay flagged for the next writedb.py run)")
    parser.add_argument("--results-only", action="store_true", help="only rewrite GrandPrixResults/GrandsPrix; skip the in-season and championship standings (use only when points cannot have changed)")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} does not exist.")
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    gp = load_grand_prix(cur, args.racename)
    rows = load_result_rows(cur, gp["id"])
    print(f"{gp['name']} (ID {gp['id']}, round {gp['round']} of {gp['season']}{', sprint weekend' if gp['sprint'] else ''}): {len(rows)} result rows in the database.")

    season_soup = fetch_html(f"{STATSF1}/en/{gp['season']}.aspx")
    gp_links = season_grand_prix_links(season_soup, gp["season"])
    if gp["round"] > len(gp_links):
        raise ValueError(f"Round {gp['round']} requested but StatsF1 lists only {len(gp_links)} Grands Prix for {gp['season']}.")
    gp_base = STATSF1 + gp_links[gp["round"] - 1].replace(".aspx", "")

    # 1. Race
    print("Scraping the race classification...")
    race_soup = fetch_html(f"{gp_base}/classement.aspx")
    updates = parse_race_classification(race_soup, rows)
    penalties = parse_penalties(race_soup, is_sprint=False)
    notes = {"RaceResultNotes": parse_notes(race_soup)}
    parse_fastest_laps(fetch_html(f"{gp_base}/meilleur-tour.aspx"), rows, updates, prefix="")

    # 2. Sprint
    sprint_updates = {}
    if gp["sprint"]:
        print("Scraping the sprint classification...")
        sprint_soup = fetch_html(f"{gp_base}/sprint.aspx")
        sprint_updates = parse_sprint_classification(sprint_soup, rows)
        penalties += parse_penalties(sprint_soup, is_sprint=True)
        notes["SprintNotes"] = parse_notes(sprint_soup)
        parse_fastest_laps(fetch_html(f"{gp_base}/sprint.aspx?mt"), rows, sprint_updates, prefix="sprint")

    # 3. Times and gaps StatsF1 does not print, from Motorsport Stats
    if gp["id"] > FIRST_GRAND_PRIX_WITH_API_TIMES:
        race_slug, sprint_slug = motorsportstats_session_slugs(gp)
        if race_slug:
            apply_api_times(fetch_json(f"https://motorsportstats.com/api/results-classification?sessionSlug={race_slug}")["details"], rows, updates, prefix="race")
        else:
            print("  Motorsport Stats has no race session for this Grand Prix; retirement times stay as StatsF1 prints them.")
        if gp["sprint"]:
            if sprint_slug:
                apply_api_times(fetch_json(f"https://motorsportstats.com/api/results-classification?sessionSlug={sprint_slug}")["details"], rows, sprint_updates, prefix="sprint")
            else:
                print("  Motorsport Stats has no sprint session for this Grand Prix; sprint retirement times stay as StatsF1 prints them.")

    compute_intervals(rows, updates, "raceposition", "racegapinseconds", "raceinterval")
    compute_intervals(rows, updates, "fastestlap", "fastestlapgapinseconds", "fastestlapinterval")
    if gp["sprint"]:
        compute_intervals(rows, sprint_updates, "sprintposition", "sprintgapinseconds", "sprintinterval")
        compute_intervals(rows, sprint_updates, "sprintfastestlap", "sprintfastestlapgapinseconds", "sprintfastestlapinterval")
    for rowid, sprint_new in sprint_updates.items():
        updates.setdefault(rowid, {}).update(sprint_new)
    assign_penalties(penalties, rows, updates)

    # 4. Write
    print("GrandPrixResults:")
    write_result_updates(cur, rows, updates, gp["name"])
    for column, text in notes.items():
        cur.execute(f"SELECT {column} FROM GrandsPrix WHERE ID = ?", (gp["id"],))
        old_text = cur.fetchone()[0]
        if old_text != text:
            print(f"  GrandsPrix.{column}: {describe(old_text)} -> {text!r}")
        cur.execute(f"UPDATE GrandsPrix SET {column} = ? WHERE ID = ?", (text, gp["id"]))
    flag_stats_for_update(cur, gp, rows)

    if args.results_only:
        print("Standings skipped (--results-only).")
    elif season_counts_all_scores(cur, gp["season"]):
        driver_deltas, constructor_deltas = points_deltas(rows, updates)
        print("In-season standings (derived from the database):")
        refresh_in_season_progress_from_db(cur, gp, driver_deltas, constructor_deltas)
        print("Championship (derived from the database):")
        refresh_championship_from_db(cur, gp)
    else:
        print(f"{gp['season']} has dropped scores or top-car-only constructor points, so the standings are re-scraped from StatsF1.")
        cur.execute(
            "SELECT DISTINCT d.Name, d.ID FROM Drivers d JOIN GrandPrixResults r ON r.driverid = d.ID JOIN GrandsPrix g ON g.ID = r.grandprixid WHERE g.Season = ?",
            (gp["season"],),
        )
        season_driver_ids = dict(cur.fetchall())
        print("In-season standings:")
        refresh_in_season_progress(cur, gp, gp_links, season_driver_ids)
        print("Championship:")
        refresh_championship(cur, gp, season_soup, season_driver_ids)

    if args.dry_run:
        conn.rollback()
        conn.close()
        print("DRY RUN: nothing was written to the database.")
        return
    conn.commit()
    conn.close()
    print(f"{gp['name']} updated and committed.")

    if args.skip_stats:
        print("Stats not recomputed (--skip-stats); the affected entities are flagged with needstatsupdate = 1.")
        return
    print("Recomputing derived statistics with updaters/update_stats_alone.py...")
    subprocess.run([sys.executable, str(STATS_UPDATER)], cwd=str(ROOT), check=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    main()
