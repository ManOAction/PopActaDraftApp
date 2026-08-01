# Plan — Phase 2: decision engine

**Status: in flight.** Written 2026-08-01. Convert to `report_` when Phase 2 ships.

The layer that answers the question the whole app exists for: *given who's gone, who's left, what
my roster needs, and when I pick again — who should I take?*

Backed by four verified research passes (survival model, tier detection, name matching, VORP
baseline). **Every contract below is locked.** An agent that believes one is wrong should say so
and stop, not quietly choose differently.

Phase 1 contracts remain in force — see [`plan_phase1_domain_core.md`](plan_phase1_domain_core.md).
Style and area rules are in [`../api/CLAUDE.md`](../api/CLAUDE.md). This document repeats neither.

---

## What the research settled

Two passes found errors in existing project documents. Both are corrected in place with dated
notes, and both are worth knowing before reading further:

- **`FeatureDescription_PickAdvisor.md` §4 ranked backwards.** It defined the board's sort key as
  `F(p) − baseline`; it must be `+`. The two expressions share both terms and differ only in
  sign, so they rank oppositely whenever the baseline varies more than the projection does —
  which is most of the draft. Verified numerically; corrected in that document.
- **`BYE` is not complete** in the rankings export — it is `'-'` on 125 rows from `RK 200`. Every
  affected row sits outside the draftable window, so the conclusion it supported still holds.

---

## Locked decisions

### 1. The value axis is a slot-marginal, not raw points

Raw projected points are **not comparable across positions** — half-PPR QBs simply score more, so
a whole-board expectation over raw points returns a QB at every pick. Value is a player's marginal
contribution to *your starting lineup*:

```
W(R)      = max over assignments of R into ranked_starter_slots of
              Σ_slots max( F(assigned), floor(slot) )      # unfilled slot contributes its floor
floor(s)  = max over p in s.eligible of r_p                # r_p = replacement level, decision 2
u(p | R)  = W(R ∪ {p}) − W(R)
```

Three properties make this the right axis:

- **It is unique even when the underlying matching is not.** `W` is a maximum, so its *value* is
  canonical, and `u` is a difference of two canonical maxima. **This retires the Phase 1 "`unfilled`
  is not canonical" limitation** — the scoring path never reads `unfilled`. Display may still show
  unfilled slots; it must not drive a number.
- **It prices superflex with no free parameter.** `floor(SUPER_FLEX) = max(r_QB, r_RB, r_WR, r_TE)
  = r_QB`, while `floor(RB) = r_RB`. A QB nets `F − r_QB` in either slot; an RB nets `F − r_RB` in
  RB/FLEX but only `F − r_QB` in SUPER_FLEX — so an RB never occupies SUPER_FLEX until RB and FLEX
  are full. The premium is *derived*, not asserted.
- **Roster need lives inside the value.** A third QB behind two better ones scores `u ≈ 0`
  automatically. No separate "need multiplier" — that would double-count.

With an empty roster `u(p|R) = F(p) − r_pos(p)`, i.e. classic VORP with the correct baseline.

### 2. Replacement level uses **draft demand**, not starter demand

**Decided 2026-08-01 by Jacob.** This is the largest modelling choice in Phase 2 — a ~77-point
swing applied to every QB.

```
r_pos = F of the (D_pos + 1)-th best player at pos,
        where D_pos = players at pos inside the top (teams × rounds) of superflex consensus order
```

Measured on the real projections: `r_QB = QB30 = 192.8`, versus starter demand's `QB21 = 269.5`.

| basis | Josh Allen | QBs in our top 40 |
| --- | --- | --- |
| starter demand (`QB21`) | rank 8 | 5 |
| **draft demand (`QB30`)** | **rank 5** | **13** |

**Why draft demand.** 29 QBs come off the board in 160 picks, not 20. If you punt QB you do not
get QB21 (a projected 493-attempt starter) — you get QB30. The baseline must reflect who you would
actually be forced to start. It also reproduces the consensus shape, in which QBs occupy overall
1–6 and 13 of the top 24. Starter demand produces a board that says "essentially never draft a QB"
in a superflex league, which is an extraordinary claim to make against a projection set whose own
publisher ranks QBs 1–6.

