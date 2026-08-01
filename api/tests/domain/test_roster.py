"""Tests for starter-slot assignment.

The heart of this file is the greedy counterexample and the property test. Everything else
guards eligibility and bookkeeping. The property test compares `assign_starters` against an
exhaustive brute-force search written independently below — an oracle that shares no code
with the augmenting-path implementation, which is the entire point of having one.

Callers must not depend on *which* maximum assignment comes back when several exist, so
these tests assert on counts and validity, never on a specific player landing in `FLEX`.
"""

import json
import random
from pathlib import Path
from typing import Any

import pytest

from popacta.domain.league import SLOT_ELIGIBILITY, LeagueConfig, SlotInstance
from popacta.domain.positions import Position
from popacta.domain.roster import StarterAssignment, assign_starters

FIXTURES = Path(__file__).parent.parent / "fixtures"


def slot(name: str, number: int = 1) -> SlotInstance:
    """A slot instance built from the real eligibility map, not a hand-typed set."""
    return SlotInstance(id=f"{name}.{number}", name=name, eligible=SLOT_ELIGIBILITY[name])


@pytest.fixture(scope="module")
def config() -> LeagueConfig:
    league = json.loads((FIXTURES / "sleeper_league.json").read_text(encoding="utf-8"))
    draft: dict[str, Any] = json.loads(
        (FIXTURES / "sleeper_draft.json").read_text(encoding="utf-8")
    )
    return LeagueConfig.from_sleeper(league, draft)


# --- the counterexample -------------------------------------------------------


def test_greedy_counterexample_qb_takes_the_superflex() -> None:
    """roster {QB1: QB, RB1: RB}, open slots {SUPER_FLEX, RB}.

    Greedy in roster order puts RB1 into SUPER_FLEX and then QB1 fits nothing, reporting
    one unfilled slot and one unplaced player. The maximum matching is QB1 -> SUPER_FLEX,
    RB1 -> RB, and nothing is left over.
    """
    roster = {"QB1": Position.QB, "RB1": Position.RB}
    slots = [slot("SUPER_FLEX"), slot("RB")]

    result = assign_starters(roster, slots)

    assert result.filled == {"SUPER_FLEX.1": "QB1", "RB.1": "RB1"}
    assert result.unfilled == ()
    assert result.bench == ()
    assert result.is_complete

    # The same two players in the insertion order that actually strands a greedy
    # implementation: RB1 is considered first and grabs SUPER_FLEX, leaving QB1 nowhere.
    # Dict order is not part of the contract, so the answer must not depend on it.
    reversed_order = assign_starters(
        {"RB1": Position.RB, "QB1": Position.QB}, [slot("SUPER_FLEX"), slot("RB")]
    )
    assert reversed_order.filled == {"SUPER_FLEX.1": "QB1", "RB.1": "RB1"}
    assert reversed_order.unfilled == ()
    assert reversed_order.bench == ()


def test_greedy_counterexample_is_order_independent() -> None:
    """The same roster in the other insertion order, and the same slots reversed.

    A "fix" that merely sorts the roster so QBs come first would pass the test above and
    fail here for some ordering.
    """
    for roster in (
        {"QB1": Position.QB, "RB1": Position.RB},
        {"RB1": Position.RB, "QB1": Position.QB},
    ):
        for slots in ([slot("SUPER_FLEX"), slot("RB")], [slot("RB"), slot("SUPER_FLEX")]):
            result = assign_starters(roster, slots)
            assert result.filled == {"SUPER_FLEX.1": "QB1", "RB.1": "RB1"}, (roster, slots)
            assert result.unfilled == ()


def test_chained_displacement_needs_a_two_step_augmenting_path() -> None:
    """A longer path: placing the QB must push the RB out of SUPER_FLEX and into FLEX.

    One level of displacement is not enough here — the RB evicted from SUPER_FLEX has to
    find FLEX, which is only reachable if the search keeps walking.
    """
    roster = {"WR1": Position.WR, "RB1": Position.RB, "QB1": Position.QB}
    slots = [slot("FLEX"), slot("SUPER_FLEX"), slot("WR")]

    result = assign_starters(roster, slots)

    assert len(result.filled) == 3
    assert result.filled["SUPER_FLEX.1"] == "QB1"
    assert set(result.filled.values()) == {"WR1", "RB1", "QB1"}


