# Contributing to f1resultsdatabase

Contributions are welcome! This project aims to be the most comprehensive database containing all the information about Formula 1 since 1950. **If any information is missing, we want to add it.** Whether you fix a single wrong lap time from 1974 or add an entire new table, it helps.

You don't need to be a programmer to contribute. See [Contributing without code](#contributing-without-code).

## Table of Contents
- [Code of Conduct](#code-of-conduct)
- [Ways to contribute](#ways-to-contribute)
- [Setting up](#setting-up)
- [The workflow](#the-workflow)
- [Reporting data inaccuracies](#reporting-data-inaccuracies)
- [Requesting features](#requesting-features)
- [Working on the code](#working-on-the-code)
- [Changing the schema](#changing-the-schema)
- [Testing your changes](#testing-your-changes)
- [Contributing without code](#contributing-without-code)
- [Licensing](#licensing)

## Code of Conduct

This project is governed by our [Code of Conduct](CODE_OF_CONDUCT.md), adapted from the Contributor Covenant 3.0. By participating — in issues, pull requests, or anywhere else in the project — you are expected to uphold it.

The short version: engage kindly and honestly, respect different viewpoints, take responsibility for your actions, and credit your sources. That last one matters especially here, since this is a data project built on other people's research and record-keeping.

If you witness or experience unacceptable behaviour, the Code of Conduct explains how to report it.

## Ways to contribute

1. **Report data inaccuracies.** A wrong result, a missing driver, a lap time that doesn't match the official timing sheets.
2. **Fill in missing data.** Check the [roadmap](ROADMAP.md) for what we know is missing.
3. **Request features.** New tables, new columns, new sources.
4. **Fix bugs or write code.** Check the [issues section](https://github.com/mclarenmp4-22/f1resultsdatabase/issues), especially the ones labelled `good first issue`.
5. **Improve Wikipedia race reports.** See [Contributing without code](#contributing-without-code).

If you're not sure where to start, open an issue and ask.

## Setting up

You'll need Python 3.9 or later (the code uses `zoneinfo`).

```bash
git clone https://github.com/mclarenmp4-22/f1resultsdatabase.git
cd f1resultsdatabase
pip install -r requirements.txt
```

Then either download the latest database from [Releases](https://github.com/mclarenmp4-22/f1resultsdatabase/releases/latest), or build one from scratch:

```bash
python updaters/reset.py   # creates sessionresults.db with all tables, empty
python writedb.py          # populates it (this takes a long time)
```

Note that `sessionresults.db` is in `.gitignore`. **Never commit the database file.** The database is distributed through Releases, not through git.

## The workflow

1. Fork the repository.
2. Create a new branch for your changes. **Do not work on the main branch!**
3. Make your changes.
4. Test them (see [Testing your changes](#testing-your-changes)).
5. Submit a Pull Request with a detailed description of your updates.

For major changes, please open an issue first to discuss what you would like to change. This saves you from writing code that goes in a direction we can't merge.

In your Pull Request, please include:
- What you changed and why.
- Which seasons or races you tested against.
- Your sources, if you're changing data (see below).
- Whether the schema changed, and where you updated it.

## Reporting data inaccuracies

Open an issue with the label `data error` and include:

- **The race, season, and session.** e.g. "1982 Monaco Grand Prix, Race".
- **The table and column.** e.g. `GrandPrixResults.racestatus`.
- **What the database says** and **what it should say**.
- **A source.** This matters more than anything else.

Good sources, roughly in order of how much we trust them: official FIA documents and F1.com timing sheets, [StatsF1](https://www.statsf1.com), [Motorsport Stats](https://motorsportstats.com), [GP Racing Stats](https://gpracingstats.com), then Wikipedia. If two sources disagree, say so in the issue — historical F1 data genuinely conflicts sometimes, and knowing that a conflict exists is useful in itself.

## Requesting features

Open an issue with the label `feature request`. Describe what data you want, where it can be found, and how far back it goes. The [roadmap](ROADMAP.md) lists what's already planned — check it first so we don't end up with duplicates.

## Working on the code

A few conventions this project follows. These are not stylistic preferences; breaking them tends to produce silently wrong data.

**1. Check the schema before you write a query.** Always verify in the [README](README.md) that you're selecting the column you think you are. Column names across tables are similar and it is easy to grab the wrong one.

**2. Think like an F1 expert, and account for the historical caveats.** This is the single biggest source of bugs in this project. Formula One is 75 years of changing rules, and code that assumes today's rules will quietly produce wrong data for older seasons. Before you assume anything, ask what caveat you haven't accounted for:

- Shared cars (two drivers, one car, split points) — common in the 1950s.
- Pre-qualifying sessions (late 1980s and early 1990s).
- Scoring systems that changed repeatedly, including dropped-scores rules where not every result counted towards the championship.
- The 1952 and 1953 seasons run to F2 regulations.
- Races stopped and restarted, with aggregate or part-points results.
- Half points.
- Sprint weekends, which change the session structure entirely.
- Data availability cliffs: lap times start in 1996, sector times and tyre data in 2018, pit stops in 1983.

At the same time, don't overthink it. Ask as many questions as you need in the issue.

**3. Fail loudly.** Do not add broad `try`/`except` blocks unless they are absolutely necessary. If something fails, we want it to fail visibly so it gets fixed. A silent `except: pass` that swallows a scraping error means the database quietly ends up with missing rows, and nobody notices for months. That is far worse than a crash.

**4. Be considerate to the sources.** The scrapers hit StatsF1, Motorsport Stats, Pitwall, Wikipedia, and others. Keep the existing rate limiting and random pauses in place. The Wikipedia REST API in particular only allows 500 requests per hour.

### Where things live

| Path | What it does |
|---|---|
| `writedb.py` | The main scraper and writer. Running it updates the database. |
| `updaters/reset.py` | Creates the database and every table. The schema lives here. |
| `updaters/deleteseason.py` | Deletes one season, for re-scraping. |
| `updaters/deleterace.py` | Deletes one race, for re-scraping. |
| `updaters/updaterace.py` | Re-syncs one race's result with StatsF1 after a post-race change, plus the standings and statistics that depend on it. |
| `updaters/update_stats_alone.py` | Recomputes derived statistics. |
| `scrapers/` | Standalone scrapers for specific data (engine models, historical practice sessions). |

The delete scripts are debugging tools. They do not clear every table containing data for that season or Grand Prix, so don't treat them as a full undo.

## Changing the schema

If you add or change a table or a column, you must update **all three** of these, in the same Pull Request:

1. **`updaters/reset.py`** — so a fresh database is created with your change.
2. **`README.md`** — so the schema documentation matches reality. This is what everyone reads.
3. **`writedb.py`** — so the column actually gets populated.

A schema change that misses any one of these will break someone else's setup. Please double-check this before opening the PR.

Also note: for boolean columns, SQLite stores `1` for true and `0` for false. Follow the existing convention rather than storing strings.

## Testing your changes

There is no automated test suite yet. Test manually, and say in your PR what you tested.

The usual approach is to delete and re-scrape a small slice of the database rather than rebuilding all 75 seasons:

```bash
python updaters/deleteseason.py 1957   # or deleterace.py "2026 Japanese Grand Prix"
python writedb.py
```

Then query the affected tables and confirm the numbers match your source.

Pick your test seasons deliberately. If you touched anything to do with results, points, or session structure, test at least one season from the 1950s, one from the 1990s, and one recent one. A change that works perfectly for 2026 and breaks 1954 is the most common failure mode in this project.

If you only changed race reports:

```bash
python writedb.py --updateracereport 2025
```

## Contributing without code

Even if you don't have any code to contribute, you can still help.

Suggest new features by opening an issue. Or contribute to the Wikipedia pages of race reports. Currently, a lot of the race report pages don't have enough data showing what happened. You can change that by editing and contributing to the Wikipedia pages of race reports. This helps both the F1 community as well as this database, since the `RaceReports` table is built from Wikipedia.

Verifying existing data against primary sources and reporting what's wrong is also genuinely valuable, and needs no programming at all.

## Licensing

This project uses a split licence. By contributing, you agree that your contributions are licensed under the same terms:

- **Code** under the [GNU General Public License v3](LICENCE.txt).
- **Data** under the [Open Database License v1.0](DATA-LICENCE.txt).

This keeps both the scraper and the compiled historical data open and accessible to everyone, permanently.

---

Anything that can make this database more comprehensive helps. Thank you for contributing.