**Cost of being wrong:** if draft demand is too aggressive we over-rate every QB by up to 77 points
of baseline and could reach for QB4 over RB1.

**Required mitigation:** compute **both** bases and expose starter-demand VORP as a sensitivity
band in the UI. A large our-rank-vs-consensus gap is the tripwire. See *Configurable in a later
cycle* below — this is the first knob.

**Not an artefact of a bloated projection set:** 28 QBs are projected ≥450 pass attempts, and the
cliff falls at QB29→QB30 (223 → 193), exactly where draft demand lands.

> **Confirmed against real market ADP, 2026-08-01.** The superflex ADP export
> (`FantasyPros_2026_Superflex_ADP_Rankings.csv`) puts **32 QBs inside the top 160** — measured
> from actual draft data rather than estimated from consensus rank, which had given 29. Draft
> demand is therefore *validated and slightly strengthened*: `r_QB` becomes `QB33`, a marginally
> lower baseline than the `QB30` this decision was made on. **This closes open question 5 below.**
>
> One nuance worth carrying into the UI: the market takes **8** QBs in the top 24, while expert
> superflex consensus ranks **13** there. The market is *less* QB-eager early than the experts.
> That gap is the same phenomenon as the +7.5 median QB `ECR VS ADP` delta measured earlier, and
> it is precisely what the starter-demand sensitivity band exists to surface.

### 3. `Plan(p)` is the ranking axis, and the baseline is **added**

```
B(p)    = E[ max over q ∈ A\{p} of  u(q | R ∪ {p}) · survives(q) ]
Plan(p) = u(p | R) + B(p)
cost_of_passing(p) = max_p' Plan(p') − Plan(p)      # the number displayed
```

`Plan(p)` is expected starting-lineup points across your next two picks. `B(p)` excludes `p` — he
is on your roster in that branch — and is computed against `R ∪ {p}`, which is what makes taking a
player degrade his own fallback value.

**This is the corrected form of the `VONA` formula.** See the correction in
[`FeatureDescription_PickAdvisor.md`](FeatureDescription_PickAdvisor.md) for the counterexample and
the arithmetic.

### 4. The `E[max]` estimator is exact — do not approximate

The baseline is an expectation of a **maximum**, which is neither the max of the expectations nor
the mean of the survivors. Exact under independence, one `O(n)` pass after sorting:

```python
def expected_max(candidates):          # [(value, survival_prob)], any order
    acc, none_yet = 0.0, 1.0
    for value, s in sorted(candidates, key=lambda c: -c[0]):
        acc += value * s * none_yet    # value is the max iff it survives and all better ones did not
        none_yet *= (1.0 - s)
    return acc                         # assert none_yet ≈ 0 on a full pool
```

Measured alternatives, on the real board — all rejected:

| form | error vs exact |
| --- | --- |
| mean of survivors | 150+ points (dominated by the deep bench) |
| value at rank `m+k+1` (**the shape LEG-5 used**) | 47–81 points, always pessimistic |
| first / cumulative `s > 0.5` point estimates | ~2 points, but discards the variance that is the entire reason `σ` matters — for no saving, since the exact form is the same loop |

**Inner-pool truncation is provably safe:** at most `k` players can leave, so the best survivor is
among the top `k+1` by value. Use `N = k + 1 + 10` and assert the residual `none_yet`.

### 5. Independence is assumed, and the assertion it buys is mandatory

The estimator treats survival events as independent. They are not — if one QB lasts, another is
likelier taken — and the model permits the impossible event that every remaining player is taken
in `k` picks. Measured against a Plackett–Luce simulation with exactly `k` departures, the bias is
**≤1.2 points through most of the draft**, uniformly signed (independence understates the baseline,
therefore overstates urgency), and largest at pick 1 — where the decision matters least.

**Accept it, and take the free calibration check it implies:**

