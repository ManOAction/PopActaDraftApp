"""Tests for starting-lineup value `W(R)` and marginal value `u(p|R)`.

Two things in this file are load-bearing and must not be "simplified":

1. **The reordered-slot tests.** `W` has slot-dependent floors, which breaks the matroid
   structure that makes greedy optimal for `assign_starters`. Greedy-by-value-into-first-
   eligible-slot is suboptimal 0/20000 times in Sleeper's production slot order and
   11773/20000 times under a randomised one, worst shortfall 546.8 points — measured on
   this league's nine ranked slots, reproducing the plan's table. Sleeper listing
   position-specific slots first and `SUPER_FLEX` last is *received data, not a
   guarantee*, so every test that only uses the production order would still pass against
   a broken implementation. This is the third time this project has found production slot
   order hiding a greedy bug; the other two are in `docs/plan_phase1_domain_core.md`.

   Verified by mutation: substituting that greedy for the DP left 400 tests passing and
   failed exactly 23 — `test_slot_order_never_changes_the_answer`,
   `test_every_permutation_of_the_real_layout_agrees`,
   `test_reversing_a_small_layout_agrees_over_every_roster_shape`,
   `test_matches_the_oracle_on_a_shuffled_real_layout`, and 19 randomised-slot-order
   seeds. Every production-order test stayed green. That contrast is the whole point.
2. **The brute-force oracle**, written independently below and sharing no code with the
   DP. It enumerates assignments slot-major; the implementation is player-major over
   bitmasks.

Replacement levels are built here rather than imported from `replacement.py` — these
functions take `replacement` as a parameter precisely so the value axis can be tested
without the baseline machinery. `r_QB` is the largest of the four, as measured
(`r_QB = QB30 = 192.8`); that ordering is what prices `SUPER_FLEX`.
"""

import itertools
import json
import random
from pathlib import Path
from typing import Any

import pytest

from popacta.domain.league import SLOT_ELIGIBILITY, LeagueConfig, SlotInstance
from popacta.domain.lineup import lineup_value, marginal_value
from popacta.domain.players import Player
from popacta.domain.positions import RANKED_POSITIONS, Position

FIXTURES = Path(__file__).parent.parent / "fixtures"

REPLACEMENT: dict[Position, float] = {
    Position.QB: 192.8,
    Position.RB: 105.0,
    Position.WR: 110.0,
    Position.TE: 70.0,
}
"""Draft-demand replacement levels, in the measured shape: `r_QB` is the highest.

So `floor(SUPER_FLEX) = 192.8` and `floor(FLEX) = max(105, 110, 70) = 110`.
"""

FLOORS_SUM = 1105.6
"""Sum of the nine ranked slot floors: 192.8 + 105 + 105 + 110 + 110 + 70 + 110 + 110 + 192.8."""

RANKED_POSITION_LIST = sorted(RANKED_POSITIONS, key=str)


def slot(name: str, number: int = 1) -> SlotInstance:
    """A slot instance built from the real eligibility map, not a hand-typed set."""
    return SlotInstance(id=f"{name}.{number}", name=name, eligible=SLOT_ELIGIBILITY[name])


def player(player_id: str, position: Position, points: float) -> Player:
    return Player(player_id=player_id, name=player_id, position=position, points=points)


@pytest.fixture(scope="module")
def config() -> LeagueConfig:
    league = json.loads((FIXTURES / "sleeper_league.json").read_text(encoding="utf-8"))
    draft: dict[str, Any] = json.loads(
        (FIXTURES / "sleeper_draft.json").read_text(encoding="utf-8")
    )
    return LeagueConfig.from_sleeper(league, draft)


@pytest.fixture(scope="module")
def ranked_slots(config: LeagueConfig) -> tuple[SlotInstance, ...]:
    slots = config.ranked_starter_slots
    assert len(slots) == 9, "fixture no longer has the nine ranked starter slots"
    return slots


# --- the floor: an unfilled slot is worth replacement level, not zero ----------


def test_empty_roster_is_the_sum_of_the_floors(ranked_slots: tuple[SlotInstance, ...]) -> None:
    assert lineup_value([], ranked_slots, REPLACEMENT) == pytest.approx(FLOORS_SUM)


def test_an_unfilled_slot_contributes_its_floor_not_zero() -> None:
    """One QB, two slots. The empty RB slot is worth `r_RB`, not nothing."""
    slots = [slot("QB"), slot("RB")]

    empty = lineup_value([], slots, REPLACEMENT)
    assert empty == pytest.approx(192.8 + 105.0)

    one_qb = lineup_value([player("QB1", Position.QB, 300.0)], slots, REPLACEMENT)
    assert one_qb == pytest.approx(300.0 + 105.0)


