# legacy/ — READ-ONLY REFERENCE

This is the **2025 application**. It is dead code, kept only so the rebuild can consult it.

## Rules

- **Never edit anything in here.** Bugs in this tree are not bugs to fix.
- **Never import from here.** The new app in `api/` and `web/` shares no code with it.
- **Never run it.** It expects an nginx/certbot stack that no longer exists and a SQLite file
  full of 2025 data.
- This directory is **deleted once Phase 3 completes**. Don't build anything that depends on it.

## What's worth reading, and why

| File | Read it for |
| --- | --- |
| `backend/app/services/vorp.py` | The replacement-level VORP idea. The *concept* is sound; the baseline is wrong (see below). |
| `backend/app/services/player_import.py` | CSV validation shape — per-row error collection is a good pattern worth keeping. |
| `frontend/src/pages/Draft.tsx` | What the board looked like, and the column visibility rule. |
| `backend/app/models.py` | The schema that could not express superflex. Instructive as a counterexample. |
| `code-style-from-other-project.md` | **Not this project's style guide.** Imported from an unrelated codebase (references `flurry.*`, `pendulum`, AWS secret loading). Kept only as a format example. |

## Do not reproduce these

Every one of these shipped and caused a real problem. Full list with detail in
[`../docs/open-issues.md`](../docs/open-issues.md).

- Roster slots as fixed integer columns (`qb_slots`, `rb_slots`, …) — **cannot express superflex**
- `flex_eligible_positions` hardcoded to `("RB","WR","TE")`
- `te_slots` missing from the update schema, so it silently could never be saved
- Pick numbers assigned as `max(actual_pick_number) + 1` — undo leaves permanent holes
- Bye weeks defaulted to `0` on parse failure, so every player showed "Bye: 0" all season
- VORP baseline computed against *global* remaining starters instead of your next pick
- Raw ORM objects returned from endpoints, so client and server types drifted
- No tests, anywhere
