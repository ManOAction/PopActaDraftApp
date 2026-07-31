# PopActa Draft Copilot

A **personal draft-day copilot** for one user drafting in a Sleeper fantasy football league.
Not a draft platform — no accounts, no invites, no shared room. Sleeper runs the draft; this app
sits beside it and answers one question continuously:

> Given who's gone, who's left, what my roster needs, and when I pick again — who should I take?

**Draft day: 2026-08-28.** Everything is judged against that date and that sentence.

## Status

**Phase 0 (foundation).** The 2025 app was moved to `legacy/` and is being rebuilt, not refactored.
There is **no working application** — `api/` holds a toolchain and an empty package, `web/` holds
only a `package.json`. Do not assume any code exists; check before referencing it.

**The repo is being relocated off Google Drive** — `npm install` fails there with `EBADF`
(BLK-8 in `docs/open-issues.md`). `web/` work is blocked until the move completes. See
*Resume here after the repo is relocated* in `docs/roadmap.md`.

## Layout

| Path | Role |
| --- | --- |
| `api/` | New backend (Python/FastAPI). Toolchain only — no application code yet. |
| `web/` | New frontend (React/TS/Vite/Tailwind/shadcn). **Not yet scaffolded** (BLK-8). |
| `data/` | Input data. `data/fantasypros/` holds the projection CSV exports. |
| `analytics/` | NFL game scraper + ELO. **Parked** — see `analytics/CLAUDE.md`. |
| `infra/` | Docker Compose + Caddy. Not yet written. |
| `legacy/` | The 2025 app. **Read-only reference** — see `legacy/CLAUDE.md`. |
| `docs/` | Reference material, read on demand via the map below. |

## Commands

**Add commands here in the same commit that introduces them** — this table is the first place
anyone looks. Every command below was run and verified on 2026-07-31.

Run these from the **repo root**; `--project api` means you never need to `cd`.

| Task | Command |
| --- | --- |
| Install/sync (api) | `uv sync --project api` |
| Test (api) | `uv run --project api pytest api` |
| Lint (api) | `uv run --project api ruff check api` |
| Format (api) | `uv run --project api ruff format api` |
| Format check (api) | `uv run --project api ruff format --check api` |
| Dev server (api) | _not yet — no FastAPI app exists_ |
| Everything under `web/` | _not yet — blocked by BLK-8_ |

**Pass the `api` path to pytest.** `uv run --project api pytest` with no path argument sets
rootdir to the repo root, finds no config file, and silently ignores `api/pyproject.toml`'s
`[tool.pytest.ini_options]`. The tests still appear to pass, so the misconfiguration is invisible.

## Documentation map — read on demand

- **Planning, prioritising, or asking "what's next"?** → `docs/roadmap.md`
- **Triaging a bug, or about to repeat a 2025 mistake?** → `docs/open-issues.md`
- **Need the system shape, the dev environment, or platform gotchas?** → `docs/architecture.md`
- **Working on draft recommendations, VORP, ADP, or survival math?** → `docs/FeatureDescription_PickAdvisor.md`
- **Parsing or importing a FantasyPros CSV?** → `docs/reference_fantasypros_exports.md`
  (read this *before* writing a parser — the column order is a trap)
- **Restructuring docs or context files?** → `docs/claude-context-structure-guide.md`

## Universal rules

- **This is a rebuild, not a refactor.** Never import from or edit `legacy/`. Read it for
  reference, then write the new thing properly.
- **Never invent league settings.** They come from Sleeper (`league_id 1385689586377687040`).
  Hardcoding roster slots or scoring is what broke the 2025 app.
- **Fail loudly at import time, never silently at draft time.** A player that doesn't match, a
  missing bye week, an unparsed column — raise. The 2025 app defaulted bad data to `0` and
  showed wrong numbers all season.
- **Draft day is 2026-08-28 and cannot slip.** When trading scope against reliability,
  reliability wins.
- Per-area rules live in each area's `CLAUDE.md`.