def test_a_player_below_replacement_never_lowers_the_lineup() -> None:
    """`max(F, floor)` — a sub-replacement starter is worth the floor, so `u == 0`."""
    slots = [slot("TE")]
    weak = player("TE9", Position.TE, 50.0)

    assert lineup_value([weak], slots, REPLACEMENT) == pytest.approx(70.0)
    assert marginal_value(weak, [], slots, REPLACEMENT) == 0.0


def test_no_slots_means_no_value() -> None:
    assert lineup_value([player("RB1", Position.RB, 300.0)], [], REPLACEMENT) == 0.0
    assert marginal_value(player("RB1", Position.RB, 300.0), [], [], REPLACEMENT) == 0.0


# --- empty roster reduces to classic VORP with the right baseline -------------


@pytest.mark.parametrize(
    ("position", "points"),
    [
        (Position.QB, 300.0),
        (Position.RB, 200.0),
        (Position.WR, 200.0),
        (Position.TE, 150.0),
    ],
)
def test_empty_roster_marginal_is_exactly_points_minus_replacement(
    ranked_slots: tuple[SlotInstance, ...],
    position: Position,
    points: float,
) -> None:
    """`u(p | {}) == F(p) - r_pos(p)` — exactly, not approximately.

    Exactness is why `marginal_value` subtracts the gain terms instead of two `W` values:
    `(S + a) - (S + b)` is not `a - b` in floating point once `S` is a four-figure sum.
    """
    candidate = player("P", position, points)
    expected = points - REPLACEMENT[position]

    assert marginal_value(candidate, [], ranked_slots, REPLACEMENT) == expected


# --- superflex is priced, not asserted ----------------------------------------


def test_two_qbs_occupy_qb_and_super_flex(ranked_slots: tuple[SlotInstance, ...]) -> None:
    roster = [player("QB1", Position.QB, 350.0), player("QB2", Position.QB, 300.0)]

    value = lineup_value(roster, ranked_slots, REPLACEMENT)

    # Both QBs are above `r_QB` and both are counted: the only way to bank both surpluses
    # is QB.1 and SUPER_FLEX.1.
    assert value == pytest.approx(FLOORS_SUM + (350.0 - 192.8) + (300.0 - 192.8))


def test_a_third_qb_behind_two_better_ones_is_worth_nothing(
    ranked_slots: tuple[SlotInstance, ...],
) -> None:
    """Roster need lives inside the value — no separate need multiplier (LEG-5)."""
    roster = [player("QB1", Position.QB, 350.0), player("QB2", Position.QB, 300.0)]
    third = player("QB3", Position.QB, 260.0)

    assert marginal_value(third, roster, ranked_slots, REPLACEMENT) == 0.0


def test_an_rb_takes_rb_not_super_flex_while_rb_is_free() -> None:
    slots = [slot("RB"), slot("SUPER_FLEX")]
    roster = [player("RB1", Position.RB, 250.0)]

    # In RB: 250 + floor(SUPER_FLEX). In SUPER_FLEX: floor(RB) + 250. The first is larger
    # because `r_QB > r_RB`, so the RB never wastes the superflex.
    assert lineup_value(roster, slots, REPLACEMENT) == pytest.approx(250.0 + 192.8)
    assert marginal_value(roster[0], [], slots, REPLACEMENT) == 250.0 - 105.0


def test_an_rb_reaches_super_flex_only_once_rb_and_flex_are_full() -> None:
    """It is priced, not forbidden: a third RB clearing `r_QB` does take SUPER_FLEX."""
    slots = [slot("RB"), slot("FLEX"), slot("SUPER_FLEX")]
    roster = [
        player("RB1", Position.RB, 300.0),
        player("RB2", Position.RB, 280.0),
        player("RB3", Position.RB, 260.0),
    ]

    assert lineup_value(roster, slots, REPLACEMENT) == pytest.approx(300.0 + 280.0 + 260.0)

    # A fourth RB below `r_QB` adds nothing: every slot he could take already holds more.
    fourth = player("RB4", Position.RB, 180.0)
    assert marginal_value(fourth, roster, slots, REPLACEMENT) == 0.0


# --- the reordered-slot counterexample ----------------------------------------
#
# DO NOT SIMPLIFY THESE AWAY. Greedy is exact under Sleeper's production slot order and
# catastrophic (worst case 397 points) under any other. Only the reordered cases can tell
# the difference, so deleting them silently removes the entire protection.


