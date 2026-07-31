# PopActa Draft Copilot

A **personal draft-day copilot** for one user drafting in a Sleeper fantasy football league.
Not a draft platform — no accounts, no invites, no shared room. Sleeper runs the draft; this app
sits beside it and answers one question continuously:

> Given who's gone, who's left, what my roster needs, and when I pick again — who should I take?

**Draft day: 2026-08-28.** Everything is judged against that date and that sentence.

## Status

**Phase 0 complete (2026-07-31); Phase 1 is next.** The 2025 app was moved to `legacy/` and is
being rebuilt, not refactored. There is still **no working application** — `api/` holds a
toolchain and an empty package, `web/` holds a scaffold that renders a placeholder. Do not assume
any code exists; check before referencing it.

Phase 1 builds the domain core: draft seat, snake order, safe undo, roster slots as
position-eligibility sets, and picks-until-your-next-turn. See `docs/roadmap.md`.

## Layout

| Path | Role |
| --- | --- |
| `api/` | New backend (Python/FastAPI). Toolchain only — no application code yet. See `api/CLAUDE.md`. |
| `web/` | New frontend (React/TS/Vite/Tailwind v4/shadcn). Scaffold only. See `web/CLAUDE.md`. |
| `data/` | Input data. `data/fantasypros/` holds the projection and rankings CSV exports. |
| `analytics/` | NFL game scraper + ELO. **Parked** — see `analytics/CLAUDE.md`. |
| `infra/` | Docker Compose + Caddy. Not yet written. |
| `legacy/` | The 2025 app. **Read-only reference** — see `legacy/CLAUDE.md`. |
| `docs/` | Reference material, read on demand via the map below. |

## Commands

**Add commands here in the same commit that introduces them** — this table is the first place
anyone looks. Every command below was run and verified on 2026-07-31.

`api` commands run from the **repo root**; `--project api` means you never need to `cd`.
`web` commands run from **`web/`**.

| Task | Command |
| --- | --- |
| Install/sync (api) | `uv sync --project api` |
| Test (api) | `uv run --project api pytest api` |
| Lint (api) | `uv run --project api ruff check api` |
| Format (api) | `uv run --project api ruff format api` |
| Format check (api) | `uv run --project api ruff format --check api` |
| Dev server (api) | _not yet — no FastAPI app exists_ |
| Install (web) | `npm install` |
| Dev server (web) | `npm run dev` — http://localhost:5173 |
| Build + typecheck (web) | `npm run build` |
| Lint (web) | `npm run lint` |
| Format (web) | `npm run format` / `npm run format:check` |
| Screenshot (web) | `npm run screenshot [route] [--keep]` |

**Pass the `api` path to pytest.** `uv run --project api pytest` with no path argument sets
rootdir to the repo root, finds no config file, and silently ignores `api/pyproject.toml`'s
`[tool.pytest.ini_options]`. The tests still appear to pass, so the misconfiguration is invisible.

CI (`.github/workflows/ci.yml`) runs exactly these commands. Keep the two in sync — if CI and
local diverge, CI stops being evidence of anything.

## Documentation map — read on demand

- **Planning, prioritising, or asking "what's next"?** → `docs/roadmap.md`
- **Writing anything in `api/src/popacta/domain/`?** → `docs/plan_phase1_domain_core.md`
  (locked contracts — read it before the code, not after)
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

## Execution style
Before starting multi-step work, identify independent steps and
consider if they can be handled as concurrent subagents (multiple Agent calls in one
message). Only chain steps that genuinely depend on each other's output.
Read-only investigation should almost always be parallelized.  Propose multi-agent plans to the user to be confirmed.