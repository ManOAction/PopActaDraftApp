# Plan — Phase 1: domain core

**Status: in flight.** Written 2026-07-31. Delete or convert to `report_` when Phase 1 ships.

The pure-functions layer the 2025 app never had: draft seat, snake order, safe undo, roster slots
as position-eligibility sets, and picks-until-your-next-turn. No database, no FastAPI, no I/O.

This document exists so parallel sub-agents share one vocabulary and one set of decisions. **Every
contract below is locked.** If an agent believes one is wrong, it should say so and stop — not
quietly pick a different answer.

Area rules and Python style are in [`../api/CLAUDE.md`](../api/CLAUDE.md), which auto-loads when
working in `api/`. This document does not repeat them.

---

## Pinned league facts

Fetched from Sleeper on 2026-07-31 and committed as fixtures:

- `api/tests/fixtures/sleeper_league.json`
- `api/tests/fixtures/sleeper_draft.json`

```
teams            10
rounds           16          <- from the DRAFT object
type             snake
reversal_round   0           <- no third-round reversal
roster_positions QB RB RB WR WR TE FLEX FLEX SUPER_FLEX DEF + BN×6
reserve_slots    1           (IR — not part of roster_positions)
draft_order      null        (BLK-3; seat is a parameter, never read from here)
```

> **Trap — read `rounds` from the draft, not the league.**
> `league.settings.draft_rounds` is **3**. `draft.settings.rounds` is **16**. The league value is
> stale and unused. Reading it yields a silently truncated 3-round draft, and every downstream
> number would be wrong without anything crashing. `LeagueConfig.from_sleeper()` takes **both**
> payloads for exactly this reason.

Tests assert against the fixtures. Nothing in the domain layer hardcodes `10` or `16`.

## Scope

**In:** `positions`, `league`, `snake`, `draft`, `roster` — five modules under
`api/src/popacta/domain/`.

**Out, deliberately:** VORP, survival probability, tier detection, positional runs (Phase 2);
persistence and Alembic; FastAPI routes; any FantasyPros or Sleeper *network* call. Loading real
projections is Phase 4. An agent that starts writing VORP has left its scope.

---

## Locked contract decisions

### 1. Kickers and defenses are not ranked

The league has **no K slot**, and the strategy is to **stream defenses**. Neither position gets
projected, ranked, or recommended.

**But they must still parse.** Nine other teams will draft defenses, and Sleeper will send us
those picks during the draft. A domain model that does not know `DEF` exists would raise on
another team's pick and take down draft-night sync — turning a strategy preference into an outage.

So there are two sets, and the distinction is load-bearing:

| | Contents | Used for |
| --- | --- | --- |
| `Position` | QB RB WR TE **DEF K** | Parsing anything Sleeper sends |
| `RANKED_POSITIONS` | QB RB WR TE | Projections, VORP, recommendations, roster needs |

Consequences:

- The `DEF` starter slot is parsed into `LeagueConfig` and then **excluded from
  `ranked_starter_slots`**. It is never reported as an unfilled need, so the app never tells you
  to draft a defense.
- A `DEF` or `K` pick by any team is recorded normally and marks that player unavailable.
- `K` never appears in `roster_positions`, so no K slot can exist. `from_sleeper()` **asserts**
  this — if a K slot ever appears, that is a league change we must not silently absorb.
- The exclusion is an explicit `excluded_positions` field, not an omission. A future reader must
  be able to see it was a decision.

### 2. Indexing is 1-based, everywhere

Seats `1..teams`, rounds `1..rounds`, pick numbers `1..teams*rounds`. Sleeper's
`slot_to_roster_id` is already `'1'..'10'`; a 0-based internal convention guarantees an
off-by-one at every conversion boundary. Python list indices are of course still 0-based — the
conversion happens once, at the tuple boundary, and is commented where it does.

### 3. `picks_until_next_turn` counts *other teams' picks*

**The keystone. This is the definition Phase 2 consumes, so it gets stated once and tested hard.**

```
picks_until_next_turn(seat, picks_made) -> int | None
```

Given `picks_made` completed picks, returns **how many picks other teams will make before this
seat picks again**. Returns `0` when the next pick belongs to this seat. Returns `None` when the
seat has no picks left.

The rejected alternative was the pick-number delta. Seat 4 in a 10-team snake picks at 4, then 17.
The delta is **13**; the number of intervening picks is **12**. Survival probability asks "how
many players get taken before I choose again", so **12** is correct — the delta overstates it by
one and makes every survival estimate systematically pessimistic.

Formula, once `next_pick_for_seat` exists:

```python
next_mine - picks_made - 1
```

**The case that catches a wrong implementation:** at the turn, a seat picks back-to-back. Seat 10
picks at 10 and 11, so `picks_until_next_turn(10, 9) == 0` **and** `picks_until_next_turn(10, 10)
== 0`. An implementation returning `1` is wrong, and nothing downstream will reveal it — it will
just quietly shade every recommendation at the turn. Seat 1 is the mirror case: picks at 1 and 20,
so `picks_until_next_turn(1, 1) == 18`.

### 4. State is immutable

Frozen dataclasses with `slots=True`. Every operation returns a new value. This makes undo
trivial, makes tests pure, and removes a whole class of draft-night aliasing bug.

### 5. Pick numbers are *derived from position*, never stored

This is the direct fix for LEG-3. `DraftState` holds an ordered tuple of player IDs:

```python
player_ids: tuple[str, ...]     # index i is pick number i+1
```

Pick number is `index + 1`. Round and seat are computed from the pick number by `snake`. Nothing
counts with `max() + 1`, so **a hole in the sequence is unrepresentable** rather than merely
avoided.

### 6. Undo removes an *arbitrary* pick, not just the last

LEG-3 is about correcting a mis-recorded pick mid-draft, so `undo(pick_number)` accepts any
existing pick. Because numbering is derived, removing element *i* re-derives everything after it
automatically — later picks shift down one and their seats recompute. That is the intended
meaning: *this pick never happened*.

Undoing a nonexistent or out-of-range pick **raises**.

### 7. `DraftState` tracks all ten teams

Not just yours. Phase 2's VORP needs to know who is globally gone; your roster is *derived* from
your seat via `roster_for_seat(seat)`. Storing only your own picks would make the replacement
baseline uncomputable.

### 8. Roster needs are slots, not position counts

`unfilled` returns the **slot instances** left open, not a per-position tally. `SUPER_FLEX` has no
single position, so a `dict[Position, int]` cannot express the answer. Bench (`BN`) is never a
need, and `DEF` is excluded per decision 1.

### 9. Bad input raises, always

Per the project's central rule. Specifically: drafting an already-drafted player; recording a pick
when the draft is complete; undoing a pick that does not exist; a `roster_positions` entry the
slot map does not recognise; a seat outside `1..teams`. Every exception message names the
offending value.

---

## Modules and signatures

All under `api/src/popacta/domain/`. Signatures are **fixed** — an agent needing a different one
should stop and say so.

### `positions.py`

```python
class Position(StrEnum):        # every position Sleeper can send
    QB = "QB"; RB = "RB"; WR = "WR"; TE = "TE"; DEF = "DEF"; K = "K"

RANKED_POSITIONS: Final[frozenset[Position]]    # {QB, RB, WR, TE}
```

### `league.py`

```python
@dataclass(frozen=True, slots=True)
class SlotInstance:                 # one concrete starter slot
    id: str                         # "RB.1", "RB.2", "FLEX.1", "SUPER_FLEX.1"
    name: str                       # "RB", "FLEX", "SUPER_FLEX"
    eligible: frozenset[Position]

@dataclass(frozen=True, slots=True)
class LeagueConfig:
    teams: int
    rounds: int
    reversal_round: int
    starter_slots: tuple[SlotInstance, ...]     # includes DEF
    bench_count: int
    excluded_positions: frozenset[Position]     # {DEF, K} — decision 1

    @classmethod
    def from_sleeper(cls, league: Mapping[str, Any], draft: Mapping[str, Any]) -> Self: ...

    @property
    def ranked_starter_slots(self) -> tuple[SlotInstance, ...]: ...   # DEF removed
    @property
    def total_picks(self) -> int: ...                                 # teams * rounds
```

Slot eligibility map — the only place this is written down:

```
QB -> {QB}     RB -> {RB}     WR -> {WR}     TE -> {TE}     DEF -> {DEF}
FLEX       -> {RB, WR, TE}
SUPER_FLEX -> {QB, RB, WR, TE}
BN         -> bench, not a starter slot
```

### `snake.py`

```python
def pick_number(round_: int, seat: int, teams: int, reversal_round: int = 0) -> int: ...
def round_and_seat(pick: int, teams: int, reversal_round: int = 0) -> tuple[int, int]: ...
def seat_picks(seat: int, teams: int, rounds: int, reversal_round: int = 0) -> tuple[int, ...]: ...
def next_pick_for_seat(seat: int, picks_made: int, teams: int, rounds: int,
                       reversal_round: int = 0) -> int | None: ...
def picks_until_next_turn(seat: int, picks_made: int, teams: int, rounds: int,
                          reversal_round: int = 0) -> int | None: ...
```