> Assert `|Σ_{q ∈ A}(1 − s_q) − k| ≤ 0.15·k` and **fail loudly**. The expected number of players
> taken in the window must equal `k` by construction. This is the cheapest available detector of a
> miscalibrated `σ` or a stale export.

### 6. Horizon: 2-ply, extending to 3-ply at the turn

Default is your next turn only. **At the turn `k == 0`**, and the 2-ply model becomes exactly
indifferent to the order of your back-to-back picks — correct, but useless. So when `k == 0`,
extend one ply using `picks_until_nth_turn(..., n=2)`.

Do not go further. Beyond 3-ply the terms are near-identical across candidates and the model stops
being narratable.

### 7. The endgame needs no special case

At your final pick `picks_until_next_turn` returns `None`, so `B(p) := 0` and
`Plan(p) = u(p | R)` — value over replacement, exactly as the PickAdvisor edge-case table requires.
`r_pos` degenerates consistently too. **"An empty window has expectation zero" is the whole rule.**

### 8. Survival probability — conditional normal, floored

Settled by research and independently verified:

```python
S(x)      = 0.5 * erfc((x - adp) / (sd * sqrt(2)))        # P(lasts past pick x)
p_survive = max( S(m + k) / S(m),  exp(-k / (sd * sqrt(3)/pi)) )
```

- **Use `0.5·erfc(z/√2)`, never `1 − Φ(z)`.** Verified: `1 − cdf` returns *exactly* `0.0` for
  z ≥ 10, making the ratio `0/0 → nan`. That fires in rounds 13–16, when most remaining players are
  deep in the tail. `erfc` stays accurate to z ≈ 37. It is **stdlib `math`** — do not add scipy.
- **Conditioning on `S(m)` is the point.** A player past his ADP but still on the board scores
  ~0.1% unconditionally and ~2.8% conditionally. The unconditional number assigns near-zero
  probability to a state you are looking at.
- The `exp(-k/s)` floor is a constant-hazard tail bound. The normal's hazard grows without bound,
  so a deep faller would otherwise score absurdly confident.
- `k == 0` yields exactly `1.0`. No special case; assert it.
- **Call `picks_until_next_turn` with `picks_made + 1`** — the baseline asks what survives between
  *your* pick and the next one, so the pick you are about to make is already counted.

### 9. Tiers: per position, absolute gap on points

Settled empirically against FantasyPros' own `TIERS` labels (768 rows):

- **Fixed absolute gap threshold, `t = 6.0` season half-PPR points, `min_tier_size = 2`.**
- **Per position, never pooled.** Pooling cuts the median gap ~4× — four interleaved positions fill
  in exactly the holes you are detecting.
- **Cluster on points, never rank.** `RK` is a dense 1..768 sequence, so every gap is exactly 1.
  There is no cliff on an axis with no gaps.
- **Freeze the threshold as a constant.** Recomputing a data-derived threshold each pick
  re-introduces global coupling and destroys stability.
- Ties (`gap == threshold`) break the tier — `>=`, stated explicitly.

**Why the simplest algorithm wins:** it scores slightly *worse* than Jenks on agreement (ARI 0.336
vs 0.392, ceiling 0.446) and decisively better on stability. Under single-player removal the **gap
rule** produces **zero** non-local boundary changes — verified independently — while Jenks moves
boundaries up to 37 positions away and largest-N-gaps up to 99. Mid-draft, one pick shifting a tier
line 65 positions away is what makes a tier display worse than none. Recompute every pick; it is
safe precisely because the estimator is local.

