# analytics/ — PARKED

Standalone NFL team-analysis project: scrapes game results from pro-football-reference into
`nfl_stats.db`, computes ELO ratings and division-strength metrics.

**It has no connection to the draft copilot and is not part of the 2026-08-28 delivery.**

## Rules

- **Do not work on this before draft day** unless explicitly asked. It is off the critical path.
- It analyses **team** outcomes; the copilot needs **player** projections. Nothing here feeds the
  app today.
- Self-contained: its own `requirements.txt`, its own `venv/`, its own SQLite file. Don't wire it
  into `api/`.

## Why it's kept

Post-season, strength-of-schedule is a genuine input to a projection model, and the ELO work in
`nfl_analysis.py` is the seed for that. See the deferred section of
[`../docs/roadmap.md`](../docs/roadmap.md).

## If you do touch it

- `nfl_scraper.py --csv data/` loads the season CSVs in `data/`; `--list` shows DB stats.
- `nfl_analysis.py --elo`, `--div-strength`, `--standings --year YYYY`.
- Scraping pro-football-reference has a deliberate 3s delay between requests. Keep it.
- The scraper's HTML path is fragile. Post-season, the nflverse packages replace most of this and
  provide player-level data, which is what a projection model actually needs.
