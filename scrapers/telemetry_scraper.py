"""
Telemetry scraper (issue #4).

Stores car telemetry as one zstd-compressed Parquet file per driver per session:

    telemetry/<season>/<GrandPrixID>/<SessionID>/<DriverID>.parquet

Each file is indexed by one row in the TelemetryIndex table. Two sources produce
exactly the same columns:

  * FastF1 (3.9 or later), if you are signed in to an F1 TV account. Sign in once with
        python -m fastf1 auth f1tv --authenticate
    or set the F1_USERNAME and F1_PASSWORD environment variables. The scraper never
    asks for credentials by itself.
  * TracingInsights (https://github.com/TracingInsights), a free copy of the same data
    under the Apache-2.0 licence, used when FastF1 is not set up or cannot load a session.

F1_TELEMETRY_SOURCE=auto|fastf1|tracinginsights overrides the choice (default auto).

Called from writedb.py for every new Grand Prix, and from updaters/update_telemetry.py
to backfill or catch up. It can also be run on its own to write Parquet files from
TracingInsights without a database:

    python scrapers/telemetry_scraper.py --year 2026 --event "Australian Grand Prix" --session Race --drivers VER
"""
import argparse
import datetime
import json
import os
import random
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SOURCE_FASTF1 = "FastF1"
SOURCE_TRACINGINSIGHTS = "TracingInsights"
SOURCE_CHOICES = ("auto", "fastf1", "tracinginsights")

# Tried in order. jsDelivr is the CDN writedb.py already uses; it caches @main for
# hours and can refuse individual files, so GitHub itself is the fallback.
BASE_URLS = (
    "https://cdn.jsdelivr.net/gh/TracingInsights/{year}@main/{path}",
    "https://raw.githubusercontent.com/TracingInsights/{year}/main/{path}",
)
TELEMETRY_DIR = Path("telemetry")
FIRST_SEASON = 2018  # both sources start here
MAX_WORKERS = 4
PAUSE_RANGE = (0.05, 0.15)  # seconds; random pause before every request
RETRIES = 3
ZSTD_LEVEL = 19

# Sessions.SessionName values that have telemetry. Sub-sessions such as
# "Qualifying 1" or "Grid", and cancelled sessions, are skipped.
TELEMETRY_SESSIONS = (
    "Practice 1", "Practice 2", "Practice 3", "Qualifying",
    "Sprint Shootout", "Sprint Qualifying", "Sprint", "Race",
)

# Parquet columns besides `lap` (uint8) and `time_ms` (int32, since the lap started).
# The names are TracingInsights' own; FASTF1_COLUMNS maps FastF1's names onto them.
COLUMNS = {
    "speed": "float32",
    "rpm": "float32",
    "throttle": "float32",  # 104 is FastF1's sensor-error value; kept as published
    "gear": "int8",
    "brake": "bool",
    "drs": "uint8",  # 1 = open; always 0 from 2026 in the TracingInsights data
    "distance": "float32",
    "x": "float32",
    "y": "float32",
    "z": "float32",
}
FASTF1_COLUMNS = {
    "Speed": "speed", "RPM": "rpm", "Throttle": "throttle", "nGear": "gear",
    "Brake": "brake", "Distance": "distance", "X": "x", "Y": "y", "Z": "z",
}
FASTF1_DRS_OPEN = (10, 12, 14)  # FastF1's raw DRS codes for "open"; everything else is closed


def normalize_driver_name(name):
    """Same normalisation as writedb.normalize_name (which cannot be imported)."""
    if not name:
        return ""
    if name.lower() == "gianmaria bruni":
        return "gimmi bruni"
    if name.lower() == "zhou guanyu":
        return "guanyu zhou"
    return unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode("ascii").replace("-", " ")


def _letters(text):
    return re.sub(r"[^a-z]", "", text)