> **Corrected 2026-08-01 — the zero-change guarantee belongs to the gap rule, not to
> `min_tier_size`.** This section originally claimed zero non-local changes outright. That holds
> for `min_tier_size = 1`; the merge pass is a downward-accumulating scan and does perturb distant
> boundaries. Measured on the real board at `t = 6.0, min_tier_size = 2`:
>
> | position | removals perturbing a distant boundary | worst distance |
> | --- | --- | --- |
> | QB (82) | 8 | 7 positions |
> | RB (128) | 6 | 3 |
> | WR (189) | 5 | 5 |
> | TE (119) | 3 | 3 |
>
> Independently reproduced on synthetic boards: 17 non-local changes at `t = 6.0, n = 40`, worst
> distance 3. **Bounded and near** — against 37 for Jenks and 99 for largest-N — so the design
> choice stands and `min_tier_size = 2` is kept. But the claim must be scoped, not asserted, and
> the degenerate case is an all-singleton board, where a removal flips parity for everything below
> it. Pinned by a test that asserts the merge pass is *not* zero-change, so this cannot be quietly
> re-claimed later.

### 10. Lineup assignment uses a bitmask DP, not greedy

`W(R)` has **slot-dependent floors**, which breaks the matroid structure that makes greedy optimal
for `assign_starters`. Bitmask DP over the 9 ranked slots: `O(n · 2^S · S)` ≈ 74k operations,
exact, ~20 lines.

**The measurement that matters, and the reason it is not "greedy is broken":**

