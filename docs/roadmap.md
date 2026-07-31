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
3. **DEF is a required starter; there is no K slot.** Last year's data had neither DST nor K —
   this is a gap to close, not a port.
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

**Remaining:**

- [ ] `.claude/rules/` for Python and TypeScript style
- [ ] Custom sub-agents in `.claude/agents/`: design reviewer (browser + screenshot), draft-logic
      verifier, test writer
- [ ] `uv` + `ruff` + `pytest` + GitHub Actions green on push; record commands in root `CLAUDE.md`
- [ ] Browser automation wired up for the design feedback loop
- [ ] Rewrite `README.md` — it still describes the 2025 app, its stack, and a Let's Encrypt setup
      that never existed
- [ ] **Commit.** Nothing above is in git yet.

### Phase 1 — Domain core *(~3 days)*

Pure functions, no DB coupling, heavily tested. The part the old app never modeled.

- Draft seat; snake order; pick numbers **derived from position**, not counted with `max()+1`
- Safe undo — the old global counter left permanent holes in the sequence
- Roster slots as position-eligibility sets (superflex-capable)
- Your roster and its unfilled needs
- **Picks until your next turn** — the keystone the whole decision engine hangs off

### Phase 2 — Decision engine *(~4 days)*

Also pure and independently verifiable, which makes it the right place to practise adversarial
sub-agent review.

- VORP rebuilt against the next-pick-window baseline, with **superflex-aware** positional demand
  (QB demand is 10 QB slots + contested share of 10 SUPER_FLEX slots, not a flat count)
- **Survival probability**: given ADP and its variance, will this player last until my next turn?
- Tier detection (gap-based clustering) — see the cliff before you fall off it
- Positional run detection

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
- **DST projections** — required starter, absent from last year's data entirely
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

- **`pick_timer` is 3600s (1 hour).** Is this a slow draft over days rather than a live room? If
  so, Phase 3 inverts: tap-speed stops mattering, on-the-clock notification becomes the top
  feature, and the analysis can be deliberative rather than glanceable.
- Your draft slot (Sleeper's `draft_order` is not yet populated)

**Closed 2026-07-31:** superflex ADP and DST projections both resolve via the FantasyPros web
export — set scoring to Half PPR and rankings to superflex/"OP". Pull the export within a few
days of 2026-08-28, since ADP moves through August.
