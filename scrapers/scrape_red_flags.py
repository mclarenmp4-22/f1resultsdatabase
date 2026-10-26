"""
scrapers/scrape_red_flags.py

Scrapes the "List of red-flagged Formula One races" Wikipedia page and populates
the dedicated `RedFlags` table in `sessionresults.db`.
"""

import argparse
import re
import sqlite3
import unicodedata
import urllib.request
from bs4 import BeautifulSoup

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_red-flagged_Formula_One_races"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

RESTART_DESCRIPTIONS = {
    "N": "Race was not restarted",
    "Y": "Race was restarted over the original distance",
    "R": "Race was resumed to complete the originally scheduled distance",
    "S": "Race was restarted or resumed with the originally scheduled distance not completed"
}


def _clean_cell_text(td):
    """Extract cell text with spaces preserved, minus numeric citation brackets."""
    text = td.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\[.*?\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_restart_code(td):
    """Pull the single-letter restart code out of an R cell (footnotes stripped)."""
    text = _clean_cell_text(td)
    match = re.search(r"[NYRS]", text.upper())
    if not match:
        raise ValueError(f"Unrecognised restart code cell: {text!r}")
    return match.group(0)


def _footnote_texts_for_cell(td, footnote_map):
    """Resolve explanatory (Notes-section) footnotes linked from a table cell."""
    texts = []
    for link in td.find_all("a", href=True):
        href = link["href"]
        if not href.startswith("#cite_note-"):
            continue
        key = href[1:]
        if key in footnote_map and footnote_map[key] not in texts:
            texts.append(footnote_map[key])
    return texts


def _build_footnote_map(soup):
    """Map Notes-section footnote ids to their explanatory text.

    Only footnotes under the 'Notes' heading are collected, so plain
    reference citations (e.g. [18]) are ignored while explanatory notes
    attached to restart codes (e.g. "The race was restarted with the
    intention of completing the originally scheduled distance...") are kept.
    """
    footnote_map = {}
    notes_heading = soup.find(id="Notes")
    if not notes_heading:
        return footnote_map
    notes_list = notes_heading.find_next("ol")
    if not notes_list:
        return footnote_map
    for item in notes_list.find_all("li", recursive=False):
        backlink = item.find("span", class_="mw-cite-backlink")
        if backlink:
            backlink.decompose()
        text = item.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\[.*?\]", "", text).strip()
        text = re.sub(r"^[\d\s↑]+", "", text).strip()
        if item.get("id") and text:
            footnote_map[item["id"]] = text
    return footnote_map


def _combine_notes(failed_drivers, failed_reason, extra_notes):
    """Assemble the Notes field from failed-restart info plus footnote text."""
    parts = []
    failed_drivers = (failed_drivers or "").strip()
    failed_reason = (failed_reason or "").strip()
    if failed_drivers and failed_reason:
        parts.append(f"{failed_drivers} ({failed_reason})")
    elif failed_drivers:
        parts.append(failed_drivers)
    elif failed_reason:
        parts.append(failed_reason)
    for note in extra_notes or []:
        note = (note or "").strip()
        if note and note not in parts:
            parts.append(note)
    return "; ".join(parts)


def fetch_wikipedia_red_flags():
    req = urllib.request.Request(WIKIPEDIA_URL, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        html_content = resp.read().decode('utf-8')

    soup = BeautifulSoup(html_content, "html.parser")
    tables = soup.find_all("table", class_="wikitable")

    # Find the World Championship table by header instead of fixed index.
    wc_table = None
    for table in tables:
        header = " ".join(
            th.get_text(" ", strip=True) for th in table.find_all("th")
        )
        if "Incident that prompted" in header and "Failed to make the restart" in header:
            if table.find(string=re.compile(r"^\s*1971\s*$")):
                wc_table = table
                break
    if wc_table is None:
        raise ValueError("Could not locate the World Championship red-flags table")

    footnote_map = _build_footnote_map(soup)

    red_flags = []
    rows = wc_table.find_all("tr")

    current_year = None
    current_gp = None
    current_winner = None

    for row in rows:
        tds = row.find_all(["td", "th"])
        if not tds:
            continue

        cell_texts = [_clean_cell_text(td) for td in tds]

        if cell_texts == ['Drivers', 'Reason']:
            continue
        if cell_texts and ('Incident that prompted' in cell_texts[0] or cell_texts[0] == 'Year'):
            continue

        # Continuation rows listing extra drivers who missed the restart,
        # e.g. ['Andrea de Adamich', 'Crash, injured'].
        if len(tds) == 2 and red_flags:
            extra_notes = _combine_notes(cell_texts[0], cell_texts[1], None)
            if extra_notes:
                prev_notes = red_flags[-1]["notes"]
                red_flags[-1]["notes"] = (
                    f"{prev_notes}; {extra_notes}" if prev_notes else extra_notes
                )
            continue

        # Continuation rows carrying extra incident detail plus a driver,
        # e.g. the 1987 Austrian second-start description.
        if len(tds) == 3 and red_flags and not re.match(r"^\d+$", cell_texts[0]):
            if cell_texts[0]:
                prev_reason = red_flags[-1]["reason"]
                red_flags[-1]["reason"] = (
                    f"{prev_reason} {cell_texts[0]}".strip()
                )
            extra_notes = _combine_notes(cell_texts[1], cell_texts[2], None)
            if extra_notes:
                prev_notes = red_flags[-1]["notes"]
                red_flags[-1]["notes"] = (
                    f"{prev_notes}; {extra_notes}" if prev_notes else extra_notes
                )
            continue

        lap_raw = restarted_code = winner_raw = reason_raw = None
        failed_drivers = failed_reason = ""
        code_cell_index = None

        # Pattern 1: full row starting with Year, 9 cells:
        # [Year, GP, Lap, R, Winner, Incident, FailDrivers, FailReason, Ref]
        if len(tds) >= 9 and re.match(r"^\d{4}$", cell_texts[0]):
            current_year = cell_texts[0]
            current_gp = cell_texts[1]
            lap_raw = cell_texts[2]
            code_cell_index = 3
            restarted_code = _extract_restart_code(tds[3])
            current_winner = cell_texts[4]
            winner_raw = current_winner
            reason_raw = cell_texts[5]
            failed_drivers = cell_texts[6]
            failed_reason = cell_texts[7]
        # Pattern 2: GP row under a rowspanned year, 8 cells:
        # [GP, Lap, R, Winner, Incident, FailDrivers, FailReason, Ref]
        elif current_year and len(tds) == 8 and not re.match(r"^\d+$", cell_texts[0]):
            current_gp = cell_texts[0]
            lap_raw = cell_texts[1]
            code_cell_index = 2
            restarted_code = _extract_restart_code(tds[2])
            current_winner = cell_texts[3]
            winner_raw = current_winner
            reason_raw = cell_texts[4]
            failed_drivers = cell_texts[5]
            failed_reason = cell_texts[6]
        # Pattern 3: additional red flag in the same race; Year, GP and
        # Winner cells are rowspanned away, leaving 5-6 cells:
        # [Lap, R, Incident, FailDrivers, FailReason, (Ref)]
        elif (current_year and current_gp and len(tds) in (5, 6)
                and re.match(r"^\d+$", cell_texts[0])):
            lap_raw = cell_texts[0]
            code_cell_index = 1
            restarted_code = _extract_restart_code(tds[1])
            winner_raw = current_winner
            reason_raw = cell_texts[2]
            failed_drivers = cell_texts[3] if len(cell_texts) > 3 else ""
            failed_reason = cell_texts[4] if len(cell_texts) > 4 else ""
        else:
            raise ValueError(f"Unrecognised red-flags row shape: {cell_texts!r}")

        if current_year is None or current_gp is None:
            raise ValueError(f"Row before year/GP established: {cell_texts!r}")

        # Explanatory footnotes on the restart-code cell (e.g. "The race was
        # restarted with the intention of completing the originally scheduled
        # distance...") belong in Notes, not in the code itself.
        extra_notes = []
        if code_cell_index is not None:
            extra_notes.extend(
                _footnote_texts_for_cell(tds[code_cell_index], footnote_map)
            )

        gp_clean = current_gp if "Grand Prix" in current_gp else f"{current_gp} Grand Prix"
        full_gp_name = f"{current_year} {gp_clean}"

        lap_match = re.search(r"\d+", lap_raw or "")
        if not lap_match:
            raise ValueError(f"Could not parse lap from row: {cell_texts!r}")
        lap_val = int(lap_match.group(0))

        restarted_desc = RESTART_DESCRIPTIONS.get(restarted_code)
        if restarted_desc is None:
            raise ValueError(f"Unknown restart code {restarted_code!r}")

        red_flags.append({
            "grandprix": full_gp_name,
            "season": int(current_year),
            "lap": lap_val,
            "restarted_code": restarted_code,
            "restarted_description": restarted_desc,
            "leader": winner_raw or "",
            "reason": reason_raw or "",
            "notes": _combine_notes(failed_drivers, failed_reason, extra_notes)
        })

    return red_flags


_cached_red_flags = None


def get_cached_red_flags(refresh=False):
    """Fetch the Wikipedia red-flags list once per process and reuse it.

    The race pipeline calls the per-race saver for every Grand Prix, so the
    page must only be fetched a single time, not once per race.
    """
    global _cached_red_flags
    if _cached_red_flags is None or refresh:
        print("Fetching red-flagged F1 races from Wikipedia...")
        _cached_red_flags = fetch_wikipedia_red_flags()
        print(f"Found {len(_cached_red_flags)} total red flag incidents from Wikipedia.")
    return _cached_red_flags


def _fold_name(name):
    return (
        unicodedata.normalize("NFKD", (name or "").lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def iter_red_flags_for_grandprix(red_flags, grandprix_name):
    """Yield the red-flag items belonging to a single Grand Prix name."""
    target = (grandprix_name or "").strip()
    target_folded = _fold_name(target)
    for item in red_flags:
        name = item["grandprix"]
        if name == target or name.lower() == target.lower():
            yield item
        elif _fold_name(name) == target_folded:
            yield item


def save_red_flags_for_race(cur, grandprix_name, grandprix_id, red_flags=None):
    """Race-pipeline hook: refresh the RedFlags rows for one Grand Prix.

    Deletes any existing rows for the Grand Prix first, so re-running a race
    through the pipeline replaces stale rows instead of duplicating them.
    Uses the caller's cursor, so no commit happens here.
    """
    if red_flags is None:
        red_flags = get_cached_red_flags()

    cur.execute('''CREATE TABLE IF NOT EXISTS RedFlags (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        GrandPrix TEXT,
        Season INTEGER,
        Lap INTEGER,
        RestartedCode TEXT,
        RestartedDescription TEXT,
        LeaderAtStoppage TEXT,
        Reason TEXT,
        Notes TEXT,
        GrandPrixID INTEGER,
        LeaderID INTEGER,
        FOREIGN KEY (GrandPrixID) REFERENCES GrandsPrix(ID),
        FOREIGN KEY (LeaderID) REFERENCES Drivers(ID)
    )''')

    cur.execute("SELECT ID, Name FROM Drivers")
    driver_name_map = {name.lower(): id_ for id_, name in cur.fetchall()}

    matching = list(iter_red_flags_for_grandprix(red_flags, grandprix_name))

    cur.execute("DELETE FROM RedFlags WHERE GrandPrixID = ?", (grandprix_id,))

    for item in matching:
        leader_name = item["leader"]
        leader_id = driver_name_map.get(leader_name.lower()) if leader_name else None
        cur.execute(
            """
            INSERT INTO RedFlags (
                GrandPrix, Season, Lap, RestartedCode, RestartedDescription,
                LeaderAtStoppage, Reason, Notes, GrandPrixID, LeaderID
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                grandprix_name, item["season"], item["lap"],
                item["restarted_code"], item["restarted_description"],
                leader_name, item["reason"], item["notes"],
                grandprix_id, leader_id
            )
        )

    if matching:
        print(f"Red flags saved for {grandprix_name} ({len(matching)} incident(s))")

    return len(matching)


def update_red_flags_db(db_path="sessionresults.db", dry_run=False):
    print("Fetching red-flagged F1 races from Wikipedia...")
    red_flags = fetch_wikipedia_red_flags()
    print(f"Found {len(red_flags)} total red flag incidents from Wikipedia.")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS RedFlags (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        GrandPrix TEXT,
        Season INTEGER,
        Lap INTEGER,
        RestartedCode TEXT,
        RestartedDescription TEXT,
        LeaderAtStoppage TEXT,
        Reason TEXT,
        Notes TEXT,
        GrandPrixID INTEGER,
        LeaderID INTEGER,
        FOREIGN KEY (GrandPrixID) REFERENCES GrandsPrix(ID),
        FOREIGN KEY (LeaderID) REFERENCES Drivers(ID)
    )''')

    if not dry_run:
        cur.execute("DELETE FROM RedFlags")

    cur.execute("SELECT ID, GrandPrixName FROM GrandsPrix")
    db_gps = cur.fetchall()
    gp_name_map = {name.lower(): (id_, name) for id_, name in db_gps}

    cur.execute("SELECT ID, Name FROM Drivers")
    db_drivers = cur.fetchall()
    driver_name_map = {name.lower(): id_ for id_, name in db_drivers}

    overrides = {
        "2023 são paulo grand prix": "2023 São Paulo Grand Prix",
        "2024 são paulo grand prix": "2024 São Paulo Grand Prix"
    }

    inserted_count = 0
    unmatched_gps = set()

    for item in red_flags:
        wiki_name = item["grandprix"]
        wiki_clean = wiki_name.lower().strip()
        gp_info = gp_name_map.get(wiki_clean)

        if not gp_info and wiki_clean in overrides:
            gp_info = gp_name_map.get(overrides[wiki_clean].lower())

        if not gp_info:
            for db_lower, (id_, name) in gp_name_map.items():
                if wiki_clean in db_lower or db_lower in wiki_clean:
                    gp_info = (id_, name)
                    break

        if gp_info:
            gp_id, canonical_gp_name = gp_info
            leader_name = item["leader"]
            leader_id = driver_name_map.get(leader_name.lower()) if leader_name else None

            print(f"[{inserted_count + 1}/{len(red_flags)}] Match: '{wiki_name}' -> '{canonical_gp_name}' (Lap {item['lap']}, Restart {item['restarted_code']})")
            inserted_count += 1

            if not dry_run:
                cur.execute(
                    """
                    INSERT INTO RedFlags (
                        GrandPrix, Season, Lap, RestartedCode, RestartedDescription,
                        LeaderAtStoppage, Reason, Notes, GrandPrixID, LeaderID
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        canonical_gp_name, item["season"], item["lap"],
                        item["restarted_code"], item["restarted_description"],
                        leader_name, item["reason"], item["notes"],
                        gp_id, leader_id
                    )
                )
        else:
            unmatched_gps.add(wiki_name)

    if not dry_run:
        conn.commit()

    conn.close()
    print(f"\nUpdate complete! Stored {inserted_count}/{len(red_flags)} red flag records.")
    if unmatched_gps:
        print(f"Unmatched Grand Prix names ({len(unmatched_gps)}): {unmatched_gps}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Wikipedia red-flagged F1 races into RedFlags table in sessionresults.db")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse without modifying database")
    parser.add_argument("--db", default="sessionresults.db", help="Path to SQLite database file")
    args = parser.parse_args()

    update_red_flags_db(db_path=args.db, dry_run=args.dry_run)
