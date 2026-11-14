"""Refresh formula1db.com schedule times and historical qualifying for one Grand Prix.

Usage:
    python updaters/update_schedules_and_old_qualifying_results.py "1961 Monaco Grand Prix"
    python updaters/update_schedules_and_old_qualifying_results.py "1961 Monaco Grand Prix" --dry-run
    python updaters/update_schedules_and_old_qualifying_results.py --season 1961
    python updaters/update_schedules_and_old_qualifying_results.py --seasons 1961-1982
    python updaters/update_schedules_and_old_qualifying_results.py --races "1961 Monaco Grand Prix" "1961 Dutch Grand Prix"

Schedules are available for every season. The separately classified
old qualifying sessions are available from 1961 through 1982. Overall qualifying
values are only filled where the existing database has no value, matching writedb.py.
From 2006 the Q1/Q2/Q3 segments of knockout qualifying are refreshed as well, along
with the SQ1/SQ2/SQ3 segments of sprint qualifying.
"""

import argparse
import datetime
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "sessionresults.db"
FIRST_OLD_QUALIFYING_SEASON = 1961
LAST_OLD_QUALIFYING_SEASON = 1982
FIRST_KNOCKOUT_SEASON = 2006
sys.path.insert(0, str(ROOT))

from scrapers.scrape_schedules_and_old_qualifying_results import ScQScraper


def normalize_name(name):
    if not name:
        return ""
    if name.lower() == "gianmaria bruni":
        return "gimmi bruni"
    if name.lower() == "zhou guanyu":
        return "guanyu zhou"
    return unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode("ascii").replace("-", " ")


def scq_time(text):
    text = text.strip()
    return None if text in ("", "-", "?") else text


def scq_gap(text):
    text = text.strip()
    return None if text in ("", "-", "?") else float(text.replace("+", ""))


def time_in_seconds(text):
    if not text:
        return None
    parts = text.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return round(int(hours) * 3600 + int(minutes) * 60 + float(seconds), 3)
    if len(parts) == 2:
        minutes, seconds = parts
        return round(int(minutes) * 60 + float(seconds), 3)
    if len(parts) == 1:
        try:
            return round(float(parts[0]), 3)
        except ValueError:
            return None
    return None


def find_entrant(cur, row, grand_prix_id, grand_prix_name):
    cur.execute(
        "SELECT rowid, driver, number, substituteorthirddriver FROM GrandPrixResults WHERE grandprixid = ?",
        (grand_prix_id,),
    )
    entrants = cur.fetchall()
    name = normalize_name(row["Driver"].replace("*", ""))
    matches = [entry for entry in entrants if normalize_name(entry[1].replace("*", "")) == name]
    if len(matches) > 1:
        matches = [entry for entry in matches if str(entry[2]) == row["No."]]
    if not matches:
        matches = [entry for entry in entrants if str(entry[2]) == row["No."] and not entry[3]]
    if len(matches) != 1:
        raise ValueError(f"Could not match qualifying row {row} to exactly one entrant in {grand_prix_name}")
    return matches[0][0]


