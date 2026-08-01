# Roadmap — PopActa Draft Copilot

**Status:** active. Supersedes `feature-roadmap.md` (deleted — it described a multi-user
platform this project never was).

**Written:** 2026-07-31. **Hard deadline:** draft day, **2026-08-28** (28 days).

---

## What this is

A **personal draft-day copilot** for one user — you — drafting in a Sleeper league.

It is not a draft platform. There are no accounts, no invites, no shared draft room. Sleeper
runs the draft; this app sits beside it and answers one question, continuously:

> Given who's gone, who's left, what my roster needs, and when I pick again —
> who should I take?

Everything in this roadmap is judged against that sentence. Features that don't serve it are
out of scope, however interesting.

## League context

**Pop Acta Premier League** — Sleeper, 2026 redraft, verified from the API on 2026-07-31.

```
league_id  1385689586377687040        draft_id   1385689586394488832
teams      10                          type       snake, 16 rounds
starters   QB RB RB WR WR TE FLEX FLEX SUPER_FLEX DEF   (+6 BN, 1 IR)
scoring    Half-PPR (rec 0.5) · pass_yd 0.04 · pass_td 4 · int -1
           rush/rec_yd 0.1 · all TD 6 · fum_lost -2 · full DST tiers
pick_timer 3600s (1 hour)  ·  start_time null  ·  draft_order not yet set
```

Four consequences that drive the design:

1. **Superflex** (`SUPER_FLEX` slot) means QB is startable in two slots. Up to 20 of 10 teams'
   starters can be QBs. Positional value shifts hard toward QBs, and standard ADP is actively
   misleading for them.
2. **Offensive scoring is standard Half-PPR** — verified by recomputing FantasyPros' `FPTS` from
   raw stats across all 518 players; max deviation 0.62 pts, all of it rounding. Points are still
   recomputed from stats rather than read from `FPTS`, so a mid-August scoring change is a
   non-event. Only **DST scoring is custom** (points-allowed tiers), and DST is one low-variance
   slot. See [reference_fantasypros_exports.md](reference_fantasypros_exports.md).
3. **DEF is a required starter, but defenses are streamed and there is no K slot.** Neither
   position is projected, ranked, or recommended (BLK-2, closed by decision on 2026-07-31). Both
   still *parse*, because other teams draft defenses and Sleeper sends us those picks. The
   universe this app ranks is exactly QB/RB/WR/TE — which is also exactly what the FantasyPros
   superflex export contains.
4. **Sleeper's API is public and read-only** (no auth; ~1000 req/min). League config, scoring
   rules, and live draft picks are all fetchable — polling every few seconds during a draft is
   well within budget. This removes most manual data entry.

## Constraints

- **Draft-night reliability outranks everything.** State survives a refresh. Undo always works.
  No external API call sits in a blocking path. All data loaded days in advance. Manual pick
  entry always available as a fallback when auto-sync fails.
- **Mobile-first.** Drafting happens on a phone or tablet, not a five-column desktop grid.
- **Four weeks, part-time.** Scope is cut before quality or the deadline.

## Non-goals this cycle

Deliberately deferred to the off-season, listed so they stay deferred:

