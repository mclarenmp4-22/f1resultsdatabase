"""Refresh circuit layout SVGs from StatsF1.

Usage:
    python updaters/update_circuit_layouts.py latest
    python updaters/update_circuit_layouts.py id 42
    python updaters/update_circuit_layouts.py range 40 50

`latest` means the layout used by the most recent Grand Prix already recorded in
the database. The ID commands refresh existing CircuitLayouts rows only; they
never create rows or renumber IDs.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "sessionresults.db"
sys.path.insert(0, str(ROOT))

from scrapers import circuit_layout_scraper as scraper


def parse_circuit_page(soup, fallback_name):
    """Return coordinates and version metadata using the scraper's page rules."""
    maps_link = soup.find("a", id="ctl00_CPH_Main_HL_GMaps")
    if maps_link is None or not maps_link.get("href"):
        raise ValueError(f"StatsF1 circuit page for {fallback_name!r} has no map link")
    import re

    coordinate_match = re.search(r"@([^,]+),([^,]+)", maps_link["href"])
    if coordinate_match is None:
        raise ValueError(f"Could not read coordinates for {fallback_name!r}")
    latitude, longitude = (scraper.parse_coordinate(value) for value in coordinate_match.groups())
    official_name, track_type = scraper.parse_circuit_metadata(soup, fallback_name=fallback_name)

    layout_divs = soup.find_all("div", class_="circuitversion")
    layouts = []
    for version, layout_div in enumerate(layout_divs, start=1):
        table = layout_div.find("table", class_="sortable circuittable")
        image = layout_div.find("img")
        description = layout_div.find("div", class_="circuitversiontxt")
        if table is None or image is None or not image.get("src") or description is None:
            raise ValueError(f"Incomplete layout {version} on {fallback_name!r} page")
        dates = [
            row.find_all("td")[0]["sorttable_customkey"]
            for row in table.find_all("tr")[1:-1]
        ]
        changes = description.get_text(strip=True).replace("\n", "").replace('"', "").replace("\r", "")
        layouts.append({
            "version": version,
            "dates": dates,
            "image_url": urljoin(scraper.STATSF1 if hasattr(scraper, "STATSF1") else "https://www.statsf1.com", image["src"]),
            "changes": changes,
        })
    return latitude, longitude, official_name, track_type, layouts


def refresh_layouts(layout_ids):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in layout_ids)
        rows = cur.execute(
            f"SELECT ID, Latitude, Longitude, CircuitVersion, Country, Elevation "
            f"FROM CircuitLayouts WHERE ID IN ({placeholders}) ORDER BY ID",
            layout_ids,
        ).fetchall()
        found_ids = {row["ID"] for row in rows}
        missing_ids = sorted(set(layout_ids) - found_ids)
        if missing_ids:
            raise ValueError(f"CircuitLayouts ID(s) not found: {', '.join(map(str, missing_ids))}")

        # Match the intended records by their stable circuit coordinates and source version.
        # Fetch each circuit page once even when refreshing several versions on it.
        groups = {}
        for row in rows:
            key = (row["Latitude"], row["Longitude"])
            groups.setdefault(key, []).append(row)

        for (latitude, longitude), group in groups.items():
            circuit = cur.execute(
                "SELECT CircuitName FROM Circuits WHERE Latitude = ? AND Longitude = ? LIMIT 1",
                (latitude, longitude),
            ).fetchone()
            if circuit is None:
                raise ValueError(f"No Circuits row for layout coordinates {latitude}, {longitude}")
            circuit_name = circuit["CircuitName"]
            slug = circuit_name.replace(" ", "-").lower()
            page = scraper.open_url(f"https://www.statsf1.com/en/circuit-{slug}.aspx")
            page_lat, page_lng, official_name, track_type, source_layouts = parse_circuit_page(page, circuit_name)
            if (page_lat, page_lng) != (latitude, longitude):
                raise ValueError(f"StatsF1 coordinates for {circuit_name!r} do not match database rows")

            for row in group:
                source = next(
                    (item for item in source_layouts if str(item["version"]) == str(row["CircuitVersion"])),
                    None,
                )
                if source is None:
                    raise ValueError(
                        f"StatsF1 has no version {row['CircuitVersion']!r} for "
                        f"CircuitLayouts.ID {row['ID']} ({circuit_name})"
                    )
                svg, direction = scraper.generate_track_svg(source["image_url"], source["dates"])
                cur.execute(
                    "UPDATE CircuitLayouts SET GrandPrixDates = ?, SVG = ?, CircuitChanges = ?, "
                    "TrackDirection = ?, OfficialCircuitName = ?, TrackType = ? WHERE ID = ?",
                    (json.dumps(source["dates"]), svg, source["changes"], direction,
                     official_name, track_type, row["ID"]),
                )
                print(f"Updated CircuitLayouts.ID {row['ID']}: {circuit_name}, version {row['CircuitVersion']}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def latest_layout_id():
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT gp.CircuitLayoutID "
            "FROM GrandsPrix gp "
            "WHERE gp.CircuitLayoutID IS NOT NULL "
            "ORDER BY gp.Date DESC, gp.ID DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise ValueError("No Grand Prix with a linked circuit layout was found")
    return row[0]


def main():
    parser = argparse.ArgumentParser(description="Refresh circuit layout data from StatsF1")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("latest", help="refresh the layout of the latest Grand Prix in the database")
    id_parser = commands.add_parser("id", help="refresh one CircuitLayouts.ID")
    id_parser.add_argument("layout_id", type=int)
    range_parser = commands.add_parser("range", help="refresh an inclusive range of CircuitLayouts IDs")
    range_parser.add_argument("first_id", type=int)
    range_parser.add_argument("last_id", type=int)
    args = parser.parse_args()

    if args.command == "latest":
        ids = [latest_layout_id()]
    elif args.command == "id":
        ids = [args.layout_id]
    else:
        if args.first_id > args.last_id:
            parser.error("first_id must be less than or equal to last_id")
        ids = list(range(args.first_id, args.last_id + 1))
    refresh_layouts(ids)


if __name__ == "__main__":
    main()