def save_schedule(cur, gp, schedule):
    for scheduled in schedule:
        name = scheduled["session"]
        start_utc = datetime.datetime.fromisoformat(scheduled["start_utc"].replace("Z", "+00:00")) if scheduled["start_utc"] else None
        end_local = datetime.datetime.fromisoformat(scheduled["end_local"]) if scheduled["end_local"] else None
        end_utc = end_local.astimezone(datetime.timezone.utc) if end_local else None
        start_local = datetime.datetime.fromisoformat(scheduled["start_local"]) if scheduled["start_local"] else None
        cur.execute(
            "SELECT ID, SessionNumber FROM Sessions WHERE GrandPrixID = ? AND SessionName = ? ORDER BY ID LIMIT 1",
            (gp["id"], name),
        )
        existing = cur.fetchone()
        if existing:
            session_id, number = existing
        else:
            cur.execute("SELECT COALESCE(MAX(SessionNumber), 0) + 1 FROM Sessions WHERE GrandPrixID = ?", (gp["id"],))
            number = cur.fetchone()[0]
            session_id = None

        values = (
            gp["name"], name, number, int(scheduled["cancelled"]),
            int(start_utc.timestamp()) if start_utc else None,
            int(end_utc.timestamp()) if end_utc else None,
            int(start_utc.timestamp() + start_local.utcoffset().total_seconds()) if start_local else None,
            int(end_utc.timestamp() + end_local.utcoffset().total_seconds()) if end_local else None,
            1 if start_utc else None, start_utc.isoformat() if start_utc else None,
            end_utc.isoformat() if end_utc else None, start_local.isoformat() if start_local else None,
            end_local.isoformat() if end_local else None, scheduled["timezone"], gp["id"],
        )
        if session_id is None:
            cur.execute(
                """INSERT INTO Sessions (GrandPrix, SessionName, SessionNumber, WasSessionCancelled,
                   StartTimeTimestampUTC, EndTimeTimestampUTC, StartTimeTimestamp, EndTimeTimestamp,
                   IfPreciseStartTime, StartTimeinDatetimeUTC, EndTimeinDatetimeUTC,
                   StartTimeinDatetime, EndTimeinDatetime, SessionTimezone, GrandPrixID)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values,
            )
        else:
            cur.execute(
                """UPDATE Sessions SET GrandPrix=?, SessionName=?, SessionNumber=?, WasSessionCancelled=?,
                   StartTimeTimestampUTC=COALESCE(?, StartTimeTimestampUTC),
                   EndTimeTimestampUTC=COALESCE(?, EndTimeTimestampUTC),
                   StartTimeTimestamp=COALESCE(?, StartTimeTimestamp),
                   EndTimeTimestamp=COALESCE(?, EndTimeTimestamp),
                   IfPreciseStartTime=COALESCE(?, IfPreciseStartTime),
                   StartTimeinDatetimeUTC=COALESCE(?, StartTimeinDatetimeUTC),
                   EndTimeinDatetimeUTC=COALESCE(?, EndTimeinDatetimeUTC),
                   StartTimeinDatetime=COALESCE(?, StartTimeinDatetime),
                   EndTimeinDatetime=COALESCE(?, EndTimeinDatetime),
                   SessionTimezone=COALESCE(?, SessionTimezone), GrandPrixID=? WHERE ID=?""",
                values + (session_id,),
            )


def apply_qualifying(cur, gp, qualifying, prefix="qualifying"):
    """prefix="sprint_qualifying" writes the SQ1/SQ2/SQ3 segments instead of Q1/Q2/Q3."""
    updated = 0
    for row in qualifying["overall"]:
        if "Driver_id" not in row:
            continue
        rowid = find_entrant(cur, row, gp["id"], gp["name"])
        lap_time = scq_time(row["Time"])
        values = {
            "qualifyingposition": int(row["Pos."]) if row["Pos."].isdigit() else None,
            "qualifyingtime": lap_time,
            "qualifyinggap": scq_time(row["Gap"]),
            "qualifyingtimeinseconds": time_in_seconds(lap_time),
            "qualifyinggapseconds": scq_gap(row["Gap"]),
            "qualifyinginterval": scq_gap(row["Interval"]),
        }
        cur.execute("SELECT qualifyingposition, qualifyingtime, qualifyinggap, qualifyingtimeinseconds, qualifyinggapseconds, qualifyinginterval FROM GrandPrixResults WHERE rowid=?", (rowid,))
        old = cur.fetchone()
        merged = tuple(previous if value is None else value for value, previous in zip(values.values(), old))
        if merged != old:
            cur.execute("""UPDATE GrandPrixResults SET qualifyingposition=?, qualifyingtime=?, qualifyinggap=?,
                qualifyingtimeinseconds=?, qualifyinggapseconds=?, qualifyinginterval=? WHERE rowid=?""", merged + (rowid,))
            updated += 1

    for number, rows in qualifying["sessions"].items():
        session_prefix = f"{prefix}{number}"
        columns = [f"{session_prefix}position", f"{session_prefix}time", f"{session_prefix}timeinseconds", f"{session_prefix}gap", f"{session_prefix}interval", f"{session_prefix}laps"]
        for row in rows:
            if "Driver_id" not in row:
                continue
            rowid = find_entrant(cur, row, gp["id"], gp["name"])
            lap_time = scq_time(row["Time"])
            values = {
                f"{session_prefix}position": int(row["Pos."]) if row["Pos."].isdigit() else None,
                f"{session_prefix}time": lap_time,
                f"{session_prefix}timeinseconds": time_in_seconds(lap_time),
                f"{session_prefix}gap": scq_gap(row["Gap"]),
                f"{session_prefix}interval": scq_gap(row["Interval"]),
                f"{session_prefix}laps": int(row["Laps"]) if row.get("Laps", "").isdigit() else None,
            }
            cur.execute(f"SELECT {', '.join(columns)} FROM GrandPrixResults WHERE rowid=?", (rowid,))
            old = cur.fetchone()
            stored = dict(zip(columns, old))
            # The session leader has no gap on formula1db.com; keep the one already stored.
            if values[f"{session_prefix}gap"] is None:
                values[f"{session_prefix}gap"] = stored[f"{session_prefix}gap"]
            values = tuple(values[column] for column in columns)
            if values != old:
                cur.execute(f"UPDATE GrandPrixResults SET {', '.join(c + '=?' for c in columns)} WHERE rowid=?", values + (rowid,))
                updated += 1
    return updated


def select_grands_prix(cur, race_names, seasons):
    if race_names:
        selected = []
        for name in race_names:
            cur.execute("SELECT ID, GrandPrixName, Season, RoundNumber FROM GrandsPrix WHERE GrandPrixName = ?", (name,))
            match = cur.fetchone()
            if not match:
                raise ValueError(f"Grand Prix {name!r} not found in GrandsPrix.")
            selected.append(match)
        return selected

    if seasons:
        first, last = seasons
        cur.execute(
            "SELECT ID, GrandPrixName, Season, RoundNumber FROM GrandsPrix WHERE Season BETWEEN ? AND ? ORDER BY Season, RoundNumber, ID",
            (first, last),
        )
        selected = cur.fetchall()
        if not selected:
            raise ValueError(f"No GrandsPrix found for seasons {first}-{last}.")
        return selected

    cur.execute(
        "SELECT ID, GrandPrixName, Season, RoundNumber FROM GrandsPrix WHERE Season = ? ORDER BY RoundNumber, ID",
        (LAST_OLD_QUALIFYING_SEASON,),
    )
    raise ValueError("Choose race names, --season YEAR, or --seasons FIRST-LAST.")


def main():
    parser = argparse.ArgumentParser(description="Refresh formula1db.com schedule times and old qualifying for one or more Grands Prix.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--races", nargs="+", metavar="RACE", help="one or more exact Grand Prix names as stored in GrandsPrix")
    selection.add_argument("--season", type=int, metavar="YEAR", help="refresh every Grand Prix in one season")
    selection.add_argument("--seasons", metavar="FIRST-LAST", help="refresh every Grand Prix in an inclusive season range")
    parser.add_argument("--dry-run", action="store_true", help="scrape and show changes, then roll back")
    args = parser.parse_args()
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} does not exist.")

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    seasons = None
    if args.season is not None:
        seasons = (args.season, args.season)
    elif args.seasons:
        parts = args.seasons.split("-")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            parser.error("--seasons must be an inclusive range such as 1961-1982")
        seasons = tuple(map(int, parts))
        if seasons[0] > seasons[1]:
            parser.error("--seasons range start must be no later than its end")

    gps = [
        {"id": row[0], "name": row[1], "season": row[2], "round": row[3]}
        for row in select_grands_prix(cur, args.races, seasons)
    ]
    for gp in gps:
        if gp["round"] is None:
            raise ValueError(f"{gp['name']} has no RoundNumber in the database.")

    print(f"Preparing to refresh {len(gps)} Grand Prix weekends.")
    scraper = None
    previous_gp = None
    try:
        for gp in gps:
            consecutive = (
                scraper is not None
                and previous_gp["season"] == gp["season"]
                and previous_gp["round"] + 1 == gp["round"]
            )
            if consecutive:
                race_url = scraper.go_to_next_race()
                if race_url is None:
                    raise RuntimeError(f"formula1db.com has no race after {previous_gp['season']} round {previous_gp['round']}.")
            else:
                if scraper is not None:
                    scraper.close_session()
                scraper = ScQScraper()
                scraper.launch(gp["season"], gp["round"])

            if f"/races/{gp['season']}-" not in scraper.race_page:
                raise RuntimeError(f"Expected a {gp['season']} race page for round {gp['round']}, got {scraper.race_page}")
            schedule = scraper.scrape_schedule()
            print(f"Refreshing {len(schedule)} scheduled sessions for {gp['name']}.")
            save_schedule(cur, gp, schedule)
            if FIRST_OLD_QUALIFYING_SEASON <= gp["season"] <= LAST_OLD_QUALIFYING_SEASON:
                qualifying = scraper.scrape_qualifying(schedule=schedule)
                changed = apply_qualifying(cur, gp, qualifying)
                print(f"Refreshed historical qualifying values in {changed} entrant rows.")
            elif gp["season"] >= FIRST_KNOCKOUT_SEASON:
                qualifying = scraper.scrape_qualifying(schedule=schedule, overall=False)
                changed = apply_qualifying(cur, gp, qualifying)
                print(f"Refreshed Q1/Q2/Q3 values in {changed} entrant rows.")
                sprint_qualifying = scraper.scrape_sprint_qualifying(schedule=schedule)
                changed = apply_qualifying(cur, gp, sprint_qualifying, prefix="sprint_qualifying")
                print(f"Refreshed SQ1/SQ2/SQ3 values in {changed} entrant rows.")
            else:
                print(f"{gp['season']} is outside the {FIRST_OLD_QUALIFYING_SEASON}-{LAST_OLD_QUALIFYING_SEASON} old qualifying range; qualifying was skipped.")
            previous_gp = gp
    finally:
        if scraper is not None:
            scraper.close_session()

    if args.dry_run:
        conn.rollback()
        print("DRY RUN: database changes rolled back.")
    else:
        conn.commit()
        print(f"Committed schedule and qualifying updates for {len(gps)} Grand Prix weekends.")
    conn.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    main()