- Building an original projection model (import FantasyPros stat projections instead)
- The nflverse ingestion pipeline; ELO / strength-of-schedule as projection features
- Multi-user, auth, shared draft rooms
- Dynasty/keeper mechanics
- **User-configurable modelling choices.** Phase 2 freezes eight modelling decisions as named
  constants — replacement basis, tier threshold, survival distribution, lookahead depth, bench
  weight and others. Several get ground-truthed for the first time at the mock-draft rehearsal
  (OPEN-2), so exposing them as settings is a plausible off-season feature. They are deliberately
  given named homes now so this becomes a settings surface rather than a refactor. Full table in
  [`plan_phase2_decision_engine.md`](plan_phase2_decision_engine.md#configurable-in-a-later-cycle).
  **Constraint:** a knob may change model *inputs*, never add a term to the score — "each signal
  enters exactly once" is what keeps the recommendation explainable, and that is not negotiable.

`scripts/` (NFL scraper + ELO + division strength) **moved to `analytics/` and is parked**
(done 2026-07-31) — not deleted, not worked on. It analyses team outcomes; the copilot needs
player projections. Its ELO work becomes a projection feature later, not now. See
[`analytics/CLAUDE.md`](../analytics/CLAUDE.md).

---

## Architecture decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Projections/ADP source | **FantasyPros CSV export**, not their API | Verified 2026-07-31: the free API tier caps *every* endpoint at 10 rows (`public_api_limited: true`) — 10 of 768 ranked players, 10 of 8,509 in the player list. Unusable for a 160-pick draft. The web export is free, complete, and carries the same `Best/Worst/Avg/Std Dev/ADP/tier/bye` columns. Full access is prohibitively expensive. |
| Player ID matching | Sleeper `/v1/players/nfl` dump + normalized names + manual override list | Uncapped and free. Provides `search_full_name` and cross-platform IDs. Name matching (suffixes, DST naming, trades) is the top silent-failure risk for draft-night auto-sync. |
| Backend | Python + FastAPI, `uv`, `ruff`, `pytest` | Keeps the door open for the deferred modeling work. Toolchain modernised. |
| API contract | Pydantic request *and* response schemas | The old app returned raw ORM objects; types drifted silently between client and server. |
| Database | SQLite + Alembic | One user, one draft. The migration discipline is the lesson, not the engine. |
| Frontend | React + TS + Vite + Tailwind v4 + shadcn/ui | shadcn components live in-repo as editable source and are the strongest target for model-generated UI. DaisyUI is not. |
| Reverse proxy | **Caddy** | Automatic HTTPS in two lines. Replaces the nginx + certbot + Let's Encrypt story that was documented but never actually worked. |
| Layout | Multi-area monorepo: `api/` `web/` `analytics/` `infra/` | Nested `CLAUDE.md` files need areas to scope to. The structure is part of the workflow lesson. |

### Roster slots must be position-eligibility sets

The old schema hardcoded `qb_slots`, `rb_slots`, … as integer columns, with
`flex_eligible_positions = ("RB", "WR", "TE")` frozen in
[`vorp.py`](../legacy/backend/app/services/vorp.py). **Superflex cannot be expressed in that
model.**

The evidence is in last year's `app.db`, where the settings were hand-entered as:

```
stored:  qb_slots=2  rb_slots=3  wr_slots=3  te_slots=1  flex_slots=3
actual:  QB×1  RB×2  WR×2  TE×1  FLEX×2  SUPER_FLEX×1  DEF×1
```

Superflex was approximated as "every team starts 2 QBs" and FLEX by inflating RB/WR counts.
Those numbers feed the VORP replacement baseline directly — the engine was solving a league
that doesn't exist. DEF was unrepresentable and simply absent.

A slot is a **set of eligible positions with a count**. Sleeper's `roster_positions` already has
exactly that shape — mirror it, and sync it rather than typing it.

Cheap in Phase 1. Expensive if retrofitted in Phase 4.

### The keystone metric

The old VORP computed drop-off against *globally* remaining starters. The correct baseline is
**the best player still likely available at your next turn**. Same idea, right denominator.

That requires three things the old app had none of: your draft seat, snake pick math, and a
survival probability per player from ADP. Phases 1 and 2 exist to build exactly those.

---

## Phases

### Phase 0 — Foundation *(~3 days, hard timebox)*

Workflow scaffolding first, because it multiplies everything after — but if it isn't done in
three days, cut and move on.

**Done (2026-07-31):**

- [x] Repo relayout — `api/` `web/` `data/` `analytics/` `infra/` `legacy/`; old app moved to
      `legacy/` as read-only reference, `scripts/` parked as `analytics/`
- [x] Lean root [`CLAUDE.md`](../CLAUDE.md) as a trigger-oriented map
- [x] Nested `CLAUDE.md` guards for `legacy/` and `analytics/`
- [x] Deleted `feature-roadmap.md`; moved `docs/code-style.md` to `legacy/` (it was another
      project's rules file — `flurry.*`, `pendulum`, AWS secret loading)
- [x] `.gitignore` rewritten path-agnostic (the old `frontend/…`-scoped rules stopped matching
      the moment that directory moved)
- [x] Docs: [`architecture.md`](architecture.md), [`open-issues.md`](open-issues.md),
      [`FeatureDescription_PickAdvisor.md`](FeatureDescription_PickAdvisor.md)

**Also done (2026-07-31, later session):**

- [x] **Committed** — `d62b525` put the relayout and docs in git. They had existed only as
      uncommitted working-tree changes on a Drive folder.
- [x] `.gitattributes` normalising line endings to LF. Windows checkouts were rewriting every
      file to CRLF, which would make every `ruff format` / `prettier` run show whole-file diffs.
- [x] `api/` Python toolchain: `uv` + `ruff` + `pytest`, **verified green** — see Commands in
      root [`CLAUDE.md`](../CLAUDE.md). `api/uv.lock` committed.

**Also done (2026-07-31, after relocation to `C:\Projects\PopActaDraftApp`):**

- [x] **BLK-8 closed.** `npm install` succeeds at the new path — 184 packages, exit 0. The Google
      Drive sync layer was the entire cause; no repo change was needed.
- [x] `web/` scaffold — Vite 8 + React 19 + TS + Tailwind v4 + shadcn-ready. Builds, lints,
      typechecks, formats clean. **TypeScript pinned to `~6.0.3`**: TS 7 is out, but
      `typescript-eslint@8` still declares `typescript <6.1.0`, so TS 7 would mean no type-aware
      linting. Revisit once typescript-eslint supports it.
- [x] Browser automation — `npm run screenshot` boots the dev server, captures mobile + desktop,
      and **exits non-zero on any console or page error**, so it doubles as a render smoke test.
- [x] `api/CLAUDE.md` and `web/CLAUDE.md` — area rules + language style, each citing the `LEG-*`
      defect it exists to prevent
- [x] Sub-agents in `.claude/agents/`: `design-reviewer`, `draft-logic-verifier`, `test-writer`
- [x] GitHub Actions (`.github/workflows/ci.yml`) — three jobs (api, web, design-loop), running
      the same commands as the docs. Every step verified locally before pushing.
- [x] `README.md` rewritten for the 2026 rebuild

**Phase 0 is complete.** Next: Phase 1.

**Toolchain traps found while verifying** — recorded because they are exactly the class of silent
misconfiguration this project keeps losing time to:

1. `uv run --project api pytest` with **no path argument** sets rootdir to the repo root, finds no
   config file, and silently ignores `api/pyproject.toml`'s `[tool.pytest.ini_options]` —
   including `--strict-config`. Tests still appear to pass. Always pass the path:
   `uv run --project api pytest api`.
2. On Windows, `child.kill()` does **not** kill a process tree. The first screenshot script leaked
   a Vite server per run; the orphans held `lightningcss.win32-x64-msvc.node` open and made
   `npm ci` fail with `EPERM`. Fixed by killing the tree (`taskkill /T /F`, or the process group
   on POSIX). Any future spawned-process tooling needs the same treatment.

### Phase 1 — Domain core *(~3 days)*

Pure functions, no DB coupling, heavily tested. The part the old app never modeled.

**Detailed contracts, module signatures, agent ownership and acceptance criteria:
[`plan_phase1_domain_core.md`](plan_phase1_domain_core.md).** Read that before writing any
code in `api/src/popacta/domain/` — it locks the decisions that otherwise diverge.

- Draft seat; snake order; pick numbers **derived from position**, not counted with `max()+1`
- Safe undo — the old global counter left permanent holes in the sequence
- Roster slots as position-eligibility sets (superflex-capable)
- Your roster and its unfilled needs
- **Picks until your next turn** — the keystone the whole decision engine hangs off

**Phase 1 complete (2026-07-31).** Built in four waves — contracts single-authored, then
three modules implemented concurrently by independent agents, then adversarial verification
and cross-module integration. **903 tests**, lint and format clean.

- Wave 0: Sleeper payloads pinned as fixtures; `positions.py`, `league.py`, `errors.py`;
  signatures for the rest
- Wave 1: `snake.py`, `roster.py`, `draft.py` implemented in parallel against those
  signatures
- Wave 2: adversarial verification (no arithmetic defects; nine input-validation holes,
  all fixed) and a full 160-pick integration suite

The keystone was verified against an independently constructed board across all 10 seats ×
161 draft states with zero mismatches, and roster matching against a bitmask-DP oracle
across 30,000 random cases. Known limitations to carry into Phase 2 are listed in
[`plan_phase1_domain_core.md`](plan_phase1_domain_core.md).

### Phase 2 — Decision engine *(~4 days)*

Also pure and independently verifiable, which makes it the right place to practise adversarial
sub-agent review.

**Full contracts, formulas, module ownership and acceptance criteria:
[`plan_phase2_decision_engine.md`](plan_phase2_decision_engine.md).** Read it before writing any
Phase 2 code.

- VORP rebuilt against the next-pick-window baseline, with **superflex-aware** positional demand
- **Survival probability**: given ADP and its variance, will this player last until my next turn?
- Tier detection (gap-based clustering) — see the cliff before you fall off it
- Positional run detection

**Research complete (2026-08-01)** — four parallel passes, each independently verified. Two found
errors in existing docs: the `VONA` formula in
[`FeatureDescription_PickAdvisor.md`](FeatureDescription_PickAdvisor.md) **ranked backwards** (the
baseline must be added, not subtracted), and `BYE` was not complete in the rankings export.

Three findings that shaped the plan:

- **The SUPER_FLEX slot is not contested** — all 10 go to QBs, decided by 110 points. "Contested
  share" is 100% QB, robustly.
- **Replacement level uses draft demand** (`QB30`, not `QB21`) — decided 2026-08-01. 29 QBs come
  off the board in 160 picks, so punting QB gets you QB30, not a projected 493-attempt starter.
- **Greedy is exact only for Sleeper's slot order** and 397 points wrong under any other. The
  weighted lineup assignment uses a bitmask DP. Third occurrence of this pattern in the project.

**Partly blocked by BLK-1.** Projection import, replacement levels, the lineup DP and tier
detection are all buildable today; survival probability and the `Plan` assembly are not. Interim
degraded mode: rank on `u(p | R)` alone — classic VORP with the correct baseline.

### Phase 3 — UI *(~6 days)*

**This is a slow draft — 1 hour per pick, spread over days. Sleeper handles on-the-clock
notification, so the app does not.** Tap-speed is not a design constraint; *legibility of the
reasoning* is. You open the app with time to think, so the analysis can be deliberative and
dense rather than glanceable.

- shadcn/ui, mobile-first (checking on a phone between picks), visible undo
- Pick-window math and the *why* behind each recommendation always on screen
- Design loop runs hard here: agent renders → screenshots → critiques against a design-system
  doc → iterates
- Offline resilience; state survives refresh
- **Not building:** notifications, live-room tap-speed optimisations, draft-clock UI

### Phase 4 — Data in *(~2 days)*

- Sleeper sync: pull `roster_positions` and `scoring_settings` from the real league
- FantasyPros **Half-PPR preset** projection import (scoring verified standard — no stat-level
  export needed); must include **bye weeks**, which last year's import silently defaulted to 0
- Superflex ADP import
- Load real data; dry run

### Phase 5 — Ship *(~2 days)*

- Caddy + Docker Compose, real HTTPS, reachable from your phone
- **Full mock-draft rehearsal, end to end** — non-negotiable before draft day

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| **Superflex ADP source** | High — standard ADP makes every QB call wrong in the same direction | Identify the source in Phase 0, not Phase 4. Blocks survival probability. |
| Sleeper draft polling behaves differently live than in testing | High — auto-sync is the main draft-day UX | Manual entry is a first-class path, not a fallback bolted on late. Rehearse against a real mock draft. |
| FantasyPros→Sleeper name matching fails silently | High — a mismatched player never gets marked drafted | Match against Sleeper's `search_full_name`; fail **loudly** on any unmatched player at import time, not at draft time. Manual override list. |
| ADP shifts through August | Medium | Import is re-runnable; re-pull the export within days of the draft. |
| Four learning tracks eat the schedule | Medium | Phase 0 is timeboxed. Learning happens *through* shipping, not beside it. |

**Retired:** "custom scoring breaks the projections pipeline" — scoring was verified as standard
Half-PPR on 2026-07-31. Removed the scoring engine from Phase 2 (~1 day recovered).

## Open questions

- Your draft slot (Sleeper's `draft_order` is not yet populated) — BLK-3

**Closed 2026-07-31:** the 1-hour `pick_timer` does mean a slow draft over days, so Phase 3 is
deliberative rather than glanceable and notifications are not built (BLK-7).

**Sharpened 2026-07-31:** the FantasyPros web export does supply superflex rankings — the
Superflex ("OP") file is in `data/fantasypros/` and is verifiably correct (QBs at overall 1–6).
But **the export variant matters more than first assumed**, in two ways the earlier note missed:

- The cheat-sheet variant carries **no `ADP` and no `Std Dev` column** in either 1QB or superflex
  form — only a rank delta. Survival probability still needs the variant with
  `Best / Worst / Avg / Std Dev / ADP`. **BLK-1 stays open.**
- The superflex export **drops DST and K entirely**. Initially read as a regression; it is not.
  Defenses are streamed and there is no K slot, so QB/RB/WR/TE is exactly the ranked universe and
  BLK-2 closed by decision the same day.

Detail in [open-issues.md](open-issues.md) (BLK-1, BLK-2) and
[reference_fantasypros_exports.md](reference_fantasypros_exports.md). Re-pull within a few days
of 2026-08-28, since ADP moves through August.