| slot order | greedy suboptimal | worst shortfall |
| --- | --- | --- |
| production (Sleeper's order) | **0 / 20000** | 0 |
| randomised | **12707 / 20000** | 397 points |

Greedy is exact *for this league's slot order* and catastrophic under any other. Sleeper lists
position-specific slots first and `SUPER_FLEX` last, which masks the bug. **That ordering is
received data, not a guarantee** — so correctness must not depend on it. This is the **third** time
this project has found production slot order hiding a greedy bug; the other two are in
`plan_phase1_domain_core.md`.

Greedy over raw points **is** exact for league-wide demand (uniform floors — a transversal
matroid), verified 0/20000. Reuse `roster._augment` there.

### 11. Each signal enters exactly once

The composition question dissolves — that is the design's main claim. Double-counting is how LEG-5
happened.

| signal | enters at | must not also |
| --- | --- | --- |
| projected points | `F(p)` | — |
| positional scarcity | `r_pos` → slot floors → `u` | be re-applied as a "scarcity bonus" |
| roster need | slot occupancy inside `W(R)` | be a separate "need multiplier" |
| survival | the weights inside `B(p)` | multiply the final score — it already sets the baseline |
| tier | **label only** | enter the score |
| positional run | **label only** | enter the score (v1) |
| bye collisions | label only | — |

### 12. Bench value is not modelled (β = 0)

**Cost, stated plainly:** rounds 12–16 under-rate handcuffs and depth, because once every starter
slot holds an above-replacement player, `u → 0` for nearly everyone. Handle it as the PickAdvisor
doc already specifies — detect "starters covered", fall back to best-available by `u` on an empty
roster, and **say so on screen**.

---

## What is buildable now vs blocked on BLK-1

BLK-1 (the rankings export carrying `ADP` and `Std Dev`) is the critical path for *part* of this
phase, not all of it.

| Buildable today | Blocked on BLK-1 |
| --- | --- |
| Projection import + scoring recompute | `survival()` |
| Player pool + Sleeper ID matching | `B(p)` (the next-turn baseline) |
| Draft demand, starter demand, `r_pos` | `Plan(p)`, `cost_of_passing` |
| `W(R)` and `u(p | R)` (the DP) | The `Σ(1−s) ≈ k` calibration assertion |
| Tier detection | |

**Interim degraded mode:** with no ADP, rank on `u(p | R)` alone — classic VORP with the correct
replacement level. It is a genuinely useful board, and it exercises everything except the survival
path. Ship it, label it, and swap in `Plan` when the export lands.

---

## Modules and ownership

New code under `api/src/popacta/`. Domain modules stay pure — no I/O, no DB.

| Module | Role | Owner |
| --- | --- | --- |
| `domain/players.py` | `Player`, `AdpEstimate`, `PlayerPool`, `available()` | Wave 0 |
| `domain/snake.py` | **add** `picks_until_nth_turn(...)` | Wave 0 |
| `domain/scoring.py` | Recompute points from raw stats + Sleeper `scoring_settings` | A |
| `ingest/fantasypros.py` | CSV parsing, keyed by `(file, column index)` | A |
| `ingest/matching.py` | FantasyPros → Sleeper ID resolution + override list | B |
| `domain/replacement.py` | Draft demand, starter demand, `r_pos` | C |
| `domain/lineup.py` | `W(R)`, `u(p|R)` — the bitmask DP | D |
| `domain/tiers.py` | Tier detection | E |
| `domain/survival.py` | The conditional normal model | F |
| `domain/advisor.py` | `B(p)`, `Plan(p)`, `cost_of_passing` — the assembly | Wave 2, solo |

Wave 0 is single-authored for the same reason it was in Phase 1: `Player` and `AdpEstimate` are
shared vocabulary, and three agents inventing their own would not compose.

`advisor.py` is the integration point and stays solo — it is where double-counting would creep in.

## Acceptance criteria

**Everywhere:** bad input raises; no silent defaults; every exception names the offending value.

- **`scoring.py` / `ingest`** — recomputed `FPTS` matches the CSV within rounding across all 518
  players. **That test does not cover the column-order trap** — the swap is points-invisible in
  this league (`rush_yd == rec_yd`, `rush_td == rec_td`), verified 2026-08-01, so a **stat-line**
  comparison against the per-position files is the test that actually catches it. Column access
  keyed by index. `BYE == '-'` raises only for a player inside the draftable window.
- **`matching.py`** — ≥99% of rows resolve; the unresolved set is **exactly** the committed
  override list; **any** ambiguity after the full tie-break ladder raises; two FantasyPros rows
  resolving to one Sleeper ID raises. `DEF` picks resolve **by ID before any name path**, because
  all 32 Sleeper DEF rows have `full_name: null` and would otherwise raise `AttributeError`
  mid-draft.
- **`replacement.py`** — `D_QB == 32` on the pinned data (**corrected 2026-08-01**; this line said
  29, the consensus-derived estimate, while the dated note under decision 2 already said 32 from
  real ADP); both bases computed; `D_pos` from the
  league-wide allocation never exceeds draft demand.
- **`lineup.py`** — matches a brute-force oracle over randomised rosters, **including randomised
  slot orders**. That reordered-slot test is the only thing standing between us and a 397-point
  error, exactly as in `test_roster.py`. Two QBs occupy `QB` and `SUPER_FLEX`; an RB never takes
  `SUPER_FLEX` while RB or FLEX is free.
- **`tiers.py`** — **the gap rule** (`min_tier_size = 1`) produces zero non-local boundary changes
  under single-player removal, at every threshold. The `min_tier_size` merge pass does not, and is
  instead bounded: assert it stays local to within a few positions, and pin that it is non-zero so
  the guarantee cannot be over-claimed. Points and VORP produce identical per-position partitions
  (they differ by a constant) — assert it, so nobody "fixes" it later.
- **`survival.py`** — `k == 0` returns exactly `1.0`; `erfc` path survives z ≥ 30 without `nan`;
  a faller past ADP returns a small positive number, not zero; `sd == 0` or missing raises at
  import; a drafted player raises.
- **`advisor.py`** — `Plan` ranks the verified counterexample correctly (A over B); `E[max]`
  matches Monte Carlo; the `Σ(1−s) ≈ k` assertion fires on deliberately miscalibrated `σ`.

## Missing Phase 1 primitives — build these in wave 0

1. **`snake.picks_until_nth_turn(seat, picks_made, teams, rounds, n, reversal_round=0)`** — needed
   independently by two research passes: the `k == 0` back-to-back case, and the horizon
   replacement level. Strict generalization; `n = 1` must reproduce `picks_until_next_turn` exactly.
2. **A player pool type.** `DraftState` holds IDs only. Phase 2 needs `Mapping[str, Player]` with
   `position`, `points`, and `AdpEstimate | None`. The ID space must be the one Sleeper sends.
   `drafted_ids` **will** contain DEF/K picks absent from the ranked pool — that is expected and
   must not raise.
3. **`available(pool, drafted_ids)`** — trivial, but it is the one place a desynchronised board
   becomes visible, so it must assert every drafted ID is either known or explicitly DEF/K.

**Phase 1 limitations, resolved:** `unfilled` non-canonicality is retired by decision 1. The
`bench`/DEF conflation is fixed by filtering `roster_for_seat` through `RANKED_POSITIONS` before it
reaches `W` — a one-line precondition that must be **asserted, not assumed**.

---

## Configurable in a later cycle

**Deferred, not forgotten.** These are the modelling choices where reasonable people differ, and
several get ground-truthed for the first time at the mock-draft rehearsal (OPEN-2). For this cycle
each is a **frozen constant with a named home**, so exposing it later is a settings surface rather
than a refactor.

| Knob | Locked value | What changing it does |
| --- | --- | --- |
| **Replacement basis** | draft demand | Starter demand shifts every QB by ~77 baseline points. The decided-against option is already computed for the sensitivity band. |
| Draft-demand horizon | `teams × rounds` (160) | Shrinking it toward the starter count interpolates between the two bases. |
| Tier threshold `t` | 6.0 points | Higher → fewer, coarser tiers. Sweep is flat 5–7, falls off sharply outside. |
| `min_tier_size` | 2 | Collapses runs of singleton tiers at the top of a board. |
| Survival distribution | normal | Swap `S(x)` for logistic if the export's `Best`/`Worst` reveal fat tails. Single named function, one-line change. |
| Lookahead depth | 2-ply (3 at the turn) | Deeper stops being narratable. |
| Bench weight `β` | 0 | Non-zero would price handcuffs and depth in rounds 12–16. |
| Positional-run handling | label only | Could become an adjustment to `σ` rather than to the score. |

**Design constraint for all of them:** a knob may change *inputs* to the model, never add a term to
the score. Decision 11 (each signal enters exactly once) is not configurable — that is the
invariant that keeps the number explainable, and explainability is a draft-day requirement.

## Open questions — status after the ADP export landed (2026-08-01)

**Closed:**

- ~~5. Does the market really take 29 QBs?~~ **It takes 32.** Measured on real superflex ADP.
  Draft demand confirmed; `r_QB = QB33`. Still worth re-deriving from the mock-draft rehearsal
  (OPEN-2), which remains the only true ground-truth before draft day.
- ~~3a. Is ADP on the same scale as `picks_made`?~~ **Yes.** Top-160 `AVG` runs 1.5 … 164.0, so no
  rescale is needed. An offence-only board would have compressed well below 160.
- ~~4. Players with no ADP.~~ **Coverage is complete** across the draftable window — `AVG` is
  present on all 278 rows. Keep the assertion anyway; it costs nothing and guards the re-pull.

**Still open — all four now blocked specifically on `Std Dev`, not on ADP:**

1. **Is `sd` monotone in `ADP`?** The cross-source spread says yes in shape — median
   `|Sleeper − FFPC|` is 4.0 at ADP ≤ 40 and 15.0 at ADP > 100 — but that measures platform
   disagreement, not draft-to-draft variance, and cannot set a magnitude.
2. **Does `Σ(1−s) ≈ k` hold?** Unanswerable without real `σ`. This remains the mandatory
   calibration assertion.
3. **Does the horizon `r_pos` reproduce the count-based one?** Needs survival, therefore `σ`.
   Prefer the count-based form if they disagree — it is directly observable, and it is now
   directly *measured* rather than inferred.
6. **What supplies `Std Dev`?** New. The ADP export does not carry it and neither does the
   cheat-sheet rankings export. The remaining candidate is the FantasyPros **ECR rankings** export
   variant with `Best / Worst / Avg / Std Dev` columns. Until one arrives, the honest options are
   (a) pull that variant, or (b) model `σ = f(ADP)` — which means inventing a coefficient, exactly
   the move that produced LEG-1 and LEG-5. **Prefer (a).**