# --- eligibility --------------------------------------------------------------


def test_qb_fills_superflex_but_never_flex() -> None:
    assert assign_starters({"QB1": Position.QB}, [slot("SUPER_FLEX")]).filled == {
        "SUPER_FLEX.1": "QB1"
    }

    flex_only = assign_starters({"QB1": Position.QB}, [slot("FLEX")])
    assert flex_only.filled == {}
    assert [s.id for s in flex_only.unfilled] == ["FLEX.1"]
    assert flex_only.bench == ("QB1",)


def test_te_fills_both_flex_and_superflex() -> None:
    assert assign_starters({"TE1": Position.TE}, [slot("FLEX")]).filled == {"FLEX.1": "TE1"}
    assert assign_starters({"TE1": Position.TE}, [slot("SUPER_FLEX")]).filled == {
        "SUPER_FLEX.1": "TE1"
    }

    both = assign_starters(
        {"TE1": Position.TE, "TE2": Position.TE}, [slot("FLEX"), slot("SUPER_FLEX")]
    )
    assert set(both.filled) == {"FLEX.1", "SUPER_FLEX.1"}
    assert set(both.filled.values()) == {"TE1", "TE2"}


def test_a_defense_fits_only_the_def_slot() -> None:
    roster = {"DEF1": Position.DEF}
    assert assign_starters(roster, [slot("DEF")]).filled == {"DEF.1": "DEF1"}
    assert assign_starters(roster, [slot("FLEX"), slot("SUPER_FLEX")]).bench == ("DEF1",)


# --- bookkeeping --------------------------------------------------------------


def test_surplus_players_land_on_the_bench_and_are_never_double_assigned() -> None:
    roster = {f"RB{i}": Position.RB for i in range(1, 6)}
    slots = [slot("RB", 1), slot("RB", 2)]

    result = assign_starters(roster, slots)

    assert len(result.filled) == 2
    assert len(result.bench) == 3
    assert set(result.filled.values()).isdisjoint(result.bench)
    assert set(result.filled.values()) | set(result.bench) == set(roster)


def test_no_player_occupies_two_slots() -> None:
    roster = {"RB1": Position.RB}
    slots = [slot("RB"), slot("FLEX"), slot("SUPER_FLEX")]

    result = assign_starters(roster, slots)

    assert len(result.filled) == 1
    assert len(set(result.filled.values())) == 1
    assert len(result.unfilled) == 2


def test_empty_roster_leaves_every_slot_unfilled(config: LeagueConfig) -> None:
    result = assign_starters({}, config.ranked_starter_slots)

    assert result.filled == {}
    assert result.bench == ()
    assert result.unfilled == config.ranked_starter_slots
    assert not result.is_complete


def test_full_roster_leaves_nothing_unfilled(config: LeagueConfig) -> None:
    roster = {
        "QB1": Position.QB,
        "QB2": Position.QB,
        "RB1": Position.RB,
        "RB2": Position.RB,
        "WR1": Position.WR,
        "WR2": Position.WR,
        "WR3": Position.WR,
        "TE1": Position.TE,
        "TE2": Position.TE,
    }
    assert len(roster) == len(config.ranked_starter_slots)

    result = assign_starters(roster, config.ranked_starter_slots)

    assert result.unfilled == ()
    assert result.bench == ()
    assert result.is_complete
    assert len(result.filled) == len(roster)