`reversal_round` is `0` for this league (no reversal). Implement it anyway — it is a few lines,
and discovering it was non-zero *after* building on the assumption would be expensive.

### `draft.py`

```python
@dataclass(frozen=True, slots=True)
class Pick:                     # a derived view, never stored
    pick_number: int
    round: int
    seat: int
    player_id: str

@dataclass(frozen=True, slots=True)
class DraftState:
    config: LeagueConfig
    numbering: SnakeNumbering          # injected — see the note below
    player_ids: tuple[str, ...] = ()

    def record(self, player_id: str) -> Self: ...
    def undo(self, pick_number: int) -> Self: ...
    def picks(self) -> tuple[Pick, ...]: ...
    def roster_for_seat(self, seat: int) -> tuple[str, ...]: ...
    @property
    def drafted_ids(self) -> frozenset[str]: ...
    @property
    def picks_made(self) -> int: ...
    @property
    def next_pick_number(self) -> int | None: ...       # None when complete
    @property
    def seat_on_the_clock(self) -> int | None: ...
```

`DraftState` must not import `snake` at module scope for its numbering — it takes the numbering
functions via a small `Protocol` so it is unit-testable against a trivial linear stub. This is
what lets `draft.py` and `snake.py` be written concurrently.

In production the `snake` **module object itself** is passed as `numbering`; it satisfies the
Protocol structurally, since `numbering.round_and_seat(pick, teams, reversal_round)` resolves to
the module-level function. Verified working end to end. Note that a static type checker would
reject this — a module is not a nominal Protocol instance — so **if mypy is ever added, this is
the first thing that will complain**, and the fix is a thin adapter class rather than a change to
the design.

### `roster.py`

```python
@dataclass(frozen=True, slots=True)
class StarterAssignment:
    filled: Mapping[str, str]           # slot id -> player_id
    unfilled: tuple[SlotInstance, ...]
    bench: tuple[str, ...]              # rostered, no starter slot

def assign_starters(roster: Mapping[str, Position],
                    slots: Sequence[SlotInstance]) -> StarterAssignment: ...
```

> **This is a maximum bipartite matching problem, and greedy is wrong.**
>
> Roster `{RB1: RB, QB1: QB}`, open slots `{SUPER_FLEX, RB}`. Greedy visiting `RB1` first puts it
> into `SUPER_FLEX`; then `QB1` fits nothing and the app reports an unfilled slot plus an unplaced
> player. The correct assignment is `QB1 -> SUPER_FLEX`, `RB1 -> RB`, everything filled.
>
> **Iteration order is load-bearing** (corrected 2026-07-31 — the original wording here said
> "greedy in roster order" with the roster written `{QB1, RB1}`, which does *not* reproduce the
> failure: visiting `QB1` first, player-major greedy reaches the right answer by luck. A test
> written from that ordering passes against a broken implementation).
>
> Use augmenting paths (Hopcroft–Karp is overkill — the graph is ~16 players by ~9 slots).
> **This counterexample must appear as a test, pinned to the order that strands the QB.**

---

## Agent ownership

Disjoint files, so no worktrees and no merge conflicts. **Do not edit a file you do not own.**

| Agent | Owns | Depends on |
| --- | --- | --- |
| Wave 0 (lead) | `positions.py`, `league.py`, fixtures, all signatures | — |
| A | `snake.py`, `tests/domain/test_snake.py` | positions, league |
| B | `roster.py`, `tests/domain/test_roster.py` | positions, league |
| C | `draft.py`, `tests/domain/test_draft.py` | positions, league, snake *signature only* |
| Wave 2 verify | nothing — read-only | all |
| Wave 2 integration | `tests/domain/test_integration.py` | all |

## Acceptance criteria

Done means all of the following, per module. An agent that finishes early should deepen its tests,
not widen its scope.

**A — `snake.py`**
- Round 1 ascending, round 2 descending, and the flip holds on *every* even round through 16
- `pick_number` and `round_and_seat` are exact inverses for all 160 picks
- `seat_picks(1)` starts `(1, 20, 21, 40, ...)`; `seat_picks(10)` starts `(10, 11, 30, 31, ...)`
- `picks_until_next_turn(10, 9) == 0` and `(10, 10) == 0` — the back-to-back turn
- `picks_until_next_turn(1, 1) == 18`; `picks_until_next_turn(4, 4) == 12`
- Returns `None` after a seat's final pick
- Seat 0, seat 11 and pick 0 all raise `DraftRangeError`
- `reversal_round=3` behaves correctly, even though this league uses 0

