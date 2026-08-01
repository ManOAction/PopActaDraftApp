# Feature — Pick Advisor

> **Status: DESIGN. Not implemented.** Targeted at Phase 2 (`docs/roadmap.md`). Nothing described
> here exists in `api/` yet. Treat this as the specification to build against, not as a
> description of working code.

The core of the application. Everything else — import, board, Sleeper sync — exists to feed this.

---

## The question it answers

Not *"who is the best player left?"* That's a ranking, and you can get one for free from anybody.

The actual question is:

> **How much do I lose by not taking this player right now?**

That reframing is the whole feature. A player who is clearly the best available but has a 95%
chance of still being there when you pick again costs you almost nothing to pass on. A slightly
worse player who will certainly be gone might be the correct pick. Ranking cannot express this;
only a model that knows *when you pick again* can.

## Projections vs. rankings — they are not competitors

This is the question that motivated the design, so it's worth stating plainly.

| Source | Answers | Role here |
| --- | --- | --- |
| **Projections** (raw stats × league scoring) | "How many points will he score?" | **Value.** Sorts the board. |
| **ADP / ECR** (consensus rankings) | "When will he be taken?" | **Cost and timing.** Never sorts the board. |

Ranking on ECR outsources your draft to consensus — no edge, and no reason to build this. Ranking
on projections alone ignores availability and burns early picks on players who would have lasted.

**The edge is the interaction between them.** Value tells you who's worth having; ADP tells you
what it costs to wait.

One further use for ECR: **disagreement detection**. When our projected value ranks a player far
from consensus, that gap is either a genuine edge or a bug in our pipeline. Surfacing it is
cheap and catches both.

---

## The model

### 1. Points

For each player, projected points are **recomputed from raw stat projections** using the
league's Sleeper `scoring_settings` — never read from the CSV's `FPTS` column.

```
F(p) = score(stats(p), league_scoring)
```

Verified equivalent to FantasyPros' Half PPR default today (max deviation 0.62 pts across 518
players), but recomputation makes a mid-August scoring change a non-event. See
`docs/reference_fantasypros_exports.md`.

### 2. Roles, not positions

A player doesn't have *a* slot, he has a **set of slots he's eligible for**. In this league:

```
QB          → {QB, SUPER_FLEX}
RB, WR, TE  → {own position, FLEX, SUPER_FLEX}
DEF         → {DEF}
```

This is why LEG-1 mattered: fixed per-position integer columns cannot represent a slot that
accepts multiple positions, so superflex had to be faked.

**Superflex consequence.** League-wide QB demand is not 10. It's 10 dedicated QB slots plus most
of the 10 `SUPER_FLEX` slots — call it 18–20 of roughly 32 startable NFL QBs. That scarcity is
the single biggest driver of value in this format, and it falls out of the model automatically
once slots are eligibility sets.

### 3. Survival probability

Given a player's ADP mean `μ` and standard deviation `σ` (both from the rankings export), the
probability he's still on the board at pick `n`:

```
S(p, n) = P(ADP(p) > n) ≈ 1 − Φ((n − μ) / σ)
```

**`σ` is the important field, not `μ`.** ADP 40 ± 3 is genuinely gone by pick 55. ADP 40 ± 18 is
a coin flip. Same average, completely different decision. The 2025 app imported neither (LEG-6).

The normal approximation is a deliberate simplification — real ADP distributions are right-skewed
and truncated at 1. It's good enough to rank with, and worth revisiting only if it visibly
misbehaves in rehearsal.

### 4. Value Over Next Available

You're on the clock at pick `n_now`; your next pick is `n_next`. For a player `p` filling role
`r`:

```
VONA(p) = F(p) − E[ max { F(q) : q fills r, q available at n_next } ]      # WRONG — see below
```

