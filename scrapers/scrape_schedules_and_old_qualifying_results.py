import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from seleniumbase import sb_cdp

"""
Usage:
scraper = ScQScraper()
scraper.launch(1961, 1)
schedule = scraper.scrape_schedule()
quali = scraper.scrape_qualifying()
"""

# Pulls the race's session list and circuit time zone out of the Next.js
# server-rendered payload (self.__next_f). That payload only exists on a FULL
# page load; after a client-side navigation (e.g. clicking a list item) it
# still holds the previous page's data.
_SCHEDULE_JS = r"""
(() => {
  const joined = (self.__next_f || [])
    .map(c => typeof c[1] === 'string' ? c[1] : '').join('');
  const key = '"sessions":[';
  let from = 0, idx, sessions = null;
  while ((idx = joined.indexOf(key, from)) !== -1) {
    let depth = 0, i = idx + key.length - 1;
    for (; i < joined.length; i++) {
      if (joined[i] === '[') depth++;
      else if (joined[i] === ']' && --depth === 0) break;
    }
    try {
      const arr = JSON.parse(joined.slice(idx + key.length - 1, i + 1));
      if (arr.length && arr[0].name) { sessions = arr; break; }
    } catch (e) {}
    from = idx + key.length;
  }
  if (!sessions) return null;
  const tz = joined.match(/"timeZone":"([^"]+)"/);
  return JSON.stringify({timeZone: tz ? tz[1] : null, sessions});
})()
"""

# Reads the classification table on a /results/qualifying[/N] page. Columns
# differ by race ("Note" and "Laps" are optional), so rows are keyed by the
# header text. Driver/Team/Constructor also get an "<col>_id" from their link
# (e.g. /drivers/jim-clark -> "jim-clark"). Returns null when there is no
# table (the site's 404 page).
_RESULT_TABLE_JS = r"""
(() => {
  const t = document.querySelector('table[class*="ResultTable"]');
  if (!t) return null;
  const headers = [...t.querySelectorAll('thead th')].map(th => th.textContent.trim());
  const rows = [...t.querySelectorAll('tbody tr')].map(tr => {
    const row = {};
    [...tr.children].forEach((td, i) => {
      const h = headers[i] || ('col' + i);
      row[h] = td.innerText.trim().replace(/\s+/g, ' ');
      const a = td.querySelector('a[href]');
      if (a) row[h + '_id'] = a.getAttribute('href').split('?')[0].split('/').filter(Boolean).pop();
    });
    return row;
  });
  return JSON.stringify({headers, rows});
})()
"""

# The race page header has prev/next links to the neighbouring races in the
# season (class names are CSS-module hashed, so match on the stable prefix).
# This reads the live DOM, so it also works after client-side navigation.
_NEXT_RACE_JS = r"""
(() => {
  const a = document.querySelector('a[class*="header_next"][href^="/races/"]');
  return a ? a.href : null;
})()
"""

SESSION_LABELS = {
    "P1": "Practice 1", "P2": "Practice 2", "P3": "Practice 3",
    "Q": "Qualifying", "Q1": "Qualifying 1", "Q2": "Qualifying 2", "Q3": "Qualifying 3",
    "R": "Race",
}


