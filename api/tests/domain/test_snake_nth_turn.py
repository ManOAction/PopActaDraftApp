"""Tests for `snake.picks_until_nth_turn` — the two-pick lookahead Phase 2 needs.

Requested independently by two research passes, for two distinct reasons: at the turn a
seat picks back-to-back so `n = 1` returns `0` for both picks and cannot distinguish them,
and the replacement-level horizon needs the distance to a later pick.

`picks_until_next_turn` now delegates here, so these tests also guard that refactor.
"""

import pytest

from popacta.domain import snake
from popacta.domain.errors import DraftRangeError

TEAMS = 10
ROUNDS = 16
TOTAL = TEAMS * ROUNDS


@pytest.mark.parametrize("seat", range(1, TEAMS + 1))
@pytest.mark.parametrize("picks_made", [0, 1, 9, 10, 11, 40, 99, 159, 160])
def test_n_one_reproduces_picks_until_next_turn(seat: int, picks_made: int) -> None:
    """A strict generalization: `n = 1` must be the existing function, exactly."""
    assert snake.picks_until_nth_turn(
        seat, picks_made, TEAMS, ROUNDS, 1
    ) == snake.picks_until_next_turn(seat, picks_made, TEAMS, ROUNDS)


def test_n_one_matches_across_every_seat_and_state() -> None:
    for seat in range(1, TEAMS + 1):
        for picks_made in range(TOTAL + 1):
            assert snake.picks_until_nth_turn(
                seat, picks_made, TEAMS, ROUNDS, 1
            ) == snake.picks_until_next_turn(seat, picks_made, TEAMS, ROUNDS)


@pytest.mark.parametrize(
    ("seat", "picks_made", "n", "expected", "why"),
    [
        (10, 9, 1, 0, "seat 10 is on the clock at pick 10"),
        (10, 9, 2, 0, "its second pick is 11 — back-to-back, nobody picks in between"),
        (10, 9, 3, 18, "its third pick is 30; picks 12..29 belong to others"),
        (1, 1, 2, 18, "seat 1 picks at 20 and 21; picks 2..19 belong to others"),
        (4, 4, 1, 12, "seat 4 picks at 4 then 17; 12 intervening picks"),
        # Picks 5..23 is 19 picks, but pick 17 is seat 4's own, so 18 belong to others.
        (4, 4, 2, 18, "seat 4's pick after 17 is 24; its own pick 17 does not count"),
    ],
)
def test_pinned_lookahead_cases(
    seat: int, picks_made: int, n: int, expected: int, why: str
) -> None:
    assert snake.picks_until_nth_turn(seat, picks_made, TEAMS, ROUNDS, n) == expected, why


def test_the_turn_is_exactly_where_one_ply_is_degenerate() -> None:
    """The motivating case: at the turn, `n = 1` cannot tell the two picks apart."""
    first = snake.picks_until_nth_turn(10, 9, TEAMS, ROUNDS, 1)
    second = snake.picks_until_nth_turn(10, 9, TEAMS, ROUNDS, 2)
    third = snake.picks_until_nth_turn(10, 9, TEAMS, ROUNDS, 3)

    assert first == second == 0, "both back-to-back picks look identical at one ply"
    assert third > 0, "the second ply is what makes the pair distinguishable"


def test_counts_only_other_teams_picks() -> None:
    """Cross-check against the seat's own schedule rather than restating the formula."""
    for seat in (1, 4, 7, 10):
        picks = snake.seat_picks(seat, TEAMS, ROUNDS)
        for picks_made in (0, 5, 23, 88):
            future = [p for p in picks if p > picks_made]
            for n in (1, 2, 3):
                if len(future) < n:
                    continue
                target = future[n - 1]
                others = [p for p in range(picks_made + 1, target) if p not in picks]
                assert snake.picks_until_nth_turn(seat, picks_made, TEAMS, ROUNDS, n) == len(others)


def test_returns_none_when_fewer_than_n_picks_remain() -> None:
    assert snake.picks_until_nth_turn(1, TOTAL, TEAMS, ROUNDS, 1) is None
    assert snake.picks_until_nth_turn(1, 0, TEAMS, ROUNDS, ROUNDS) is not None
    assert snake.picks_until_nth_turn(1, 0, TEAMS, ROUNDS, ROUNDS + 1) is None


@pytest.mark.parametrize("n", [0, -1])
def test_n_below_one_raises(n: int) -> None:
    with pytest.raises(DraftRangeError, match="n must be at least 1"):
        snake.picks_until_nth_turn(1, 0, TEAMS, ROUNDS, n)


@pytest.mark.parametrize(
    ("seat", "picks_made"),
    [(0, 0), (TEAMS + 1, 0), (1, -1), (1, TOTAL + 1)],
)
def test_bounds_are_still_enforced_through_the_delegation(seat: int, picks_made: int) -> None:
    """The refactor must not have lost Phase 1's range checks."""
    with pytest.raises(DraftRangeError):
        snake.picks_until_nth_turn(seat, picks_made, TEAMS, ROUNDS, 1)


def test_third_round_reversal_is_respected() -> None:
    picks = snake.seat_picks(1, TEAMS, 4, 3)
    assert picks == (1, 20, 30, 31)
    assert snake.picks_until_nth_turn(1, 1, TEAMS, 4, 1, 3) == 18
    assert snake.picks_until_nth_turn(1, 1, TEAMS, 4, 2, 3) == 27