> ### ⚠ Corrected 2026-07-31 — this formula ranks backwards
>
> The baseline must be **added**, not subtracted. As written, the formula recommends the player
> you should *not* take.
>
> Because the expectation excludes `p`, the baseline is a function of `p`: removing a
> likely-to-survive player leaves a weak fallback, and removing a certain-to-be-gone player
> leaves a strong one. Subtracting it therefore penalises exactly the player you must take now.
>
> Three players at the same role, `(points, survival to your next pick)`:
> `A = (250, 0.05)`, `B = (262, 0.80)`, `C = (210, 0.90)`.
>
> | | baseline `E[max others]` | `F − baseline` (this doc) | `F + baseline` (correct) |
> | --- | --- | --- | --- |
> | A | 247.40 | 2.60 | **497.40** |
> | B | 192.05 | **69.95** | 454.05 |
>
> Take A and you score 250 now plus a 247.4 fallback = 497.4. Take B and you score 262 now plus
> a 192.1 fallback = 454.1. **A is correct**, and the formula above picks B. Note the two
> expressions share both terms and differ only in the sign, so they rank oppositely whenever the
> baseline varies more than the projection does — which is most of the draft.
>
> The worked example below reaches the *right* answer only because it hand-assigns each player a
> different baseline (210 vs 258) instead of computing both from one shared candidate pool. That
> assumption encodes the conclusion; it is not derived.
>
> **The corrected form** — expected starting-lineup points across your next two picks:
>
> ```
> Plan(p)            = u(p | roster) + E[ max { u(q | roster ∪ {p}) · survives(q) } ]
> cost_of_passing(p) = max_p' Plan(p') − Plan(p)      # the number to display
> ```
>
> where `u(p | roster)` is `p`'s marginal contribution to your starting lineup rather than raw
> points — which is also what makes values comparable across positions in superflex. Full
> derivation, the replacement-level definition, and the superflex demand calculation are in
> [`plan_phase2_decision_engine.md`](plan_phase2_decision_engine.md).
>
> Keep this section as written, with the correction attached. The error is instructive: it is the
> same shape as LEG-5 — a plausible formula, computing cleanly, answering the wrong question.

Then:

```
priority(p) = Plan(p), restricted to roles you still need to fill
```

**This is the number the board sorts on.**

### Worked intuition

Two players, you pick again in 14 picks:

- **A**: 250 projected pts, ADP 20 ± 4. Best alternative at his role at your next pick: 210.
  → gone for certain, VONA ≈ **40**
- **B**: 262 projected pts, ADP 55 ± 20. Best alternative at his role: 258.
  → likely survives, and the drop-off behind him is shallow, VONA ≈ **4**

B is the better player. **A is the correct pick.** No ranking, however good, tells you that.

---

## Supporting signals

Secondary, shown alongside — not folded into the sort:

- **Tier breaks.** Gap-based clustering on projected points. Answers "is there a cliff right
  after this group?" The rankings export ships FantasyPros' own `Tier` column, which is a useful
  cross-check on ours.
- **Positional runs.** When N of the last M picks were one position, remaining players at that
  position become less likely to survive than static ADP implies. A first version can simply
  *flag* the run rather than adjust `σ`.
- **Roster need.** Roles already filled are excluded from `priority`; roles about to be scarce
  are weighted up.
- **Bye week collisions.** Low priority, easy to compute, occasionally decisive between close
  players.

## Inputs and outputs

**Inputs:** projections (stat-level), rankings (ADP, σ, tier, bye), league config from Sleeper
(roster positions, scoring), current draft state (picks made), your draft slot.

**Output:** an ordered list of candidates with `priority`, plus the components that produced it —
`F(p)`, `S(p, n_next)`, the replacement value, and which role it assumes he fills.

**Showing the components is a requirement, not a nicety.** This is a slow draft; you have an hour
per pick and you will want to know *why*. A number you can't interrogate is a number you won't
trust on draft night.

## Edge cases that must be handled explicitly

| Case | Required behaviour |
| --- | --- |
| Player has no ADP (deep sleepers) | Cannot compute survival. Treat as "certain to survive", **flag it**, never silently assume `σ=0`. |
| Final pick of the draft | No `n_next`. VONA degenerates to value over replacement level. |
| All roles filled | Advisor should fall back to best-available-by-value, clearly labelled as such. |
| Sleeper sync and manual entry disagree | **Undecided — see OPEN-4.** Must be settled before Phase 3. |
| A pick arrives for a player not in our data | Fail loudly. Never silently skip — that desynchronises the board (OPEN-1). |

## Implementation notes

- **Pure functions, no database access.** Takes state, returns recommendations. This is the most
  heavily-tested code in the project and the reason Phase 1 builds the domain core separately.
- Lives in `api/`, exposed as a single read endpoint returning candidates plus components.
- Deterministic given identical inputs — a fixed draft state must always produce the same output,
  so recommendations can be regression-tested against recorded scenarios.
- Recompute on every pick. At ~500 players and 10 teams this is trivially fast; don't cache.