class ScQScraper:
    def __init__(self):
        self.sb = sb_cdp.Chrome(incognito=True)
        self.launched = False
        self.current_page = None
        self.race_page = None
        self.next_page = None

    def __slow_scroll_to_bottom(self, step=400, pause=0.15):
        # sb_cdp has no slow_scroll_to(), so scroll in steps until the bottom.
        # Loads lazy content and looks less robotic than a jump.
        while self.sb.evaluate(
            "window.innerHeight + window.scrollY < document.documentElement.scrollHeight - 2"
        ):
            self.sb.scroll_by_y(step)
            self.sb.sleep(pause)

    def __handle_page_change(self, url):
        self.sb.goto(url)
        self.sb.sleep(8)
        self.sb.solve_captcha()
        self.__slow_scroll_to_bottom()
        self.sb.sleep(2.5)
        self.current_page = url
        if re.search(r"/races/[^/?#]+/?$", url.split("?")[0]):
            self.__update_next_page()

    def launch(self, season, round):
        if self.launched:
            return
        attempts = 3
        for attempt in range(1, attempts + 1):
            self.__handle_page_change(f"https://www.formula1db.com/races?season={season}&round={round}")
            self.sb.sleep(4)
            # The site is flaky here: the list item is sometimes missing or the
            # click doesn't navigate. Retry those, but fail loudly on the last.
            try:
                self.sb.click("ul#race-name-list li:nth-child(1)")
                self.sb.sleep(2.5)
                # Clicking a race changes the browser location, but
                # __handle_page_change above only recorded the index URL. Keep
                # the actual race URL so the first scrape doesn't navigate back
                # to /races/.
                current = self.sb.get_current_url()
                if not re.search(r"/races/[^/?#]+/?(?:[?#].*)?$", current):
                    raise RuntimeError(
                        f"Expected a race detail page after selecting season {season} "
                        f"round {round}, got {current!r}"
                    )
            except Exception:
                if attempt == attempts:
                    raise
                continue
            self.current_page = self.race_page = current
            self.__update_next_page()
            self.launched = True
            return

    def scrape_schedule(self, race_url=None):
        """
        Returns the race weekend schedule in the circuit's LOCAL time
        (not "My time"), e.g. for https://www.formula1db.com/races/1961-monaco-grand-prix

        Each item: session, code, date, time, start_local, end_local,
        start_utc, timezone. Monaco 1961 has Q1, Q2 and Q3, all returned.
        Sessions with no known start time (Monaco 1961 Q1) come back with
        date/time/start_local = None.
        """
        if race_url is None:
            race_url = self.race_page
        race_url = race_url.split("?")[0].split("#")[0]
        # Full page load so __next_f holds THIS race's data. Navigating to the
        # URL the browser is already on (e.g. right after launch() clicked into
        # it) doesn't refresh the payload, so leave the page first. The payload
        # is in the initial HTML, so waiting doesn't help when it's missing;
        # only a fresh load does.
        attempts = 3
        for attempt in range(1, attempts + 1):
            self.sb.goto("about:blank")
            self.sb.sleep(1)
            self.__handle_page_change(race_url)
            raw = self.sb.evaluate(_SCHEDULE_JS)
            if raw:
                break
        else:
            raise RuntimeError(f"No sessions payload found on {race_url} after {attempts} loads")

        data = json.loads(raw)
        tz = ZoneInfo(data["timeZone"]) if data.get("timeZone") else None

        def to_local(iso):
            if not iso:
                return None
            utc = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return utc.astimezone(tz) if tz else utc

        schedule = []
        for s in sorted(data["sessions"], key=lambda x: x.get("order", 0)):
            start = to_local(s.get("startTime"))
            end = to_local(s.get("endTime"))
            schedule.append({
                "session": SESSION_LABELS.get(s["name"], s["name"]),
                "code": s["name"],
                "date": start.strftime("%Y-%m-%d") if start else None,
                "time": start.strftime("%H:%M") if start else None,
                "start_local": start.isoformat() if start else None,
                "end_local": end.isoformat() if end else None,
                "start_utc": s.get("startTime"),
                "timezone": data.get("timeZone"),
                "cancelled": s.get("cancelled", False),
            })
        return schedule

    def __scrape_results_table(self, url):
        """Returns a list of row dicts. Raises if the page has no table."""
        self.__handle_page_change(url)
        raw = self.sb.evaluate(_RESULT_TABLE_JS)
        if not raw:  # slow render? one retry
            self.sb.sleep(3)
            raw = self.sb.evaluate(_RESULT_TABLE_JS)
        if not raw:
            raise RuntimeError(f"No results table found on {url}")
        return json.loads(raw)["rows"]

    def scrape_qualifying(self, race_url=None, schedule=None):
        """
        Scrapes the "Qualifying" section of a race, e.g. for
        https://www.formula1db.com/races/1961-monaco-grand-prix

        The race's own schedule says which qualifying sessions exist (codes
        Q1, Q2, Q3, or a bare Q), so only those pages are loaded. Pass the result of
        scrape_schedule() as `schedule` to avoid loading it a second time.

        Returns {"overall": [...], "sessions": {1: [...], 2: [...], 3: [...]}}
          - "overall" is /results/qualifying (the combined classification)
          - "sessions" has one entry per Q<N> in the schedule, fetched from
            /results/qualifying/N, so Monaco 1961 gives 1, 2 and 3.
        Each row is keyed by the table headers (Pos., No., Driver, Team,
        Constructor, Time, Gap, Interval, plus Laps / Note when present), with
        extra Driver_id / Team_id / Constructor_id keys. Values are the site's
        raw text: "-" means none, "?" means unknown.
        A bare Q gives only "overall". Races whose schedule has no Q sessions
        return empty results without loading any page. A listed session with no results
        table raises.
        """
        if race_url is None:
            race_url = self.race_page
        race_url = race_url.split("?")[0].split("#")[0].rstrip("/")
        race_url = re.sub(r"/(entries|results)(/.*)?$", "", race_url)
        base = f"{race_url}/results/qualifying"

        if schedule is None:
            schedule = self.scrape_schedule(race_url)
        codes = [s["code"] for s in schedule if re.fullmatch(r"Q\d*", s["code"])]
        if not codes:
            return {"overall": [], "sessions": {}}
        # A bare "Q" (e.g. 1953 Argentina) is a single session whose results
        # live only on the overall page; Q1/Q2/Q3 also have /qualifying/N.
        numbers = sorted(int(c[1:]) for c in codes if len(c) > 1)

        overall = self.__scrape_results_table(base)
        sessions = {n: self.__scrape_results_table(f"{base}/{n}") for n in numbers}
        return {"overall": overall, "sessions": sessions}

    def __update_next_page(self):
        """Populate self.next_page from the race page currently loaded.
        Set to None when there is no next link (e.g. last race in the data)."""
        url = self.next_page = self.sb.evaluate(_NEXT_RACE_JS)
        if not url:  # slow render? one retry
            self.sb.sleep(2)
            url = self.sb.evaluate(_NEXT_RACE_JS)
        self.next_page = url or None

    def go_to_next_race(self):
        """
        Navigates to the next race using self.next_page and returns its URL,
        or None if there is no next race. A full page load is used, so
        scrape_schedule() / scrape_qualifying() work right after it.
        """
        if not self.next_page:
            return None
        url = self.next_page
        self.__handle_page_change(url)
        self.race_page = url
        self.__update_next_page()  # now points at the race after this one
        return url    

    def close_session(self):
        self.sb.quit()