> **Corrected 2026-07-31.** This list originally also demanded "pick 161 raises", which has no
> home in the locked signatures: `round_and_seat(pick, teams, reversal_round)` takes no `rounds`
> and therefore *cannot* know 161 is past the end of a 160-pick draft. Only `seat_picks`,
> `next_pick_for_seat` and `picks_until_next_turn` know the draft length. The bound is enforced
> there — `picks_made > teams * rounds` raises, while `picks_made == 160` stays legal and returns
> `None`. The criterion was wrong, not the signature.

**B — `roster.py`**
- The `{QB1, RB1}` / `{SUPER_FLEX, RB}` counterexample above
- A QB fills `SUPER_FLEX` but never `FLEX`; a TE fills `FLEX` and `SUPER_FLEX`
- Surplus players land in `bench`, never double-assigned
- Empty roster returns every slot unfilled; full roster returns none
- `DEF` never appears in `unfilled` when using `ranked_starter_slots`
- Assignment count equals the true maximum matching on randomised rosters (property test)

**C — `draft.py`**
- 160 picks recorded, then `picks()` is contiguous `1..160` with correct seats
- `undo` mid-round, at a round boundary, on pick 1, and on the final pick — sequence stays
  contiguous every time, **the LEG-3 regression test**
- Re-drafting a drafted player raises; recording past pick 160 raises; undoing a nonexistent pick
  raises
- `roster_for_seat` returns exactly that seat's 16 players
- Every operation leaves the original state unmutated

## Known limitations — carry these into Phase 2

Surfaced by the adversarial verification pass on 2026-07-31. None is a defect today; each
is a trap for the phase that consumes this layer.

**`unfilled` is not canonical.** Several maximum matchings can exist, and they can name
*different* slots as the need — opposite draft advice from the same roster. On a toy
layout, roster `{RB1, TE1}` with slots `[FLEX.1, RB.1, TE.1]` reports `TE.1` unfilled in one
insertion order and `RB.1` in the other. **It does not reproduce on this league** (0 cases
in 60,000 order-permutation trials) because Sleeper lists position-specific slots before
`FLEX`/`SUPER_FLEX`. It is latent and contingent entirely on slot ordering. Phase 2 will
read `unfilled` as "needs" — if it ever needs a stable answer, make the tie-break explicit
rather than relying on the current ordering.

**The production slot order hides the greedy bug.** Verified by mutation testing: swapping
in naive greedy leaves the *entire* integration suite passing, because with this league's
real slot order a flex-eligible player only reaches `SUPER_FLEX` once both `FLEX` slots are
gone, so greedy provably attains a maximum. The counterexample is reachable only with a
reordered slot list. **The protection against this class of bug lives exclusively in
`test_roster.py`** — do not "simplify" those reordered-slot tests away.

**`bench` conflates excluded positions with genuine surplus.** Feeding a roster containing
a `DEF` into `assign_starters(..., ranked_starter_slots)` puts the DEF in `bench`, so
`len(bench)` overstates bench usage against `bench_count`. Phase 2 must filter to
`RANKED_POSITIONS` before comparing.

**Two boundary conventions are duplicated rather than delegated.**
`DraftState.roster_for_seat` re-implements the `1 <= seat <= teams` check, and
`LeagueConfig.from_sleeper` requires `teams >= 2` while `snake._check_teams` allows
`teams >= 1`. Harmless — the config is the stricter one — but it is duplicated knowledge.

**Reversal-round semantics are not independently verified.** `test_snake.py`'s board helper
copies the `_descends` rule from the implementation, so under reversal it would agree with
a wrong interpretation. Hand-checked against standard third-round reversal and correct.
`reversal_round` is `0` for this league, so nothing rides on it today.

## Designed against these Phase 2 consumers

Signatures were chosen with the next phase in view, so Phase 1 is not immediately reworked:

- **Survival probability** consumes `picks_until_next_turn(seat, picks_made)` directly — hence
  decision 3, and hence `picks_made` rather than a `DraftState` argument, so it stays a pure
  function of integers.
- **Superflex-aware positional demand** consumes `ranked_starter_slots` across all teams. QB
  demand is `10 × QB slots + a contested share of 10 × SUPER_FLEX`, which is computable only
  because slots are eligibility sets (decision 8) rather than per-position integers.
- **The VORP baseline** — "best player likely available at your next turn" — needs
  `drafted_ids` plus `picks_until_next_turn`. Both are on `DraftState` or pure in `snake`.
- **Tier detection** needs no Phase 1 surface at all.
