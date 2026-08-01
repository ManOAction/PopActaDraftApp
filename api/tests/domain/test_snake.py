"""Tests for snake draft order and pick arithmetic.

Two things are being defended here.

The first is that snake order exists at all — the 2025 app treated `total_teams` purely as
picks-per-round and never modelled the reversal (LEG-3).

The second is decision 3 in `docs/plan_phase1_domain_core.md`: `picks_until_next_turn`
counts *other teams' intervening picks*, not the pick-number delta. An implementation that
returns the delta is off by exactly one everywhere, crashes nothing, and quietly shades
every survival estimate in Phase 2. The back-to-back turn (`(10, 9)` and `(10, 10)` both
`0`) is the case that separates the two definitions.
"""

import pytest

from popacta.domain.errors import DraftRangeError
from popacta.domain.snake import (
    next_pick_for_seat,
    pick_number,
    picks_until_next_turn,
    round_and_seat,
    seat_picks,
)

# The pinned league: 10 teams, 16 rounds, no third-round reversal.
TEAMS = 10
ROUNDS = 16
TOTAL_PICKS = TEAMS * ROUNDS


def board(teams: int, rounds: int, reversal_round: int = 0) -> list[int]:
    """The draft board built by listing seats per round, independent of the arithmetic.

    Index `i` holds the seat owning pick `i + 1`. Deliberately constructed by reversing
    lists rather than by modular arithmetic, so it fails differently from the module under
    test rather than reproducing its bugs.
    """
    order: list[int] = []
    for round_ in range(1, rounds + 1):
        seats = list(range(1, teams + 1))
        descending = round_ % 2 == 0
        if reversal_round > 0 and round_ >= reversal_round:
            descending = not descending
        if descending:
            seats.reverse()
        order.extend(seats)
    return order


# --- direction ----------------------------------------------------------------------


@pytest.mark.parametrize("seat", range(1, TEAMS + 1))
def test_round_one_ascends_from_seat_one(seat: int) -> None:
    assert pick_number(1, seat, TEAMS) == seat


@pytest.mark.parametrize("seat", range(1, TEAMS + 1))
def test_round_two_descends_from_seat_ten(seat: int) -> None:
    assert pick_number(2, seat, TEAMS) == 21 - seat


def test_round_one_is_exactly_picks_one_through_ten_in_seat_order() -> None:
    assert [pick_number(1, s, TEAMS) for s in range(1, TEAMS + 1)] == list(range(1, 11))


def test_round_two_is_exactly_picks_eleven_through_twenty_reversed() -> None:
    assert [pick_number(2, s, TEAMS) for s in range(1, TEAMS + 1)] == list(range(20, 10, -1))


@pytest.mark.parametrize("round_", range(1, ROUNDS + 1))
def test_odd_rounds_ascend_and_even_rounds_descend_through_round_sixteen(round_: int) -> None:
    picks = [pick_number(round_, seat, TEAMS) for seat in range(1, TEAMS + 1)]

    assert sorted(picks) == list(range((round_ - 1) * TEAMS + 1, round_ * TEAMS + 1))
    if round_ % 2 == 1:
        assert picks == sorted(picks), f"round {round_} should ascend"
    else:
        assert picks == sorted(picks, reverse=True), f"round {round_} should descend"


@pytest.mark.parametrize("round_", range(1, ROUNDS))
def test_the_flip_holds_at_every_round_boundary(round_: int) -> None:
    """The last pick of a round and the first of the next belong to the same seat."""
    last_of_round = pick_number(round_, TEAMS if round_ % 2 == 1 else 1, TEAMS)
    first_of_next = pick_number(round_ + 1, TEAMS if round_ % 2 == 1 else 1, TEAMS)

    assert last_of_round == round_ * TEAMS
    assert first_of_next == round_ * TEAMS + 1


def test_every_pick_matches_the_independently_built_board() -> None:
    expected = board(TEAMS, ROUNDS)

    for pick in range(1, TOTAL_PICKS + 1):
        _, seat = round_and_seat(pick, TEAMS)
        assert seat == expected[pick - 1], f"pick {pick}"


# --- inverses -----------------------------------------------------------------------


@pytest.mark.parametrize("pick", range(1, TOTAL_PICKS + 1))
def test_round_and_seat_inverts_pick_number_for_all_160_picks(pick: int) -> None:
    round_, seat = round_and_seat(pick, TEAMS)

    assert 1 <= round_ <= ROUNDS
    assert 1 <= seat <= TEAMS
    assert pick_number(round_, seat, TEAMS) == pick


