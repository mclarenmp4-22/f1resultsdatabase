"""Fill the race tyre columns of LapByLap (TyreCompound, StintNumber, TyreAge) from motorsport.com.

Usage:
    python updaters/update_tyre_history.py --races "2016 Australian Grand Prix"
    python updaters/update_tyre_history.py --season 2016
    python updaters/update_tyre_history.py --seasons 2015-2017
    python updaters/update_tyre_history.py --seasons 2015-2017 --dry-run

motorsport.com has the tyre history of the 2015 to 2017 races; from 2018 the tyres come
from TracingInsights/FastF1 in writedb.py. The site gives each car's stints but not the lap
a stint ended on, so the stints are placed with the pit stops already in PitStopSummary.
A driver whose stints do not fit his pit stops is reported and left untouched.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "sessionresults.db"
sys.path.insert(0, str(ROOT))

from scrapers.scrape_tyre_history import FIRST_SEASON, LAST_SEASON, save_tyre_history


def main():
    parser = argparse.ArgumentParser(description="Fill race tyre history in LapByLap from motorsport.com.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--races", nargs="+", metavar="RACE", help="one or more exact Grand Prix names as stored in GrandsPrix")
    selection.add_argument("--season", type=int, metavar="YEAR", help="every Grand Prix in one season")
    selection.add_argument("--seasons", metavar="FIRST-LAST", help="every Grand Prix in an inclusive season range")
    parser.add_argument("--dry-run", action="store_true", help="scrape and report, then roll back")
    args = parser.parse_args()
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} does not exist.")

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    if args.races:
        gps = []
        for name in args.races:
            cur.execute("SELECT ID, GrandPrixName, Season FROM GrandsPrix WHERE GrandPrixName = ?", (name,))
            match = cur.fetchone()
            if not match:
                raise ValueError(f"Grand Prix {name!r} not found in GrandsPrix.")
            gps.append(match)
    else:
        if args.season is not None:
            first = last = args.season
        else:
            parts = args.seasons.split("-")
            if len(parts) != 2 or not all(part.isdigit() for part in parts):
                parser.error("--seasons must be an inclusive range such as 2016-2017")
            first, last = map(int, parts)
        cur.execute("SELECT ID, GrandPrixName, Season FROM GrandsPrix WHERE Season BETWEEN ? AND ? ORDER BY ID", (first, last))
        gps = cur.fetchall()
        if not gps:
            raise ValueError(f"No GrandsPrix found for seasons {first}-{last}.")
    for _, name, season in gps:
        if not FIRST_SEASON <= season <= LAST_SEASON:
            raise ValueError(f"motorsport.com tyre history is used for {FIRST_SEASON}-{LAST_SEASON}; {name} is {season}.")

    unplaced_total = 0
    for grandprix_id, name, season in gps:
        unplaced = save_tyre_history(cur, grandprix_id, name, season)
        cur.execute("SELECT SUM(TyreCompound IS NOT NULL), COUNT(*) FROM LapByLap WHERE GrandPrixID = ? AND Session = 'Race'", (grandprix_id,))
        filled, laps = cur.fetchone()
        print(f"{name}: tyres on {filled} of {laps} race laps.")
        for driver in unplaced:
            print(f"  NOT PLACED: {driver} - his stints do not fit his pit stops, laps left untouched.")
        unplaced_total += len(unplaced)

    if args.dry_run:
        conn.rollback()
        print("DRY RUN: database changes rolled back.")
    else:
        conn.commit()
        print(f"Committed tyre history for {len(gps)} Grands Prix.")
    if unplaced_total:
        print(f"{unplaced_total} drivers could not be placed (listed above).")
    conn.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    main()
