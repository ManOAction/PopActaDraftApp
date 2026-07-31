# Architecture & working environment

Two things in one document: **what the system is** and **what it's like to work in this repo**.
The second half exists because several of this environment's quirks have already cost real time.

---

## System shape

Single user, single draft, one machine. There is no multi-tenancy, no auth, and no shared state
between people. That is a deliberate constraint, not a gap — see `docs/roadmap.md`.

```
  FantasyPros CSV export ────┐
  (projections: raw stats)   │
                             ├──► import ──► SQLite ──► FastAPI ──► React (web/)
  FantasyPros CSV export ────┤     (api/)              (api/)
  (rankings: ADP, std dev,   │        ▲
   tier, bye)                │        │
                             │        │ league config + live picks
  Sleeper public API ────────┴────────┘
  (no auth, ~1000 req/min)
```

**Three inputs, one store, one reader.**

- **Projections** and **rankings** arrive as CSVs pulled by hand from FantasyPros. They are not
  fetched at runtime — the free API tier caps every endpoint at 10 rows and is unusable. See
  `docs/reference_fantasypros_exports.md`.
- **Sleeper** supplies league configuration (roster positions, scoring rules) and, during the
  draft, the picks themselves. Public and read-only, so no credentials are involved.
- **SQLite** holds everything. One user means no concurrency pressure and no reason for anything
  larger.

### Why the data flows this way

The 2025 app made the user type league settings into a form. Those hand-entered values fed the
VORP baseline directly, and they were wrong — superflex was approximated as "every team starts 2
QBs." **Configuration is now derived, never entered.** If a number can come from Sleeper, it must.

Projections are **recomputed from raw stats** using the league's own scoring rules rather than
read from the CSV's `FPTS` column. Verified equivalent today, but recomputation means a
commissioner changing a scoring setting in mid-August is a non-event instead of a silent
wrong-number bug.

### Draft-day runtime constraints

The draft is **slow** — a 1-hour pick timer, spread over days. Sleeper handles notifying you when
you're on the clock, so this app does not.

- No external API call may sit in a blocking path.
- All data must be loaded days in advance.
- State survives a refresh. Undo always works.
- Manual pick entry is a first-class path, not a fallback — Sleeper sync failing must be an
  inconvenience, not a disaster.

---

## Repository layout

| Path | Role | Notes |
| --- | --- | --- |
| `api/` | Backend (Python/FastAPI) | **Empty scaffold.** |
| `web/` | Frontend (React/TS/Vite/Tailwind/shadcn) | **Empty scaffold.** |
| `data/fantasypros/` | Projection CSV exports | Committed — small, and reproducibility matters |
| `analytics/` | NFL scraper + ELO | Parked; `analytics/CLAUDE.md` |
| `infra/` | Compose + Caddy | Not yet written |
| `legacy/` | 2025 app | Read-only; `legacy/CLAUDE.md` |
| `docs/` | Reference | Reached via the map in root `CLAUDE.md` |

Nothing runs yet. Commands go in root `CLAUDE.md` **in the same commit that introduces them**.

---

## Working environment

| | |
| --- | --- |
| OS | Windows 11 Pro (26200) |
| Shells | PowerShell 7 (primary), Git Bash (POSIX) — each needs its own syntax |
| Python | 3.13, at `C:\Program Files\Python313` |
| Repo path | `G:\My Drive\Repos\PopActaDraftApp` — **on Google Drive** |
| Editor | VS Code |

### Platform gotchas

These have each already cost time. They are not hypothetical.

**The repo lived on Google Drive, and is being moved off it (2026-07-31).** The path contained a
space (`My Drive`), so every shell command needed quoting. Worse, `npm install` **fails outright**
there — exit 13, `EBADF: bad file descriptor, write`, partway through writing `web/node_modules`.
Drive's sync layer does not survive npm's write pattern. `uv sync` on the same path succeeded, so
this is npm-specific rather than a general filesystem failure. Tracked as BLK-8 in
[open-issues.md](open-issues.md).

**`.venv/` and `node_modules/` do not survive a move.** Both hardcode absolute paths, and both are
gitignored, so git does not carry them. After relocating, delete any copies and reinstall — don't
debug a venv that still thinks it lives on `G:\`.

**Windows Python cannot resolve Git Bash's `/tmp`.** A script invoked as `python /tmp/x.py` from
Bash fails with `FileNotFoundError`, because Python interprets `/tmp` as `C:\tmp`. Use the
session scratchpad directory with a full Windows path instead.

**The console is cp1252, not UTF-8.** Printing any non-ASCII character (`Δ`, `—`, box drawing)
raises `UnicodeEncodeError: 'charmap' codec can't encode`. Prefix with `PYTHONIOENCODING=utf-8`
when output may contain non-ASCII.

**`.gitignore` rules must be path-agnostic.** The original file scoped rules to `frontend/...`;
the 2026-07 relayout moved that directory and instantly unignored ~30k `node_modules` files.
Match by name (`node_modules/`), never by location.

**Use `git mv` when relocating tracked files** so rename detection preserves history. Note it
fails on untracked paths — `docs/` was untracked during the relayout and needed a plain `mv`.

### Conventions for agent sessions

- **Temp files go in the session scratchpad**, never in the repo and never in `/tmp`. A stray
  script in the working tree becomes a stray file on Google Drive.
- **`legacy/` is read-only.** Read it, cite it, never edit or import it.
- **Verify before asserting.** This project has already been wrong about the FantasyPros API tier
  limit, the CSV column order, and whether the league's scoring was custom. All three were
  settled by running something, not by reasoning about it.
- **Check that code exists before referencing it.** `api/` and `web/` are empty. Docs describing
  planned behaviour are labelled with a status line; treat unlabelled description as aspiration.

### Secrets

`.env` files are gitignored. Nothing currently requires a credential — Sleeper is unauthenticated
and FantasyPros data arrives as files. A FantasyPros API key exists but the free tier is unusable,
so **no component depends on it**; don't add one without revisiting `docs/roadmap.md`.
