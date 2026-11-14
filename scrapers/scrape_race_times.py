"""
Race and sprint elapsed times from motorsport.com, for the drivers StatsF1 prints no
time for (lapped cars and retirements).

Usage:
    classification = scrape_classification(2026, "2026 São Paulo Grand Prix", "RACE")
    apply_times(classification, [(entrant["number"], entrant) for entrant in entrants], "race")

motorsport.com only has full results pages from 2016 onwards.
"""

import random
import re
import time
import unicodedata

from bs4 import BeautifulSoup
from curl_cffi import requests

FIRST_SEASON = 2016
BASE = "https://www.motorsport.com"

# Grand Prix names motorsport.com spells differently from the database.
NAME_ALIASES = [
    {"mexican", "mexico city"},
    {"brazilian", "sao paulo"},
    {"saudi arabia", "saudi arabian"},
    {"tuscany", "tuscan"},
]

_events = {}  # season -> [(normalized event name, href)]


def _get(url, **kwargs):
    response = requests.get(url, impersonate="chrome", timeout=30, **kwargs)
    response.raise_for_status()
    time.sleep(random.uniform(2, 5))  # be gentle with the site
    return response


def _normalize(name):
    name = unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^a-z0-9]+", " ", name).strip()
    return re.sub(r" (gp|grand prix)$", "", name)


def season_events(season):
    """[(normalized name, href)] for every event motorsport.com lists in the season."""
    if season not in _events:
        # The endpoint answers "Not found" without the AJAX header.
        data = _get(f"{BASE}/f1/results/get-events/{season}/?type=results",
                    headers={"X-Requested-With": "XMLHttpRequest"}).json()
        if not data.get("status"):
            raise RuntimeError(f"motorsport.com has no event list for {season}: {data}")
        soup = BeautifulSoup(data["html"], "html.parser")
        _events[season] = [(_normalize(a.get_text(" ", strip=True)), a["href"]) for a in soup.find_all("a", href=True)]
    return _events[season]


def event_url(season, grand_prix_name):
    """The results page of a Grand Prix, e.g. "2026 São Paulo Grand Prix". Raises when it cannot be matched to exactly one event."""
    wanted = {_normalize(re.sub(r"^\d{4} ", "", grand_prix_name))}
    for aliases in NAME_ALIASES:
        if wanted & aliases:
            wanted |= aliases
    events = season_events(season)
    matches = [href for name, href in events if name in wanted]
    if len(matches) != 1:
        raise ValueError(f"Could not match {grand_prix_name!r} to exactly one motorsport.com event; {season} has {[name for name, _ in events]}")
    return BASE + matches[0]


def _seconds(text):
    """"1:35'38.106", "43'24.700", "+1'15.402" or "+14.602" -> seconds. Anything else ("+1 Lap", "71 laps", "") -> None."""
    match = re.fullmatch(r"\+?(?:(\d+):)?(?:(\d+)')?(\d+\.\d+)", text.strip())
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return round(int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds), 3)


def scrape_classification(season, grand_prix_name, session):
    """
    The classification of the race (session "RACE") or the sprint ("SPR").

    Returns one dict per car: number, position (int, or None if not classified),
    time (elapsed seconds, None if unknown) and gap (seconds behind the winner,
    None when the car was lapped or retired).
    """
    url = f"{event_url(season, grand_prix_name)}?st={session}"
    soup = BeautifulSoup(_get(url).content, "html.parser")
    if f"?st={session}" not in {a["href"][a["href"].index("?"):] for a in soup.find_all("a", href=True) if "?st=" in a["href"]}:
        raise RuntimeError(f"motorsport.com has no {session} results on {url}")
    table = soup.find("table", class_="ms-table--result")
    if table is None:
        raise RuntimeError(f"No results table found on {url}")

    classification = []
    for row in table.find("tbody").find_all("tr"):
        def cell(field):
            td = row.find("td", class_=f"ms-table_field--{field}")
            if td is None:
                raise RuntimeError(f"No {field!r} column in the results table on {url}")
            return td

        position = cell("pos").get_text(strip=True)
        # A classified finisher behind the winner has two lines (gap, then elapsed time); everyone else has one.
        lines = [p.get_text(strip=True) for p in cell("time").find_all("p")] or [cell("time").get_text(strip=True)]
        classification.append({
            "number": int(cell("number").get_text(strip=True)),
            "position": int(position) if position.isdigit() else None,
            "time": _seconds(lines[-1]),
            "gap": _seconds(lines[0]) if len(lines) == 2 else None,
        })
    if not classification:
        raise RuntimeError(f"Empty results table on {url}")
    return classification


def time_text(seconds, prefix):
    """
    Elapsed seconds as text, the way the times from StatsF1 are stored: "1:35:38.106s"
    (or "43:24.700s" under an hour) for the race, "33:43.431" for the sprint.
    """
    hours, rest = divmod(round(seconds * 1000), 3600000)
    minutes, milliseconds = divmod(rest, 60000)
    text = f"{minutes:02d}:{milliseconds / 1000:06.3f}" + ("s" if prefix == "race" else "")
    return f"{hours}:{text}" if hours else text


def gap_text(seconds):
    minutes, milliseconds = divmod(round(seconds * 1000), 60000)
    return f"+{minutes}m {milliseconds / 1000:06.3f}s" if minutes else f"+{milliseconds / 1000:06.3f}s"


def apply_times(classification, targets, prefix):
    """
    Fills the still-empty <prefix>time / <prefix>gap values (prefix "race" or "sprint").

    targets is [(car number, dict)] for the drivers who took part in the session; values
    the dict already has are left alone. The winner's car number must agree with the
    dict that has <prefix>position 1, so a wrongly matched event cannot slip through.
    """
    winners = [car["number"] for car in classification if car["position"] == 1]
    expected = [number for number, target in targets if target.get(f"{prefix}position") == 1]
    if winners != expected:
        raise ValueError(f"motorsport.com {prefix} winner is car {winners}, but the database has car {expected}")

    by_number = {car["number"]: car for car in classification}
    for number, target in targets:
        car = by_number.get(number)
        if car is None:
            continue
        if target.get(f"{prefix}time") is None and car["time"] is not None:
            target[f"{prefix}time"] = time_text(car["time"], prefix)
            target[f"{prefix}timeinseconds"] = car["time"]
        if target.get(f"{prefix}gap") is None and car["gap"] is not None:
            target[f"{prefix}gap"] = gap_text(car["gap"])
            target[f"{prefix}gapinseconds"] = car["gap"]
