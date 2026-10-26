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
    "Q1": "Qualifying 1", "Q2": "Qualifying 2", "Q3": "Qualifying 3",
    "R": "Race",
}


class ScQScraper:
    def __init__(self):
        self.sb = sb_cdp.Chrome(incognito=True)
        self.launched = False
        self.current_page = None
        self.next_page = None

    def __handle_page_change(self, url):
        self.sb.goto(url)
        self.sb.sleep(4)
        self.sb.solve_captcha()
        self.sb.sleep(2.5)
        self.current_page = url
        if re.search(r"/races/[^/?#]+/?$", url.split("?")[0]):
            self.__update_next_page()

    def launch(self, season, round):
        if not self.launched:
            self.__handle_page_change(f"https://www.formula1db.com/races?season={season}&round={round}")
            self.sb.click("ul.race-list li.RaceIndexListItem_container__oTdbC:nth-child(1)")
            self.sb.sleep(2.5)
            self.__update_next_page()
            self.launched = True            

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
            race_url = self.sb.get_current_url()
        race_url = race_url.split("?")[0].split("#")[0]
        # Full page load so __next_f holds THIS race's data.
        self.__handle_page_change(race_url)

        raw = self.sb.evaluate(_SCHEDULE_JS)
        if not raw:
            self.sb.sleep(3)
            raw = self.sb.evaluate(_SCHEDULE_JS)
        if not raw:
            return []

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
        """Returns a list of row dicts, or None if the page has no table."""
        self.__handle_page_change(url)
        raw = self.sb.evaluate(_RESULT_TABLE_JS)
        if not raw:  # slow render? one retry before treating it as missing
            self.sb.sleep(3)
            raw = self.sb.evaluate(_RESULT_TABLE_JS)
        return json.loads(raw)["rows"] if raw else None

    def scrape_qualifying(self, race_url=None, max_sessions=5):
        """
        Scrapes the "Qualifying" section of a race, e.g. for
        https://www.formula1db.com/races/1961-monaco-grand-prix

        Returns {"overall": [...], "sessions": {1: [...], 2: [...], 3: [...]}}
          - "overall" is /results/qualifying (the combined classification)
          - "sessions" has one entry per /results/qualifying/N page that
            exists, so Monaco 1961 gives 1, 2 and 3, while 1961 Italian
            gives 1 and 2. Every N from 1 to max_sessions is tried and
            missing pages are skipped, so a gap (no Q1 but a Q2) still
            returns the Q2 data.
        Each row is keyed by the table headers (Pos., No., Driver, Team,
        Constructor, Time, Gap, Interval, plus Laps / Note when present), with
        extra Driver_id / Team_id / Constructor_id keys. Values are the site's
        raw text: "-" means none, "?" means unknown.
        Races with no qualifying data (e.g. 1953 Monaco) return empty results
        (after max_sessions + 1 page loads, since nothing is assumed missing).
        """
        if race_url is None:
            race_url = self.sb.get_current_url()
        race_url = race_url.split("?")[0].split("#")[0].rstrip("/")
        race_url = re.sub(r"/(entries|results)(/.*)?$", "", race_url)
        base = f"{race_url}/results/qualifying"

        # Every page is tried independently: a missing overall page or a
        # missing Q1 doesn't mean Q2/Q3 are missing too.
        overall = self.__scrape_results_table(base) or []

        sessions = {}
        for n in range(1, max_sessions + 1):
            rows = self.__scrape_results_table(f"{base}/{n}")
            if rows is not None:
                sessions[n] = rows
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
        self.__update_next_page()  # now points at the race after this one
        return url    

    def close_session(self):
        self.sb.quit()