def test_slot_order_never_changes_the_answer() -> None:
    """The hand-computed counterexample that kills greedy-into-first-eligible-slot.

    Slots {RB, FLEX, SUPER_FLEX}, floors {105, 110, 192.8}. Three RBs: 300, 280, 160.

    Optimal:  300 -> RB, 280 -> FLEX, and SUPER_FLEX left at its floor (160 < 192.8)
              = 300 + 280 + 192.8 = 772.8 — the best lineup does *not* fill every slot.
    Greedy, best player into the first eligible free slot, slots listed SUPER_FLEX-first:
              300 -> SUPER_FLEX, 280 -> FLEX, 160 -> RB = 740.0, short by 32.8.
    """
    roster = [
        player("RB1", Position.RB, 300.0),
        player("RB2", Position.RB, 280.0),
        player("RB3", Position.RB, 160.0),
    ]
    production = [slot("RB"), slot("FLEX"), slot("SUPER_FLEX")]
    reordered = [slot("SUPER_FLEX"), slot("FLEX"), slot("RB")]

    assert lineup_value(roster, production, REPLACEMENT) == pytest.approx(772.8)
    assert lineup_value(roster, reordered, REPLACEMENT) == pytest.approx(772.8)


def test_every_permutation_of_the_real_layout_agrees(
    ranked_slots: tuple[SlotInstance, ...],
) -> None:
    """`W` is a property of the slot *multiset*, so shuffling the list cannot move it.

    This needs no oracle: greedy happens to be exact in the production order, so any
    order-sensitive implementation disagrees with itself here.
    """
    rng = random.Random(4)
    slots = list(ranked_slots)

    for seed in range(120):
        roster = random_roster(random.Random(seed), 6)
        expected = lineup_value(roster, slots, REPLACEMENT)

        shuffled = slots[:]
        rng.shuffle(shuffled)
        assert lineup_value(roster, shuffled, REPLACEMENT) == pytest.approx(expected), (
            f"slot order changed W for roster={[(p.player_id, p.points) for p in roster]}"
        )


def test_reversing_a_small_layout_agrees_over_every_roster_shape() -> None:
    """Exhaustive rather than random: every position triple against a reversed layout."""
    slots = [slot("QB"), slot("RB"), slot("FLEX"), slot("SUPER_FLEX")]
    reversed_slots = list(reversed(slots))

    for positions in itertools.product(RANKED_POSITION_LIST, repeat=3):
        roster = [
            player(f"P{i}", position, 300.0 - 40.0 * i) for i, position in enumerate(positions)
        ]
        assert lineup_value(roster, slots, REPLACEMENT) == pytest.approx(
            lineup_value(roster, reversed_slots, REPLACEMENT)
        ), positions


# --- preconditions: raise, never absorb ---------------------------------------


@pytest.mark.parametrize("position", [Position.DEF, Position.K])
def test_an_excluded_position_reaching_lineup_value_raises(
    ranked_slots: tuple[SlotInstance, ...],
    position: Position,
) -> None:
    """Phase 1's `bench` conflation, asserted rather than assumed.

    A DEF matches no ranked slot, so it would be silently benched and counted as bench
    surplus instead of failing. That is the LEG-4 shape: a wrong number, not a crash.
    """
    roster = [player("X", position, 120.0)]

    with pytest.raises(ValueError, match="does not rank"):
        lineup_value(roster, ranked_slots, REPLACEMENT)

    with pytest.raises(ValueError, match="does not rank"):
        marginal_value(player("Y", position, 120.0), [], ranked_slots, REPLACEMENT)


def test_a_roster_position_missing_from_replacement_raises() -> None:
    """No `.get(pos, 0)` — a missing baseline is a data defect, not a zero."""
    slots = [slot("QB")]
    qb_only = {Position.QB: 192.8}

    with pytest.raises(ValueError, match="no replacement level for position 'RB'"):
        lineup_value([player("RB1", Position.RB, 200.0)], slots, qb_only)


def test_a_slot_position_missing_from_replacement_raises(
    ranked_slots: tuple[SlotInstance, ...],
) -> None:
    without_te = {p: r for p, r in REPLACEMENT.items() if p is not Position.TE}

    with pytest.raises(ValueError, match=r"slot 'TE\.1' accepts \['TE'\]"):
        lineup_value([], ranked_slots, without_te)


def test_the_def_slot_raises_rather_than_scoring_as_zero(config: LeagueConfig) -> None:
    """`config.starter_slots` includes DEF, which has no replacement level here."""
    assert any(s.name == "DEF" for s in config.starter_slots), "fixture lost its DEF slot"

    with pytest.raises(ValueError, match="ranked_starter_slots"):
        lineup_value([], config.starter_slots, REPLACEMENT)


# --- property tests against a brute-force oracle ------------------------------


