"""Snake draft order and pick arithmetic.

Everything here is 1-based: seats `1..teams`, rounds `1..rounds`, picks `1..teams*rounds`.
The 2025 app never modelled snake order at all — `total_teams` was used only as
picks-per-round (LEG-3).
"""

from popacta.domain.errors import DraftRangeError

__all__ = [
    "next_pick_for_seat",
    "pick_number",
    "picks_until_next_turn",
    "round_and_seat",
    "seat_picks",
]


def _check_teams(teams: int) -> None:
    if teams < 1:
        raise DraftRangeError(f"teams must be at least 1, got {teams}")


def _check_rounds(rounds: int) -> None:
    if rounds < 1:
        raise DraftRangeError(f"rounds must be at least 1, got {rounds}")


def _check_seat(seat: int, teams: int) -> None:
    if not 1 <= seat <= teams:
        raise DraftRangeError(f"seat {seat} outside 1..{teams}")


def _check_reversal_round(reversal_round: int, rounds: int | None = None) -> None:
    """Reject a `reversal_round` that could never take effect.

    `_descends` would quietly treat a negative value, or one past the final round, as
    plain snake — a config typo would then produce a wrong board with nothing raising.
    These functions are public and Phase 2 calls them directly, so the check cannot live
    only in `LeagueConfig`. `rounds` is omitted where the caller does not know it.
    """
    if reversal_round < 0:
        raise DraftRangeError(f"reversal_round {reversal_round} is negative")
    if rounds is not None and reversal_round > rounds:
        raise DraftRangeError(
            f"reversal_round {reversal_round} is past the last round ({rounds}); "
            "it would never take effect"
        )


def _descends(round_: int, reversal_round: int) -> bool:
    """True when `round_` runs from seat `teams` down to seat 1.

    Plain snake: even rounds descend. A `reversal_round` of `r > 0` flips the direction
    again from round `r` onward, so with `r = 3` rounds 2 and 3 both descend.
    """
    descending = round_ % 2 == 0
    if reversal_round > 0 and round_ >= reversal_round:
        descending = not descending
    return descending


def pick_number(round_: int, seat: int, teams: int, reversal_round: int = 0) -> int:
    """Overall pick number for a seat in a given round.

    Odd rounds ascend (seat 1 first); even rounds descend. With `reversal_round = r > 0`,
    the direction flips again from round `r` onward — some leagues reverse a second time
    at round 3. This league uses `0`.

    Raises:
        DraftRangeError: `round_` or `seat` outside its valid range.
    """
    _check_teams(teams)
    _check_reversal_round(reversal_round)
    if round_ < 1:
        raise DraftRangeError(f"round {round_} below 1")
    _check_seat(seat, teams)

    offset = teams - seat + 1 if _descends(round_, reversal_round) else seat
    return (round_ - 1) * teams + offset


def round_and_seat(pick: int, teams: int, reversal_round: int = 0) -> tuple[int, int]:
    """Inverse of `pick_number`: which round and seat owns this overall pick.

    Raises:
        DraftRangeError: `pick` below 1.
    """
    _check_teams(teams)
    _check_reversal_round(reversal_round)
    if pick < 1:
        raise DraftRangeError(f"pick {pick} below 1")

    # The one 0-based conversion in this module: `pick - 1` indexes the board.
    round_ = (pick - 1) // teams + 1
    offset = (pick - 1) % teams + 1
    seat = teams - offset + 1 if _descends(round_, reversal_round) else offset
    return round_, seat


def seat_picks(seat: int, teams: int, rounds: int, reversal_round: int = 0) -> tuple[int, ...]:
    """Every overall pick number belonging to `seat`, ascending.

    For a 10-team, 16-round snake: seat 1 gets `(1, 20, 21, 40, ...)` and seat 10 gets
    `(10, 11, 30, 31, ...)` — the back-to-back picks at the turn.

    Raises:
        DraftRangeError: `seat` outside `1..teams`.
    """
    _check_teams(teams)
    _check_rounds(rounds)
    _check_reversal_round(reversal_round, rounds)
    _check_seat(seat, teams)

    return tuple(
        pick_number(round_, seat, teams, reversal_round) for round_ in range(1, rounds + 1)
    )


def next_pick_for_seat(
    seat: int, picks_made: int, teams: int, rounds: int, reversal_round: int = 0
) -> int | None:
    """The seat's next overall pick number after `picks_made` completed picks.

    Returns `None` once the seat has no picks left.

    Raises:
        DraftRangeError: `seat` outside `1..teams`, or `picks_made` negative, or
            `picks_made` greater than the `teams * rounds` picks the draft contains.
    """
    _check_teams(teams)
    _check_rounds(rounds)
    _check_reversal_round(reversal_round, rounds)
    _check_seat(seat, teams)
    if picks_made < 0:
        raise DraftRangeError(f"picks_made {picks_made} is negative")
    total_picks = teams * rounds
    if picks_made > total_picks:
        raise DraftRangeError(
            f"picks_made {picks_made} exceeds the {total_picks} picks in a "
            f"{teams}-team, {rounds}-round draft"
        )

    for pick in seat_picks(seat, teams, rounds, reversal_round):
        if pick > picks_made:
            return pick
    return None


def picks_until_next_turn(
    seat: int, picks_made: int, teams: int, rounds: int, reversal_round: int = 0
) -> int | None:
    """How many picks OTHER teams make before `seat` picks again. The keystone metric.

    Counts intervening picks, **not** the pick-number delta — see decision 3 in the plan.
    Seat 4 picks at 4 and 17: the delta is 13, but 12 players come off the board in
    between, and survival probability asks for the latter.

    Returns `0` when the next pick belongs to this seat, which happens at the turn where
    a seat picks back-to-back (seat 10 picks at 10 and 11). Returns `None` when the seat
    has no picks left.

    Equivalent to `next_pick_for_seat(...) - picks_made - 1`.

    Raises:
        DraftRangeError: `seat` outside `1..teams`, or `picks_made` negative, or
            `picks_made` greater than the `teams * rounds` picks the draft contains.
    """
    next_mine = next_pick_for_seat(seat, picks_made, teams, rounds, reversal_round)
    if next_mine is None:
        return None
    return next_mine - picks_made - 1