def test_def_is_never_an_unfilled_need(config: LeagueConfig) -> None:
    """The app must never tell you to draft a defense — decision 1."""
    assert any(s.name == "DEF" for s in config.starter_slots), "fixture lost its DEF slot"

    ranked = assign_starters({}, config.ranked_starter_slots)
    assert not any(s.name == "DEF" for s in ranked.unfilled)

    partial = assign_starters({"QB1": Position.QB}, config.ranked_starter_slots)
    assert not any(s.name == "DEF" for s in partial.unfilled)

    # It is still reachable deliberately, via the full roster shape.
    full_shape = assign_starters({}, config.starter_slots)
    assert any(s.name == "DEF" for s in full_shape.unfilled)


def test_no_slots_benches_everyone() -> None:
    result = assign_starters({"QB1": Position.QB, "RB1": Position.RB}, [])

    assert result.filled == {}
    assert result.unfilled == ()
    assert result.bench == ("QB1", "RB1")
    assert result.is_complete, "no slots means nothing is unfilled"


def test_duplicate_slot_ids_raise() -> None:
    slots = [slot("RB", 1), slot("RB", 1)]

    with pytest.raises(ValueError, match=r"duplicate slot ids \['RB\.1'\]"):
        assign_starters({"RB1": Position.RB}, slots)


# --- property test against a brute-force oracle -------------------------------


def brute_force_max_filled(roster: dict[str, Position], slots: list[SlotInstance]) -> int:
    """The true maximum matching, by exhaustive search over every assignment.

    Deliberately naive and deliberately independent of `assign_starters`: each player in
    turn either takes some free eligible slot or goes to the bench, and we keep the best
    total. Exponential, so only ever called on small inputs.
    """
    players = list(roster.items())

    def search(index: int, used: frozenset[int]) -> int:
        if index == len(players):
            return 0
        _, position = players[index]
        best = search(index + 1, used)  # bench this player
        for slot_index, candidate in enumerate(slots):
            if slot_index not in used and position in candidate.eligible:
                best = max(best, 1 + search(index + 1, used | {slot_index}))
        return best

    return search(0, frozenset())


def assert_valid(
    result: StarterAssignment, roster: dict[str, Position], slots: list[SlotInstance]
) -> None:
    """Invariants every assignment must satisfy, maximum or not."""
    by_id = {s.id: s for s in slots}

    assert set(result.filled) <= set(by_id)
    for slot_id, player_id in result.filled.items():
        assert by_id[slot_id].accepts(roster[player_id]), f"{player_id} illegal in {slot_id}"

    placed = list(result.filled.values())
    assert len(placed) == len(set(placed)), "a player occupies two slots"
    assert set(placed).isdisjoint(result.bench)
    assert set(placed) | set(result.bench) == set(roster), "a rostered player vanished"
    assert {s.id for s in result.unfilled} == set(by_id) - set(result.filled)
    assert len(result.unfilled) == len(set(result.unfilled))


SLOT_POOL = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "DEF"]
POSITION_POOL = list(Position)


@pytest.mark.parametrize("seed", range(200))
def test_matching_is_maximum_on_random_rosters(seed: int) -> None:
    rng = random.Random(seed)

    roster = {f"P{i}": rng.choice(POSITION_POOL) for i in range(rng.randint(0, 7))}
    counts: dict[str, int] = {}
    slots = []
    for _ in range(rng.randint(0, 6)):
        name = rng.choice(SLOT_POOL)
        counts[name] = counts.get(name, 0) + 1
        slots.append(slot(name, counts[name]))

    result = assign_starters(roster, slots)

    assert_valid(result, roster, slots)
    assert len(result.filled) == brute_force_max_filled(roster, slots), (
        f"not a maximum matching for roster={roster} slots={[s.id for s in slots]}"
    )


def test_matching_is_maximum_on_the_real_slot_layout(config: LeagueConfig) -> None:
    """Same property, but against this league's actual nine ranked starter slots."""
    rng = random.Random(99)
    slots = list(config.ranked_starter_slots)

    for _ in range(150):
        roster = {f"P{i}": rng.choice(POSITION_POOL) for i in range(rng.randint(0, 6))}

        result = assign_starters(roster, slots)

        assert_valid(result, roster, slots)
        assert len(result.filled) == brute_force_max_filled(roster, slots), roster