def test_pick_number_is_a_bijection_onto_1_through_160() -> None:
    picks = [
        pick_number(round_, seat, TEAMS)
        for round_ in range(1, ROUNDS + 1)
        for seat in range(1, TEAMS + 1)
    ]

    assert sorted(picks) == list(range(1, TOTAL_PICKS + 1))


# --- seat_picks ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seat", "expected_prefix"),
    [
        (1, (1, 20, 21, 40)),
        (2, (2, 19, 22, 39)),
        (4, (4, 17, 24, 37)),
        (9, (9, 12, 29, 32)),
        (10, (10, 11, 30, 31)),
    ],
)
def test_seat_picks_opens_with_the_expected_snake_pattern(
    seat: int, expected_prefix: tuple[int, ...]
) -> None:
    assert seat_picks(seat, TEAMS, ROUNDS)[:4] == expected_prefix


def test_seat_one_has_the_full_expected_pick_list() -> None:
    expected = (1, 20, 21, 40, 41, 60, 61, 80, 81, 100, 101, 120, 121, 140, 141, 160)

    assert seat_picks(1, TEAMS, ROUNDS) == expected


def test_seat_ten_has_the_full_expected_pick_list() -> None:
    expected = (10, 11, 30, 31, 50, 51, 70, 71, 90, 91, 110, 111, 130, 131, 150, 151)

    assert seat_picks(10, TEAMS, ROUNDS) == expected


@pytest.mark.parametrize("seat", range(1, TEAMS + 1))
def test_seat_picks_are_ascending_and_one_per_round(seat: int) -> None:
    picks = seat_picks(seat, TEAMS, ROUNDS)

    assert len(picks) == ROUNDS
    assert list(picks) == sorted(picks)
    assert len(set(picks)) == ROUNDS


def test_the_ten_seats_partition_the_whole_draft() -> None:
    all_picks = [p for seat in range(1, TEAMS + 1) for p in seat_picks(seat, TEAMS, ROUNDS)]

    assert sorted(all_picks) == list(range(1, TOTAL_PICKS + 1))


# --- next_pick_for_seat -------------------------------------------------------------


@pytest.mark.parametrize(
    ("seat", "picks_made", "expected"),
    [
        (1, 0, 1),
        (1, 1, 20),
        (1, 19, 20),
        (1, 20, 21),
        (4, 0, 4),
        (4, 4, 17),
        (10, 9, 10),
        (10, 10, 11),
        (10, 11, 30),
    ],
)
def test_next_pick_for_seat_finds_the_first_pick_after_those_already_made(
    seat: int, picks_made: int, expected: int
) -> None:
    assert next_pick_for_seat(seat, picks_made, TEAMS, ROUNDS) == expected


@pytest.mark.parametrize("seat", range(1, TEAMS + 1))
def test_next_pick_for_seat_is_none_after_that_seats_final_pick(seat: int) -> None:
    final = seat_picks(seat, TEAMS, ROUNDS)[-1]

    assert next_pick_for_seat(seat, final - 1, TEAMS, ROUNDS) == final
    assert next_pick_for_seat(seat, final, TEAMS, ROUNDS) is None
    assert next_pick_for_seat(seat, TOTAL_PICKS, TEAMS, ROUNDS) is None


# --- picks_until_next_turn — the keystone -------------------------------------------


@pytest.mark.parametrize(
    ("seat", "picks_made", "expected"),
    [
        # The back-to-back turn. Seat 10 picks at 10 and 11, so both are 0. An
        # implementation returning the pick-number delta gives 1 for (10, 10).
        (10, 9, 0),
        (10, 10, 0),
        # The mirror case: seat 1 picks at 1 then 20, so 18 other teams pick between.
        (1, 0, 0),
        (1, 1, 18),
        # Decision 3's worked example: seat 4 picks at 4 then 17. Delta 13, answer 12.
        (4, 4, 12),
        (4, 0, 3),
        (4, 16, 0),
        (4, 17, 6),
        (2, 2, 16),
        (5, 5, 10),
        (9, 9, 2),
    ],
)
def test_picks_until_next_turn_counts_other_teams_picks_not_the_delta(
    seat: int, picks_made: int, expected: int
) -> None:
    assert picks_until_next_turn(seat, picks_made, TEAMS, ROUNDS) == expected


def test_the_turn_gives_two_consecutive_zeroes_while_the_wing_gives_eighteen() -> None:
    """Stated as one assertion block because this is the pair that defines the metric."""
    assert picks_until_next_turn(10, 9, TEAMS, ROUNDS) == 0
    assert picks_until_next_turn(10, 10, TEAMS, ROUNDS) == 0
    assert picks_until_next_turn(1, 1, TEAMS, ROUNDS) == 18


