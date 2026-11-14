"""
Race tyre history from motorsport.com (the "Tyre history" tab of a results page),
written into the tyre columns of LapByLap.

Usage:
    stints = scrape_tyre_history(2016, "2016 Australian Grand Prix")
    save_tyre_history(cur, grandprix_id, "2016 Australian Grand Prix", 2016)

motorsport.com lists, for every car, the stints it ran: the compound, how many laps
the set had done by the end of the stint, and whether the set was new. It does not say
on which lap a stint ended, so the stint boundaries come from the pit stops (and the
laps) already in the database.
"""

import itertools

from bs4 import BeautifulSoup

from scrapers.scrape_race_times import _get, event_url

# TracingInsights/FastF1 cover tyres from 2018; motorsport.com has a tyre history tab from 2015.
FIRST_SEASON = 2015
LAST_SEASON = 2017

COMPOUNDS = {
    "H": "HARD", "M": "MEDIUM", "S": "SOFT", "SS": "SUPERSOFT", "US": "ULTRASOFT", "HS": "HYPERSOFT",
    "I": "INTERMEDIATE", "W": "WET",
}


def scrape_tyre_history(season, grand_prix_name):
    """
    {car number: [stint, ...]} in the order the stints were run. Each stint is
    {"compound": "SUPERSOFT", "laps": 15, "new": False}: "laps" is the age of the set
    at the end of the stint, which is the stint's length only when the set was new.
    """
    url = f"{event_url(season, grand_prix_name)}?st=TH"
    # lxml, because the page closes a <td> inside a <span>, which makes html.parser drop most of the table.
    soup = BeautifulSoup(_get(url).content, "lxml")
    if "?st=TH" not in {a["href"][a["href"].index("?"):] for a in soup.find_all("a", href=True) if "?st=" in a["href"]}:
        raise RuntimeError(f"motorsport.com has no tyre history on {url}")
    table = soup.find("table", class_="ms-table--result")
    if table is None:
        raise RuntimeError(f"No tyre history table found on {url}")

    history = {}
    for row in table.find("tbody").find_all("tr"):
        number = int(row.find("td", class_="ms-table_field--number").get_text(strip=True))
        stints = []
        for cell in row.find_all("td", class_="ms-table_field--tyre-history"):
            label = cell.find(class_="label")
            if label is None:
                continue
            code = label.get_text(strip=True)
            if code not in COMPOUNDS:
                raise ValueError(f"Unknown tyre compound {code!r} for car {number} on {url}")
            stints.append({
                "compound": COMPOUNDS[code],
                "laps": int(cell.find(class_="value").get_text(strip=True)),
                "new": label.name == "strong",  # new sets are printed in bold
            })
        history[number] = stints
    if not history:
        raise RuntimeError(f"Empty tyre history table on {url}")
    return history


def stint_boundaries(stints, stop_laps, last_lap):
    """
    The last lap of each stint, or None when the stints cannot be placed.

    A stint ends on the lap of a pit stop (the in-lap belongs to the old set) and the
    final one on the car's last lap. Not every pit stop is a tyre change (drive-through
    and stop-go penalties), so the tyre changes are picked from the pit stops such that
    every stint fits: a new set did exactly its number of laps, a used set at most.
    Some 2015 pages count a stint that ended in the pits one lap short, so when nothing
    fits exactly, that is allowed for too. Other 2015 pages give no lap counts at all
    (every stint says 0); those are placed only when every pit stop is a tyre change.
    None is returned unless exactly one choice fits.
    """
    stop_laps = sorted(lap for lap in set(stop_laps) if lap < last_lap)
    if all(stint["laps"] == 0 for stint in stints):
        return stop_laps + [last_lap] if len(stints) == len(stop_laps) + 1 else None

    for short in (0, 1):  # laps a stint that ended in the pits may be undercounted by
        fits = []
        for changes in itertools.combinations(stop_laps, len(stints) - 1):
            ends = list(changes) + [last_lap]
            lengths = [end - start for start, end in zip([0] + ends, ends)]
            allowed = [short if end != last_lap else 0 for end in ends]
            if all(
                stint["laps"] <= length <= stint["laps"] + extra if stint["new"] else 0 < length <= stint["laps"] + extra
                for length, stint, extra in zip(lengths, stints, allowed)
            ):
                fits.append(ends)
        if fits:
            return fits[0] if len(fits) == 1 else None
    return None


def save_tyre_history(cur, grandprix_id, grand_prix_name, season):
    """
    Fills TyreCompound, TyreAge and StintNumber of the race laps of one Grand Prix.
    StintNumber counts every visit to the pit lane, tyre change or not. TyreAge is left
    empty where motorsport.com gives no lap counts. Returns the drivers whose tyre
    stints could not be placed; their tyre columns are left untouched.
    """
    history = scrape_tyre_history(season, grand_prix_name)
    cur.execute("SELECT driverid, number, driver FROM GrandPrixResults WHERE grandprixid = ?", (grandprix_id,))
    drivers = {driver_id: (number, driver) for driver_id, number, driver in cur.fetchall()}
    cur.execute("SELECT DriverID, Lap FROM PitStopSummary WHERE GrandPrixID = ? AND SessionName = 'Race'", (grandprix_id,))
    stops = {}
    for driver_id, lap in cur.fetchall():
        stops.setdefault(driver_id, []).append(lap)
    cur.execute("SELECT rowid, DriverID, Lap FROM LapByLap WHERE GrandPrixID = ? AND Session = 'Race'", (grandprix_id,))
    laps = {}
    for rowid, driver_id, lap in cur.fetchall():
        laps.setdefault(driver_id, []).append((rowid, lap))

    unplaced = []
    for driver_id, driver_laps in laps.items():
        number, driver = drivers[driver_id]
        last_lap = max(lap for _, lap in driver_laps)
        driver_stops = stops.get(driver_id, [])
        cur.executemany("UPDATE LapByLap SET StintNumber = ? WHERE rowid = ?",
                        [(1 + sum(stop < lap for stop in driver_stops), rowid) for rowid, lap in driver_laps])

        stints = history.get(number, [])
        if stints and stints[-1]["laps"] == 0 and any(stint["laps"] for stint in stints):
            stints = stints[:-1]  # a set fitted just before retiring in the pits never ran a lap
        ends = stint_boundaries(stints, driver_stops, last_lap) if stints else None
        if ends is None:
            unplaced.append(driver)
            continue
        no_lap_counts = all(stint["laps"] == 0 for stint in stints)
        start = 1
        for stint, end in zip(stints, ends):
            # Laps the set had done before this stint: none for a new set.
            age_before = 0 if stint["new"] else max(stint["laps"] - (end - start + 1), 0)
            cur.executemany(
                "UPDATE LapByLap SET TyreCompound = ?, TyreAge = ? WHERE rowid = ?",
                [(stint["compound"], None if no_lap_counts else age_before + lap - start + 1, rowid)
                 for rowid, lap in driver_laps if start <= lap <= end],
            )
            start = end + 1
    return unplaced
