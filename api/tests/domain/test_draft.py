"""Tests for `DraftState` — immutable draft state with safe, arbitrary undo.

The centre of gravity here is LEG-3: the 2025 app numbered picks with
`max(actual_pick_number) + 1`, so undoing a mid-draft pick left a permanent hole in the
sequence. Numbering is now derived from position, which makes a hole unrepresentable —
these tests exist to keep it that way.

Everything runs against `linear_numbering()`, the non-snake stub, so state transitions are
verified independently of the real snake arithmetic (which is written concurrently in
`snake.py`). Wave 2 integrates the two.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from popacta.domain.draft import DraftState, Pick
from popacta.domain.errors import (
    DraftCompleteError,
    DraftRangeError,
    DuplicatePickError,
    NoSuchPickError,
)
from popacta.domain.league import LeagueConfig

from .numbering_stub import linear_numbering

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def config() -> LeagueConfig:
    """The real league: 10 teams, 16 rounds, 160 picks."""
    league = json.loads((FIXTURES / "sleeper_league.json").read_text(encoding="utf-8"))
    draft: dict[str, Any] = json.loads(
        (FIXTURES / "sleeper_draft.json").read_text(encoding="utf-8")
    )
    return LeagueConfig.from_sleeper(league, draft)


@pytest.fixture
def empty(config: LeagueConfig) -> DraftState:
    return DraftState(config=config, numbering=linear_numbering())


def player(pick_number: int) -> str:
    """A traceable player id: the pick number it was originally recorded at."""
    return f"P{pick_number:03d}"


def drafted(state: DraftState, count: int) -> DraftState:
    """Record `count` picks, `P001`..., on top of `state`."""
    for pick_number in range(state.picks_made + 1, state.picks_made + count + 1):
        state = state.record(player(pick_number))
    return state


@pytest.fixture
def full(empty: DraftState) -> DraftState:
    """A completed draft: all 160 picks made."""
    return drafted(empty, empty.config.total_picks)


def expected_seat(pick_number: int, teams: int) -> int:
    """Seat under the linear stub — ascending, no reversal."""
    return ((pick_number - 1) % teams) + 1


def expected_round(pick_number: int, teams: int) -> int:
    return ((pick_number - 1) // teams) + 1


def assert_contiguous(state: DraftState) -> None:
    """The LEG-3 invariant: pick numbers are exactly `1..picks_made`, once each.

    Also checks every derived round and seat, because a shifted pick whose seat did not
    recompute would be just as wrong as a hole.
    """
    picks = state.picks()
    numbers = [pick.pick_number for pick in picks]

    assert numbers == list(range(1, state.picks_made + 1)), "hole or gap in the sequence"
    assert len(set(numbers)) == len(numbers), "duplicate pick numbers"

    teams = state.config.teams
    for pick in picks:
        assert pick.seat == expected_seat(pick.pick_number, teams)
        assert pick.round == expected_round(pick.pick_number, teams)
        assert 1 <= pick.seat <= teams


# --- recording ------------------------------------------------------------------------


def test_empty_state_has_no_picks(empty: DraftState) -> None:
    assert empty.player_ids == ()
    assert empty.picks() == ()
    assert empty.picks_made == 0
    assert empty.drafted_ids == frozenset()
    assert empty.next_pick_number == 1
    assert empty.seat_on_the_clock == 1


def test_a_full_draft_is_contiguous_with_correct_seats(full: DraftState) -> None:
    assert full.picks_made == 160
    assert_contiguous(full)

    picks = full.picks()
    assert picks[0] == Pick(pick_number=1, round=1, seat=1, player_id="P001")
    assert picks[9] == Pick(pick_number=10, round=1, seat=10, player_id="P010")
    assert picks[10] == Pick(pick_number=11, round=2, seat=1, player_id="P011")
    assert picks[159] == Pick(pick_number=160, round=16, seat=10, player_id="P160")


def test_record_appends_at_the_next_pick_number(empty: DraftState) -> None:
    state = drafted(empty, 3)

    assert state.player_ids == ("P001", "P002", "P003")
    assert state.picks_made == 3
    assert state.next_pick_number == 4
    assert state.seat_on_the_clock == 4
    assert state.drafted_ids == {"P001", "P002", "P003"}


def test_record_does_not_mutate_the_original(empty: DraftState) -> None:
    state = drafted(empty, 5)

    later = state.record("NEW")

    assert state.player_ids == ("P001", "P002", "P003", "P004", "P005")
    assert state.picks_made == 5
    assert "NEW" not in state.drafted_ids
    assert later is not state
    assert later.picks_made == 6


def test_two_records_from_one_state_do_not_alias(empty: DraftState) -> None:
    """Branching off one state is how undo/redo and "what if" views will work."""
    base = drafted(empty, 3)

    left = base.record("LEFT")
    right = base.record("RIGHT")

    assert base.player_ids == ("P001", "P002", "P003")
    assert left.player_ids == ("P001", "P002", "P003", "LEFT")
    assert right.player_ids == ("P001", "P002", "P003", "RIGHT")


def test_two_undos_from_one_state_do_not_alias(full: DraftState) -> None:
    first = full.undo(1)
    second = full.undo(160)

    assert full.picks_made == 160
    assert first.player_ids[0] == "P002"
    assert second.player_ids[0] == "P001"
    assert second.player_ids[-1] == "P159"


def test_state_is_frozen(empty: DraftState) -> None:
    with pytest.raises(AttributeError):
        empty.player_ids = ("X",)  # type: ignore[misc]


def test_redrafting_a_taken_player_raises(empty: DraftState) -> None:
    state = drafted(empty, 4)

    with pytest.raises(DuplicatePickError, match="P002"):
        state.record("P002")

    assert state.player_ids == ("P001", "P002", "P003", "P004")


def test_duplicate_message_names_the_original_pick_number(empty: DraftState) -> None:
    """On draft night the message is the whole debugging session."""
    state = drafted(empty, 30)

    with pytest.raises(DuplicatePickError, match="pick 17"):
        state.record("P017")


def test_recording_past_the_final_pick_raises(full: DraftState) -> None:
    with pytest.raises(DraftCompleteError, match="160"):
        full.record("P161")

    assert full.picks_made == 160


def test_a_completed_draft_has_no_next_pick(full: DraftState) -> None:
    assert full.next_pick_number is None
    assert full.seat_on_the_clock is None


def test_next_pick_and_clock_track_the_final_pick(empty: DraftState) -> None:
    almost = drafted(empty, 159)

    assert almost.next_pick_number == 160
    assert almost.seat_on_the_clock == 10

    complete = almost.record("P160")

    assert complete.next_pick_number is None
    assert complete.seat_on_the_clock is None
    assert almost.next_pick_number == 160, "recording must not mutate the original"


# --- undo: the LEG-3 regression -------------------------------------------------------


@pytest.mark.parametrize(
    ("undo_at", "description"),
    [
        (1, "the very first pick"),
        (5, "mid-round"),
        (10, "the last pick of a round"),
        (11, "the first pick of a round"),
        (80, "the halfway boundary"),
        (159, "the second-to-last pick"),
        (160, "the final pick"),
    ],
)
def test_undo_leaves_no_hole_anywhere_in_the_draft(
    full: DraftState, undo_at: int, description: str
) -> None:
    """LEG-3 regression: undo any pick, the sequence stays contiguous.

    `description` is unused at runtime; it names the case in the test id.
    """
    assert description

    after = full.undo(undo_at)

    assert after.picks_made == 159
    assert_contiguous(after)
    assert player(undo_at) not in after.drafted_ids
    assert after.player_ids == tuple(player(n) for n in range(1, 161) if n != undo_at)

    # The original is untouched.
    assert full.picks_made == 160
    assert player(undo_at) in full.drafted_ids
    assert_contiguous(full)


def test_undo_shifts_later_picks_down_and_recomputes_their_seats(full: DraftState) -> None:
    """The intended meaning of undo: the pick never happened.

    Under the linear stub, `P011` sits at pick 11 (round 2, seat 1). Remove pick 5 and it
    becomes pick 10 (round 1, seat 10). Nothing about the pick was stored, so it moves.
    """
    before = full.picks()[10]
    assert before == Pick(pick_number=11, round=2, seat=1, player_id="P011")

    after = full.undo(5)

    assert after.picks()[9] == Pick(pick_number=10, round=1, seat=10, player_id="P011")
    assert full.picks()[10] == before


def test_repeated_undos_stay_contiguous(full: DraftState) -> None:
    """The 2025 failure compounded: each undo left another permanent hole."""
    state = full
    for target in (17, 3, 140, 1, 100):
        state = state.undo(target)
        assert_contiguous(state)

    assert state.picks_made == 155
    assert full.picks_made == 160


def test_undo_then_record_reuses_the_vacated_pick_number(full: DraftState) -> None:
    """Correcting a mis-recorded pick: undo the wrong player, record the right one."""
    corrected = full.undo(42)

    assert corrected.next_pick_number == 160

    fixed = corrected.record("CORRECTED")

    assert fixed.picks_made == 160
    assert_contiguous(fixed)
    assert fixed.picks()[159].player_id == "CORRECTED"
    assert "P042" not in fixed.drafted_ids

    assert corrected.picks_made == 159, "recording must not mutate the original"
    assert "CORRECTED" not in corrected.drafted_ids
    assert full.picks_made == 160


def test_undo_of_the_only_pick_empties_the_draft(empty: DraftState) -> None:
    one = empty.record("P001")

    assert one.undo(1).player_ids == ()
    assert one.player_ids == ("P001",)


@pytest.mark.parametrize("pick_number", [0, -1, 6, 7, 161, 10_000])
def test_undoing_a_pick_that_was_never_made_raises(empty: DraftState, pick_number: int) -> None:
    state = drafted(empty, 5)

    with pytest.raises(NoSuchPickError, match=str(pick_number)):
        state.undo(pick_number)

    assert state.picks_made == 5


def test_undoing_on_an_empty_draft_raises(empty: DraftState) -> None:
    with pytest.raises(NoSuchPickError, match="1"):
        empty.undo(1)

    assert empty.player_ids == ()


def test_undo_does_not_mutate_the_original(full: DraftState) -> None:
    after = full.undo(1)

    assert after is not full
    assert full.player_ids == tuple(player(n) for n in range(1, 161))
    assert full.picks_made == 160
    assert full.next_pick_number is None


# --- rosters --------------------------------------------------------------------------


def test_every_seat_gets_exactly_sixteen_players(full: DraftState) -> None:
    seen: list[str] = []

    for seat in range(1, full.config.teams + 1):
        roster = full.roster_for_seat(seat)
        assert len(roster) == full.config.rounds == 16
        seen.extend(roster)

    assert sorted(seen) == sorted(full.player_ids), "every pick belongs to exactly one seat"
    assert full.picks_made == 160


def test_roster_is_that_seats_picks_in_order(full: DraftState) -> None:
    """Seat 3 under the linear stub owns picks 3, 13, 23, ..., 153."""
    assert full.roster_for_seat(3) == tuple(player(n) for n in range(3, 161, 10))


def test_roster_reflects_a_partial_draft(empty: DraftState) -> None:
    state = drafted(empty, 12)

    assert state.roster_for_seat(1) == ("P001", "P011")
    assert state.roster_for_seat(2) == ("P002", "P012")
    assert state.roster_for_seat(3) == ("P003",)


def test_roster_after_undo_reflects_the_reshuffled_seats(full: DraftState) -> None:
    """Because seats are derived, undoing pick 1 hands `P011` to seat 10."""
    after = full.undo(1)

    assert after.roster_for_seat(10)[0] == "P011"
    assert after.roster_for_seat(1)[0] == "P002"
    assert full.roster_for_seat(1)[0] == "P001"


@pytest.mark.parametrize("seat", [0, -1, 11, 99])
def test_roster_for_a_seat_outside_the_league_raises(full: DraftState, seat: int) -> None:
    with pytest.raises(DraftRangeError, match=str(seat)):
        full.roster_for_seat(seat)


def test_draft_range_error_is_a_value_error(full: DraftState) -> None:
    """Documented on the exception; existing `except ValueError` handlers must still work."""
    with pytest.raises(ValueError, match="11"):
        full.roster_for_seat(11)


# --- the linear stub itself -----------------------------------------------------------


def test_linear_numbering_is_not_snake_order() -> None:
    """If this ever starts reversing, every test above is testing the wrong thing."""
    numbering = linear_numbering()

    assert numbering.round_and_seat(1, 10) == (1, 1)
    assert numbering.round_and_seat(10, 10) == (1, 10)
    assert numbering.round_and_seat(11, 10) == (2, 1)  # snake would say seat 10
    assert numbering.round_and_seat(20, 10) == (2, 10)
    assert numbering.round_and_seat(160, 10) == (16, 10)


def test_linear_numbering_ignores_reversal_round() -> None:
    numbering = linear_numbering()

    assert numbering.round_and_seat(21, 10, 3) == numbering.round_and_seat(21, 10, 0)


def test_linear_numbering_rejects_a_pick_below_one() -> None:
    with pytest.raises(DraftRangeError, match="0"):
        linear_numbering().round_and_seat(0, 10)