@pytest.mark.parametrize("seat", range(1, TEAMS + 1))
def test_picks_until_next_turn_equals_the_counted_intervening_picks(seat: int) -> None:
    """Counts the other seats' picks off the independently-built board.

    This is the definition, spelled out without reusing the module's arithmetic: how many
    board slots between now and my next pick belong to somebody else.
    """
    seats_by_pick = board(TEAMS, ROUNDS)
    mine = [i + 1 for i, s in enumerate(seats_by_pick) if s == seat]

    for picks_made in range(TOTAL_PICKS + 1):
        remaining = [p for p in mine if p > picks_made]
        if not remaining:
            assert picks_until_next_turn(seat, picks_made, TEAMS, ROUNDS) is None
            continue
        next_mine = remaining[0]
        others = sum(
            1 for pick in range(picks_made + 1, next_mine) if seats_by_pick[pick - 1] != seat
        )

        assert picks_until_next_turn(seat, picks_made, TEAMS, ROUNDS) == others, (
            f"seat {seat}, picks_made {picks_made}"
        )


@pytest.mark.parametrize("seat", range(1, TEAMS + 1))
def test_picks_until_next_turn_is_next_pick_minus_picks_made_minus_one(seat: int) -> None:
    for picks_made in range(TOTAL_PICKS + 1):
        next_mine = next_pick_for_seat(seat, picks_made, TEAMS, ROUNDS)
        expected = None if next_mine is None else next_mine - picks_made - 1

        assert picks_until_next_turn(seat, picks_made, TEAMS, ROUNDS) == expected


@pytest.mark.parametrize("seat", range(1, TEAMS + 1))
def test_picks_until_next_turn_is_never_negative(seat: int) -> None:
    for picks_made in range(TOTAL_PICKS + 1):
        result = picks_until_next_turn(seat, picks_made, TEAMS, ROUNDS)
        assert result is None or result >= 0


@pytest.mark.parametrize("seat", range(1, TEAMS + 1))
def test_picks_until_next_turn_is_none_after_that_seats_final_pick(seat: int) -> None:
    final = seat_picks(seat, TEAMS, ROUNDS)[-1]

    assert picks_until_next_turn(seat, final - 1, TEAMS, ROUNDS) == 0
    assert picks_until_next_turn(seat, final, TEAMS, ROUNDS) is None
    assert picks_until_next_turn(seat, TOTAL_PICKS, TEAMS, ROUNDS) is None


# --- range errors -------------------------------------------------------------------


@pytest.mark.parametrize("seat", [0, -1, 11, 999])
def test_a_seat_outside_one_through_teams_raises_everywhere(seat: int) -> None:
    with pytest.raises(DraftRangeError):
        pick_number(1, seat, TEAMS)
    with pytest.raises(DraftRangeError):
        seat_picks(seat, TEAMS, ROUNDS)
    with pytest.raises(DraftRangeError):
        next_pick_for_seat(seat, 0, TEAMS, ROUNDS)
    with pytest.raises(DraftRangeError):
        picks_until_next_turn(seat, 0, TEAMS, ROUNDS)


@pytest.mark.parametrize("pick", [0, -1, -160])
def test_round_and_seat_rejects_a_pick_below_one(pick: int) -> None:
    with pytest.raises(DraftRangeError):
        round_and_seat(pick, TEAMS)


@pytest.mark.parametrize("round_", [0, -1])
def test_pick_number_rejects_a_round_below_one(round_: int) -> None:
    with pytest.raises(DraftRangeError):
        pick_number(round_, 1, TEAMS)


@pytest.mark.parametrize("picks_made", [-1, -160])
def test_a_negative_picks_made_raises(picks_made: int) -> None:
    with pytest.raises(DraftRangeError):
        next_pick_for_seat(1, picks_made, TEAMS, ROUNDS)
    with pytest.raises(DraftRangeError):
        picks_until_next_turn(1, picks_made, TEAMS, ROUNDS)


@pytest.mark.parametrize("picks_made", [161, 200])
def test_more_picks_made_than_the_draft_contains_raises(picks_made: int) -> None:
    """Pick 161 does not exist in a 160-pick draft; claiming it happened is a bad state."""
    with pytest.raises(DraftRangeError):
        next_pick_for_seat(1, picks_made, TEAMS, ROUNDS)
    with pytest.raises(DraftRangeError):
        picks_until_next_turn(1, picks_made, TEAMS, ROUNDS)


def test_the_last_legal_picks_made_is_the_total_and_it_does_not_raise() -> None:
    assert next_pick_for_seat(1, TOTAL_PICKS, TEAMS, ROUNDS) is None


