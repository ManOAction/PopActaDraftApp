# PopActa Draft Copilot

A personal draft-day copilot for a single Sleeper fantasy football league.

It is **not** a draft platform — there are no accounts, no invites, no shared draft room. Sleeper
runs the draft; this app sits beside it and answers one question, continuously:

> Given who's gone, who's left, what my roster needs, and when I pick again — who should I take?

**Draft day: 2026-08-28.**

## Status

**Phase 0 — foundation.** The 2025 application was moved to `legacy/` and is being **rebuilt, not
refactored**.

There is **no working application yet**: `api/` has a verified toolchain and an empty package,
`web/` has a scaffold that builds and renders a placeholder. The domain core, decision engine, UI
and data import are Phases 1–5. See [`docs/roadmap.md`](docs/roadmap.md).

## The league

Pop Acta Premier League — Sleeper, 2026 redraft, verified from the API on 2026-07-31.

```
league_id  1385689586377687040    draft_id  1385689586394488832
teams      10                      type      snake, 16 rounds
starters   QB RB RB WR WR TE FLEX FLEX SUPER_FLEX DEF   (+6 BN, 1 IR)
scoring    Half-PPR · custom DST tiers
pick_timer 3600s (1 hour) — a slow draft spread over days
```

Two facts drive most of the design. **Superflex** means QB is startable in two slots, so standard
ADP is actively misleading for quarterbacks. And the **1-hour pick timer** means this is a
deliberative tool, not a fast one — legibility of the reasoning matters more than tap-speed.

League settings are always **derived from Sleeper, never hand-entered**. Hardcoding them is what
broke the 2025 app.

## Layout

| Path | Role |
| --- | --- |
| `api/` | Backend — Python, FastAPI, SQLAlchemy, SQLite. Toolchain only so far. |
| `web/` | Frontend — React 19, TypeScript, Vite, Tailwind v4, shadcn/ui. Scaffold only. |
| `data/` | FantasyPros CSV exports (projections and rankings). |
| `analytics/` | NFL scraper + ELO. Parked — off the critical path. |
| `infra/` | Docker Compose + Caddy. Not yet written. |
| `legacy/` | The 2025 app. Read-only reference; deleted after Phase 3. |
| `docs/` | Roadmap, architecture, open issues, feature and format references. |

## Requirements

- **Python 3.13** and [`uv`](https://docs.astral.sh/uv/)
- **Node.js 24+** and npm

## Getting started

```bash
git clone https://github.com/ManOAction/PopActaDraftApp.git
cd PopActaDraftApp

# Backend
uv sync --project api
uv run --project api pytest api      # the `api` path argument is required — see below

# Frontend
cd web
npm install
npm run dev                          # http://localhost:5173
```

## Commands

Backend commands run from the repo root; `--project api` means you never need to `cd`.

| Task | Command |
| --- | --- |
| Install/sync (api) | `uv sync --project api` |
| Test (api) | `uv run --project api pytest api` |
| Lint (api) | `uv run --project api ruff check api` |
| Format (api) | `uv run --project api ruff format api` |
| Install (web) | `npm install` *(in `web/`)* |
| Dev server (web) | `npm run dev` |
| Build (web) | `npm run build` |
| Lint (web) | `npm run lint` |
| Format (web) | `npm run format` |
| Screenshot (web) | `npm run screenshot [route] [--keep]` |

**Always pass the `api` path to pytest.** `uv run --project api pytest` with no path sets rootdir
to the repo root, finds no config file, and silently ignores `api/pyproject.toml`'s
`[tool.pytest.ini_options]`. The tests still appear to pass, so the misconfiguration is invisible.

`npm run screenshot` boots the dev server, captures `web/screenshots/mobile.png` and
`desktop.png`, and **exits non-zero if the page logged any console or page error** — so it doubles
as a render smoke test. CI runs it on every push.

## Design constraints

- **Draft-night reliability outranks everything.** State survives a refresh. Undo always works.
  No external API call sits in a blocking path. Manual pick entry is a first-class path, not a
  fallback bolted on late.
- **Mobile-first.** Drafting happens on a phone, not a five-column desktop grid.
- **Fail loudly at import time, never silently at draft time.** An unmatched player, a missing bye
  week, an unparsed column — raise. The 2025 app defaulted bad data to `0` and displayed wrong
  numbers all season.

## Contributing

This is a personal project with a fixed deadline, not an open-source product. If you are working
in it (human or agent), start with [`CLAUDE.md`](CLAUDE.md) — it maps which document to read for
which task. Per-area rules live in `api/CLAUDE.md` and `web/CLAUDE.md` and load automatically when
working in those directories.

## License

Unlicensed / all rights reserved. Personal project.