def resolve_driver(entry, drivers, grandprix_drivers):
    """Map one driver entry to a (DriverID, Name) row. The entry is a dict with
    'driver' (three-letter code) and optionally 'fn' / 'ln' (first and last name),
    which is what both TracingInsights' drivers.json and FastF1's results provide.

    1. If the entry has a usable first and last name, match it against the whole
       Drivers table.
    2. Otherwise, or if the name is spelled differently from ours, use the
       three-letter code (e.g. 'HUL'), which is the start of the surname: look
       for exactly one driver in this Grand Prix whose surname starts with it.
       2018 files and some later ones only carry the code, and the name field
       is sometimes the literal string 'None'."""
    first, last = entry.get("fn"), entry.get("ln")
    if all(value not in (None, "", "None") for value in (first, last)):
        match = drivers.get(normalize_driver_name(f"{first} {last}"))
        if match is not None:
            return match

    code = entry["driver"].lower()
    surname_matches, word_matches = [], []
    for driver_id, name in grandprix_drivers:
        words = normalize_driver_name(name).split()
        # 'de vries' -> 'dev', "o'ward" -> 'owa'
        surnames = {_letters(words[-1])[:3], _letters("".join(words[1:]))[:3]}
        if code in surnames:
            surname_matches.append((driver_id, name))
        elif code in {_letters(word)[:3] for word in words}:
            word_matches.append((driver_id, name))  # e.g. a first name; only a last resort
    matches = surname_matches or word_matches
    if len(matches) != 1:
        raise ValueError(
            f"Could not match driver {entry['driver']} (name: {first} {last}) "
            f"to exactly one driver in this Grand Prix; candidates: {matches}"
        )
    return matches[0]


def finish_frame(df):
    """Cast a frame that already uses our column names to the Parquet schema."""
    for column, dtype in COLUMNS.items():
        if dtype in ("bool", "int8", "uint8") and df[column].isna().any():
            raise ValueError(f"unexpected missing values in integer column '{column}'")
        df[column] = df[column].astype(dtype)
    df["lap"] = df["lap"].astype("uint8")
    df["time_ms"] = df["time_ms"].astype("int32")
    return df.sort_values(["lap", "time_ms"], kind="stable").reset_index(drop=True)[["lap", "time_ms", *COLUMNS]]