def test_range_errors_name_the_offending_value() -> None:
    with pytest.raises(DraftRangeError, match="11"):
        seat_picks(11, TEAMS, ROUNDS)
    with pytest.raises(DraftRangeError, match="0"):
        round_and_seat(0, TEAMS)


@pytest.mark.parametrize("teams", [0, -1])
def test_a_nonsensical_team_count_raises(teams: int) -> None:
    with pytest.raises(DraftRangeError):
        round_and_seat(1, teams)
    with pytest.raises(DraftRangeError):
        pick_number(1, 1, teams)


@pytest.mark.parametrize("rounds", [0, -1])
def test_a_nonsensical_round_count_raises(rounds: int) -> None:
    with pytest.raises(DraftRangeError):
        seat_picks(1, TEAMS, rounds)


# --- reversal_round (0 for this league; implemented anyway) --------------------------


def test_reversal_round_zero_is_the_default_and_means_plain_snake() -> None:
    for pick in range(1, TOTAL_PICKS + 1):
        assert round_and_seat(pick, TEAMS) == round_and_seat(pick, TEAMS, 0)
    assert seat_picks(1, TEAMS, ROUNDS) == seat_picks(1, TEAMS, ROUNDS, 0)


@pytest.mark.parametrize(
    ("round_", "seat", "expected"),
    [
        # Round 1 ascends and round 2 descends, exactly as in plain snake.
        (1, 1, 1),
        (1, 10, 10),
        (2, 10, 11),
        (2, 1, 20),
        # Round 3 descends again — that is the reversal.
        (3, 10, 21),
        (3, 1, 30),
        # Round 4 ascends, and the alternation resumes from there.
        (4, 1, 31),
        (4, 10, 40),
        (5, 10, 41),
        (5, 1, 50),
        (6, 1, 51),
        (6, 10, 60),
    ],
)
def test_third_round_reversal_repeats_the_descending_order_in_round_three(
    round_: int, seat: int, expected: int
) -> None:
    assert pick_number(round_, seat, TEAMS, reversal_round=3) == expected


@pytest.mark.parametrize(
    ("seat", "expected"),
    [
        (1, (1, 20, 30, 31, 50)),
        (10, (10, 11, 21, 40, 41)),
    ],
)
def test_third_round_reversal_moves_the_double_pick_to_the_other_wing(
    seat: int, expected: tuple[int, ...]
) -> None:
    assert seat_picks(seat, TEAMS, 5, reversal_round=3) == expected


@pytest.mark.parametrize("pick", range(1, TOTAL_PICKS + 1))
def test_the_inverse_property_still_holds_under_third_round_reversal(pick: int) -> None:
    round_, seat = round_and_seat(pick, TEAMS, reversal_round=3)

    assert pick_number(round_, seat, TEAMS, reversal_round=3) == pick


def test_third_round_reversal_still_partitions_the_whole_draft() -> None:
    all_picks = [
        p for seat in range(1, TEAMS + 1) for p in seat_picks(seat, TEAMS, ROUNDS, reversal_round=3)
    ]

    assert sorted(all_picks) == list(range(1, TOTAL_PICKS + 1))


def test_third_round_reversal_matches_the_independently_built_board() -> None:
    expected = board(TEAMS, ROUNDS, reversal_round=3)

    for pick in range(1, TOTAL_PICKS + 1):
        _, seat = round_and_seat(pick, TEAMS, reversal_round=3)
        assert seat == expected[pick - 1], f"pick {pick}"


@pytest.mark.parametrize("seat", range(1, TEAMS + 1))
def test_picks_until_next_turn_counts_intervening_picks_under_reversal(seat: int) -> None:
    seats_by_pick = board(TEAMS, ROUNDS, reversal_round=3)
    mine = [i + 1 for i, s in enumerate(seats_by_pick) if s == seat]

    for picks_made in range(TOTAL_PICKS + 1):
        remaining = [p for p in mine if p > picks_made]
        expected = None if not remaining else remaining[0] - picks_made - 1

        assert (
            picks_until_next_turn(seat, picks_made, TEAMS, ROUNDS, reversal_round=3) == expected
        ), f"seat {seat}, picks_made {picks_made}"


def test_a_reversal_round_of_two_leaves_round_two_ascending() -> None:
    """`reversal_round` flips from that round onward, so round 2 loses its descent."""
    assert pick_number(1, 1, TEAMS, reversal_round=2) == 1
    assert pick_number(2, 1, TEAMS, reversal_round=2) == 11
    assert pick_number(2, 10, TEAMS, reversal_round=2) == 20
