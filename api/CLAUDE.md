# api/ — backend rules + Python style

FastAPI + SQLAlchemy + SQLite, managed by `uv`. This is the **new** backend; it shares no code
with `legacy/`.

**Status: toolchain only.** `src/popacta/` is an empty package. Check what exists before
referencing it.

Commands live in the root [`CLAUDE.md`](../CLAUDE.md). Always pass the path —
`uv run --project api pytest api`, never bare `pytest`.

## Area rules

- **Never import from `legacy/`.** Read it for reference, then write the new thing properly.
- **Fail loudly at import time, never silently at draft time.** No `except: pass`, no
  `.get(k, 0)` on data that must exist, no defaulting a failed parse. Raise with the offending
  row in the message. LEG-4 defaulted bye weeks to `0` on parse failure and every one of 527
  players displayed "Bye: 0" for a season.
- **Never hardcode league settings.** Roster slots, scoring, team count and round count come
  from Sleeper (`league_id 1385689586377687040`). A slot is a **set of eligible positions with a
  count** — mirror Sleeper's `roster_positions`. Integer columns per position cannot express
  superflex (LEG-1).
- **Pure domain logic stays free of the DB.** Snake order, pick math, VORP and survival
  probability are pure functions over plain values, unit-tested without a session. They are the
  part worth trusting on draft night.
- **Derive pick numbers from position in the draft order**, never `max(pick_number) + 1` — that
  is LEG-3, and it puts a permanent hole in the sequence the first time you undo.

## FastAPI / Pydantic

- **Every endpoint declares a `response_model`.** Returning ORM objects let client and server
  types drift silently all of 2025 (LEG-7).
- **Request models set `extra="forbid"`.** A field the UI sends that the model doesn't declare
  must be a 422, not a silent drop — that is exactly how `te_slots` became unsettable (LEG-2).
- Keep route handlers thin: parse, call a service, return. Logic belongs in `services/`.
- Schemas live in `schemas/` and are separate types from the ORM models in `models/`. Do not
  reuse one class for both.
- CORS: list the dev origin explicitly. `allow_origins=["*"]` with `allow_credentials=True` is
  an invalid combination browsers reject (LEG-9).

## Database

- **Every schema change is an Alembic migration.** "Drop and recreate" is not a migration
  (LEG-12). Never edit a migration that has been applied.
- SQLite, one user, one draft. No connection pooling story is needed.

## Python style

Ruff is the enforcement mechanism and its config in [`pyproject.toml`](pyproject.toml) is the
source of truth — line length 100, target `py313`, `ANN` on, `S110`/`S112` on so swallowed
exceptions are lint errors. Run `ruff check` and `ruff format` before claiming work is done.

Beyond what ruff checks:

- **Type hints on every public function**, including return types. `-> None` counts.
- **Prefer functions over classes.** Use a class when there is real state to hold; a module of
  functions is the default.
- Dataclasses (or Pydantic models) over dicts for anything with a fixed shape. A `dict[str, Any]`
  crossing a module boundary is a missing type.
- f-strings for interpolation. `pathlib.Path`, never `os.path`.
- Exceptions carry context: `raise ValueError(f"no Sleeper match for {name!r} (row {i})")`, not
  `raise ValueError("bad player")`. On draft night the message is the whole debugging session.

## Tests

- `pytest`, in `tests/`, mirroring the `src/popacta/` layout.
- **The domain core is tested exhaustively** — snake order, pick math, roster eligibility,
  survival probability. LEG-8 was "no tests, anywhere"; that is the defect this project most
  wants not to repeat.
- Test the boundaries, not the middle: CSV parsing against real fixture rows from
  `data/fantasypros/`, Sleeper responses against captured JSON. Do not mock the thing you are
  actually trying to verify.
- A bug fix starts with the failing test.