def brute_force_lineup_value(
    roster: list[Player],
    slots: list[SlotInstance],
    replacement: dict[Position, float],
) -> float:
    """`W(R)` by exhaustive search. Deliberately naive and independent of the DP.

    Walks *slots* in order — each either stays empty at its floor or takes some unused
    eligible player — where the implementation walks *players* over slot bitmasks.
    Exponential, so only ever called on small inputs.
    """
    floors = [max(replacement[p] for p in s.eligible) for s in slots]

    def search(slot_index: int, used: frozenset[int]) -> float:
        if slot_index == len(slots):
            return 0.0
        floor = floors[slot_index]
        best = floor + search(slot_index + 1, used)  # leave this slot empty
        for index, candidate in enumerate(roster):
            if index not in used and slots[slot_index].accepts(candidate.position):
                filled = max(candidate.points, floor)
                best = max(best, filled + search(slot_index + 1, used | {index}))
        return best

    return search(0, frozenset())


SLOT_POOL = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"]


def describe(roster: list[Player]) -> list[tuple[str, str, float]]:
    """Readable failure output — a bare `Player` repr buries the numbers that matter."""
    return [(p.player_id, str(p.position), p.points) for p in roster]


def random_roster(rng: random.Random, max_size: int) -> list[Player]:
    return [
        player(f"P{i}", rng.choice(RANKED_POSITION_LIST), round(rng.uniform(40.0, 400.0), 1))
        for i in range(rng.randint(0, max_size))
    ]


def random_candidate(rng: random.Random) -> Player:
    return player("CAND", rng.choice(RANKED_POSITION_LIST), round(rng.uniform(40.0, 400.0), 1))


def random_slots(rng: random.Random, max_size: int) -> list[SlotInstance]:
    """A random slot list — including a random *order*, which is the whole point."""
    counts: dict[str, int] = {}
    slots = []
    for _ in range(rng.randint(0, max_size)):
        name = rng.choice(SLOT_POOL)
        counts[name] = counts.get(name, 0) + 1
        slots.append(slot(name, counts[name]))
    return slots


@pytest.mark.parametrize("seed", range(200))
def test_matches_the_oracle_on_random_rosters_and_random_slot_orders(seed: int) -> None:
    rng = random.Random(seed)
    roster = random_roster(rng, 5)
    slots = random_slots(rng, 6)

    detail = f"roster={describe(roster)} slots={[s.id for s in slots]}"
    assert lineup_value(roster, slots, REPLACEMENT) == pytest.approx(
        brute_force_lineup_value(roster, slots, REPLACEMENT)
    ), detail


def test_matches_the_oracle_on_the_production_slot_order(
    ranked_slots: tuple[SlotInstance, ...],
) -> None:
    slots = list(ranked_slots)

    for seed in range(60):
        roster = random_roster(random.Random(seed), 4)
        assert lineup_value(roster, slots, REPLACEMENT) == pytest.approx(
            brute_force_lineup_value(roster, slots, REPLACEMENT)
        ), roster


def test_matches_the_oracle_on_a_shuffled_real_layout(
    ranked_slots: tuple[SlotInstance, ...],
) -> None:
    """The test the 397-point error hides behind. Do not merge it into the one above."""
    shuffler = random.Random(11)

    for seed in range(60):
        roster = random_roster(random.Random(seed), 4)
        slots = list(ranked_slots)
        shuffler.shuffle(slots)

        assert lineup_value(roster, slots, REPLACEMENT) == pytest.approx(
            brute_force_lineup_value(roster, slots, REPLACEMENT)
        ), f"roster={describe(roster)} slots={[s.id for s in slots]}"


@pytest.mark.parametrize("seed", range(200))
def test_marginal_value_is_never_negative_and_is_the_difference_of_two_maxima(
    seed: int,
) -> None:
    rng = random.Random(1000 + seed)
    roster = random_roster(rng, 6)
    slots = random_slots(rng, 6)
    candidate = random_candidate(rng)

    result = marginal_value(candidate, roster, slots, REPLACEMENT)

    assert result >= 0.0, "adding a player lowered the best achievable lineup"
    assert result == pytest.approx(
        lineup_value([*roster, candidate], slots, REPLACEMENT)
        - lineup_value(roster, slots, REPLACEMENT)
    )


def test_marginal_value_ignores_roster_order(ranked_slots: tuple[SlotInstance, ...]) -> None:
    """`u` is a difference of two maxima, so which player was added first cannot matter."""
    slots = list(ranked_slots)

    for seed in range(60):
        rng = random.Random(500 + seed)
        roster = random_roster(rng, 5)
        candidate = random_candidate(rng)

        expected = marginal_value(candidate, roster, slots, REPLACEMENT)
        rng.shuffle(roster)
        assert marginal_value(candidate, roster, slots, REPLACEMENT) == pytest.approx(expected)