def write_parquet(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    floats = [field.name for field in table.schema if pa.types.is_floating(field.type)]
    # byte-stream-split on the float columns shrinks the files by ~40%; it needs
    # dictionary encoding switched off.
    pq.write_table(table, path, compression="zstd", compression_level=ZSTD_LEVEL,
                   use_dictionary=False, use_byte_stream_split=floats)


# ---------------------------------------------------------------------------
# Source 1: FastF1
# ---------------------------------------------------------------------------

def fastf1_session_name(session_name, year):
    """FastF1 calls the 2021 and 2022 sprints 'Sprint'; our Sessions table calls them 'Sprint Qualifying'."""
    if session_name == "Sprint Qualifying" and year in (2021, 2022):
        return "Sprint"
    return session_name


def fastf1_ready():
    """True if FastF1 can send an F1 TV token without asking anybody for anything:
    FastF1 3.9 or later, with either a valid stored token (python -m fastf1 auth f1tv
    --authenticate) or F1_USERNAME and F1_PASSWORD set. Nothing is downloaded or signed in here."""
    try:
        import fastf1
        from fastf1.internals.f1account import token_manager
    except ImportError:
        return False
    if not hasattr(fastf1, "set_auth_method"):
        return False  # FastF1 older than 3.9 cannot sign in
    token = token_manager.get_stored()
    if token is not None and token.is_valid():
        return True
    return bool(os.environ.get("F1_USERNAME") and os.environ.get("F1_PASSWORD"))


def load_fastf1_session(year, round_number, session_name):
    import fastf1
    # A loaded session is hundreds of MB; do not leave it in FastF1's disk cache.
    with fastf1.Cache.disabled():
        session = fastf1.get_session(year, round_number, fastf1_session_name(session_name, year))
        session.load(laps=True, telemetry=True, weather=False, messages=False)
    return session


def _fastf1_lap_frame(lap):
    """One lap's merged car + position telemetry in our column names. This is
    Lap.get_telemetry() without its slow driver-ahead calculation, which we do not store."""
    pos_data = lap.get_pos_data(pad=1, pad_side="both")
    car_data = lap.get_car_data(pad=1, pad_side="both").add_distance()
    tel = pos_data.merge_channels(car_data).slice_by_lap(lap, interpolate_edges=True)
    if len(tel) == 0:
        return None
    frame = pd.DataFrame({
        "lap": int(lap["LapNumber"]),
        "time_ms": (tel["Time"].dt.total_seconds() * 1000).round().to_numpy(),
    })
    for source, name in FASTF1_COLUMNS.items():
        frame[name] = tel[source].to_numpy()
    frame["drs"] = tel["DRS"].isin(FASTF1_DRS_OPEN).astype("uint8").to_numpy()
    return frame


def fastf1_driver_frames(session):
    """Yield (entry, DataFrame, missing_laps) for each driver of a loaded FastF1
    session. The DataFrame is None if the driver has no telemetry."""
    for _, driver in session.results.iterrows():
        frames, missing = [], 0
        for _, lap in session.laps.pick_drivers(driver["DriverNumber"]).iterlaps():
            if pd.isna(lap["LapNumber"]) or pd.isna(lap["LapStartTime"]) or pd.isna(lap["Time"]):
                missing += 1
                continue
            frame = _fastf1_lap_frame(lap)
            if frame is None:
                missing += 1
            else:
                frames.append(frame)
        entry = {"driver": driver["Abbreviation"], "fn": driver["FirstName"], "ln": driver["LastName"]}
        if not frames:
            yield entry, None, missing
            continue
        df = pd.concat(frames, ignore_index=True)
        # keep the last known gear / brake / DRS across the interpolated edge samples
        for column in ("gear", "brake", "drs"):
            df[column] = df.groupby("lap")[column].transform(lambda values: values.ffill().bfill())
        yield entry, finish_frame(df), missing


def _fastf1_results(year, round_number, grandprix_name, session_name, strict):
    """Load a session through FastF1 and convert every driver. Returns a list of
    (entry, DataFrame, missing_laps), or None if FastF1 could not provide the
    session and we are allowed to fall back to TracingInsights."""
    from fastf1.exceptions import DataNotLoadedError, F1AuthError, NoLapDataError
    try:
        session = load_fastf1_session(year, round_number, session_name)
        return list(fastf1_driver_frames(session))
    except (DataNotLoadedError, F1AuthError, NoLapDataError, ValueError) as error:
        if strict:
            raise
        print(f"FastF1 could not load {grandprix_name} {session_name} ({error}); trying TracingInsights")
        return None


# ---------------------------------------------------------------------------
# Source 2: TracingInsights
# ---------------------------------------------------------------------------

def event_folder(grandprix_name, year):
    """TracingInsights folder for a Grand Prix: the name without the year, with
    the same renames writedb.py applies for its lap scraping."""
    name = re.sub(r"^\d{4}\s+", "", grandprix_name).strip()
    if name == "Mexican Grand Prix" and year >= 2020:
        name = "Mexico City Grand Prix"
    elif name == "Barcelona-Catalunya Grand Prix" and year >= 2026:
        name = "Barcelona Grand Prix"
    return name


def session_folder(session_name, year):
    """TracingInsights calls the 2022 sprint 'Sprint'; our Sessions table calls it 'Sprint Qualifying'."""
    if session_name == "Sprint Qualifying" and year == 2022:
        return "Sprint"
    return session_name


_host_failures = {}  # host -> consecutive failed requests
_host_down_until = {}  # host -> time.time() until which it is skipped
HOST_GIVE_UP = 5  # consecutive failures before a host is skipped...
HOST_COOLDOWN = 600  # ...for this many seconds


def fetch_json(year, path, base_urls=BASE_URLS):
    """GET a JSON file, trying each host in turn.

    Returns None only if the last host (GitHub itself) says 404, meaning the file
    does not exist. A 404 or a refusal (403, 5xx, timeout) from an earlier host just
    moves on to the next one, and a host that keeps failing is skipped for a while
    so one blocked CDN does not slow down every file. If every host fails, raises."""
    errors = []
    last_was_404 = False
    for position, host in enumerate(base_urls):
        is_last = position == len(base_urls) - 1
        if not is_last and _host_down_until.get(host, 0) > time.time():
            continue
        url = host.format(year=year, path=urllib.parse.quote(path))
        last_was_404 = False
        attempts = RETRIES
        attempt = 0
        while attempt < attempts:
            attempt += 1
            time.sleep(random.uniform(*PAUSE_RANGE))
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    data = json.loads(response.read())
                _host_failures[host] = 0
                return data
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    last_was_404 = True
                    break
                errors.append(f"{url}: HTTP {error.code}")
                if error.code not in (429, 500, 502, 503, 504):
                    break  # e.g. 403: retrying the same host will not help
                time.sleep(5 * attempt)  # rate limited or server trouble: back off
            except OSError as error:  # unreachable, timeout, connection reset
                errors.append(f"{url}: {error}")
                attempts = 2  # one quick retry, then move on
                time.sleep(2)
        if not last_was_404:
            _host_failures[host] = _host_failures.get(host, 0) + 1
            if _host_failures[host] >= HOST_GIVE_UP:
                _host_down_until[host] = time.time() + HOST_COOLDOWN
                _host_failures[host] = 0
                print(f"Skipping {host.split('/')[2]} for {HOST_COOLDOWN // 60} minutes after repeated failures")
    if last_was_404:
        return None
    raise RuntimeError("Could not download " + path + ":\n  " + "\n  ".join(errors))


def _lap_frame(year, base, lap, base_urls):
    data = fetch_json(year, f"{base}/{lap}_tel.json", base_urls)
    if data is None:
        return None
    tel = data["tel"]
    absent = [name for name in COLUMNS if name not in tel]
    if absent:
        raise ValueError(f"{base}/{lap}_tel.json is missing columns {absent}")
    frame = pd.DataFrame({name: tel[name] for name in COLUMNS})
    frame.insert(0, "time_ms", (pd.Series(tel["time"]) * 1000).round())
    frame.insert(0, "lap", lap)
    return frame


def driver_frame(year, event, folder, code, base_urls=BASE_URLS):
    """All laps of one driver in one TracingInsights session as a single DataFrame.
    Returns (frame, missing_lap_files); frame is None if the driver has no data."""
    base = f"{event}/{folder}/{code}"
    laptimes = fetch_json(year, f"{base}/laptimes.json", base_urls)
    if laptimes is None:
        return None, 0
    laps = laptimes["lap"]
    with ThreadPoolExecutor(MAX_WORKERS) as pool:
        results = list(pool.map(lambda lap: _lap_frame(year, base, lap, base_urls), laps))
    missing = sum(1 for result in results if result is None)
    frames = [result for result in results if result is not None and len(result)]
    if not frames:
        return None, missing

    df = pd.concat(frames, ignore_index=True)
    # TracingInsights writes the string 'None' for missing values in some columns
    for name in COLUMNS:
        df[name] = pd.to_numeric(df[name], errors="coerce")
    try:
        return finish_frame(df), missing
    except ValueError as error:
        raise ValueError(f"{base}: {error}") from error


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

def _store(cursor, df, path, source, grandprix_name, session_name, driver_name, grandprix_id, session_id, driver_id):
    write_parquet(df, path)
    cursor.execute("""
        INSERT OR REPLACE INTO TelemetryIndex (
            GrandPrixName, SessionName, Driver, FilePath, RowCount, LapCount,
            Source, RetrievedAtUTC, GrandPrixID, SessionID, DriverID
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        grandprix_name, session_name, driver_name, path.as_posix(), len(df),
        int(df["lap"].nunique()), source,
        datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        grandprix_id, session_id, driver_id,
    ))


_announced = False


def _announce_tracinginsights():
    global _announced
    if not _announced:
        _announced = True
        print("Telemetry source: TracingInsights. To use FastF1 instead, sign in to F1 TV once with "
              "`python -m fastf1 auth f1tv --authenticate` (FastF1 3.9 or later).")


def save_telemetry(cursor, year, grandprix_name, grandprix_id, out_root=TELEMETRY_DIR,
                   base_urls=BASE_URLS, source=None):
    """Download and index telemetry for every session of one Grand Prix that does
    not have it yet. Safe to re-run. Returns the number of files written.

    `source` (default: the F1_TELEMETRY_SOURCE environment variable, else 'auto'):
      'auto'            FastF1 when it is set up, for sessions with nothing indexed yet;
                        TracingInsights for everything else, including when FastF1 fails.
      'fastf1'          FastF1 only; raises if it is not set up or cannot load a session.
      'tracinginsights' TracingInsights only.
    Sessions that no source has published yet are skipped and picked up by
    updaters/update_telemetry.py later."""
    source = (source or os.environ.get("F1_TELEMETRY_SOURCE", "auto")).strip().lower()
    if source not in SOURCE_CHOICES:
        raise ValueError(f"F1_TELEMETRY_SOURCE must be one of {SOURCE_CHOICES}, not '{source}'")
    if year < FIRST_SEASON:
        return 0
    use_fastf1 = source != "tracinginsights"
    if source == "fastf1" and not fastf1_ready():
        raise RuntimeError(
            "FastF1 telemetry needs FastF1 3.9 or later and an F1 TV sign-in. Run "
            "`python -m fastf1 auth f1tv --authenticate` once, or set F1_USERNAME and F1_PASSWORD."
        )
    if source == "auto":
        use_fastf1 = fastf1_ready()
        if not use_fastf1:
            _announce_tracinginsights()

    cursor.execute("SELECT ID, Name FROM Drivers")
    drivers = {normalize_driver_name(name): (driver_id, name) for driver_id, name in cursor.fetchall()}
    cursor.execute("SELECT DISTINCT driverid, driver FROM GrandPrixResults WHERE grandprixid = ?", (grandprix_id,))
    grandprix_drivers = cursor.fetchall()
    cursor.execute("SELECT RoundNumber FROM GrandsPrix WHERE ID = ?", (grandprix_id,))
    round_number = cursor.fetchone()[0]
    cursor.execute("SELECT ID, SessionName FROM Sessions WHERE GrandPrixID = ? ORDER BY SessionNumber", (grandprix_id,))
    sessions = [(session_id, name) for session_id, name in cursor.fetchall() if name in TELEMETRY_SESSIONS]

    event = event_folder(grandprix_name, year)
    written = 0
    for session_id, session_name in sessions:
        cursor.execute("SELECT COUNT(*) FROM TelemetryIndex WHERE SessionID = ?", (session_id,))
        already_indexed = cursor.fetchone()[0]

        # FastF1 loads a whole session in one go, so it is only used for sessions with
        # nothing indexed yet; a partly finished session is completed from TracingInsights.
        if use_fastf1 and already_indexed == 0:
            results = _fastf1_results(year, round_number, grandprix_name, session_name, strict=source == "fastf1")
            if results is not None:
                for entry, df, missing in results:
                    if df is None:
                        continue
                    driver_id, driver_name = resolve_driver(entry, drivers, grandprix_drivers)
                    path = Path(out_root) / str(year) / str(grandprix_id) / str(session_id) / f"{driver_id}.parquet"
                    _store(cursor, df, path, SOURCE_FASTF1, grandprix_name, session_name, driver_name,
                           grandprix_id, session_id, driver_id)
                    written += 1
                    note = f" ({missing} laps without telemetry)" if missing else ""
                    print(f"Telemetry saved for {grandprix_name} {session_name} {driver_name} [FastF1]{note}")
                continue
        if source == "fastf1":
            continue

        folder = session_folder(session_name, year)
        meta = fetch_json(year, f"{event}/{folder}/drivers.json", base_urls)
        if meta is None:
            print(f"Telemetry not available yet for {grandprix_name} {session_name}")
            continue

        for entry in meta["drivers"]:
            driver_id, driver_name = resolve_driver(entry, drivers, grandprix_drivers)
            path = Path(out_root) / str(year) / str(grandprix_id) / str(session_id) / f"{driver_id}.parquet"

            cursor.execute("SELECT 1 FROM TelemetryIndex WHERE SessionID = ? AND DriverID = ?", (session_id, driver_id))
            if cursor.fetchone() and path.exists():
                continue

            df, missing = driver_frame(year, event, folder, entry["driver"], base_urls)
            if df is None:
                continue
            _store(cursor, df, path, SOURCE_TRACINGINSIGHTS, grandprix_name, session_name, driver_name,
                   grandprix_id, session_id, driver_id)
            written += 1
            note = f" ({missing} lap files missing upstream)" if missing else ""
            print(f"Telemetry saved for {grandprix_name} {session_name} {driver_name}{note}")
    return written


def main():
    parser = argparse.ArgumentParser(description="Write TracingInsights telemetry Parquet files without touching the database.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--event", required=True, help='e.g. "Australian Grand Prix"')
    parser.add_argument("--session", required=True, help='e.g. "Race", "Qualifying", "Practice 1"')
    parser.add_argument("--drivers", nargs="*", help="three-letter codes; default is every driver in the session")
    parser.add_argument("--out", default=str(TELEMETRY_DIR))
    parser.add_argument("--base-url", dest="base_urls", nargs="+", default=BASE_URLS,
                        help="URL templates with {year} and {path}, tried in order")
    args = parser.parse_args()

    folder = session_folder(args.session, args.year)
    codes = args.drivers
    if not codes:
        meta = fetch_json(args.year, f"{args.event}/{folder}/drivers.json", args.base_urls)
        if meta is None:
            raise SystemExit(f"No telemetry published for {args.event} {folder}")
        codes = [entry["driver"] for entry in meta["drivers"]]

    for code in codes:
        df, missing = driver_frame(args.year, args.event, folder, code, args.base_urls)
        if df is None:
            print(f"{code}: no data")
            continue
        path = Path(args.out) / str(args.year) / args.event / args.session / f"{code}.parquet"
        write_parquet(df, path)
        print(f"{code}: {df['lap'].nunique()} laps, {len(df):,} rows, {path.stat().st_size / 1024:.0f} KB, {missing} lap files missing")


if __name__ == "__main__":
    main()
