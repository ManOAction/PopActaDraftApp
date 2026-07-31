"""Snake draft order and pick arithmetic.

SIGNATURES ONLY — implemented by wave 1, agent A. See `docs/plan_phase1_domain_core.md`.

Everything here is 1-based: seats `1..teams`, rounds `1..rounds`, picks `1..teams*rounds`.
The 2025 app never modelled snake order at all — `total_teams` was used only as
picks-per-round (LEG-3).
"""

__all__ = [
    "next_pick_for_seat",
    "pick_number",
    "picks_until_next_turn",
    "round_and_seat",
    "seat_picks",
]


def pick_number(round_: int, seat: int, teams: int, reversal_round: int = 0) -> int:
    """Overall pick number for a seat in a given round.

    Odd rounds ascend (seat 1 first); even rounds descend. With `reversal_round = r > 0`,
    the direction flips again from round `r` onward — some leagues reverse a second time
    at round 3. This league uses `0`.

    Raises:
        DraftRangeError: `round_` or `seat` outside its valid range.
    """
    raise NotImplementedError


def round_and_seat(pick: int, teams: int, reversal_round: int = 0) -> tuple[int, int]:
    """Inverse of `pick_number`: which round and seat owns this overall pick.

    Raises:
        DraftRangeError: `pick` below 1.
    """
    raise NotImplementedError


def seat_picks(seat: int, teams: int, rounds: int, reversal_round: int = 0) -> tuple[int, ...]:
    """Every overall pick number belonging to `seat`, ascending.

    For a 10-team, 16-round snake: seat 1 gets `(1, 20, 21, 40, ...)` and seat 10 gets
    `(10, 11, 30, 31, ...)` — the back-to-back picks at the turn.

    Raises:
        DraftRangeError: `seat` outside `1..teams`.
    """
    raise NotImplementedError


def next_pick_for_seat(
    seat: int, picks_made: int, teams: int, rounds: int, reversal_round: int = 0
) -> int | None:
    """The seat's next overall pick number after `picks_made` completed picks.

    Returns `None` once the seat has no picks left.

    Raises:
        DraftRangeError: `seat` outside `1..teams`, or `picks_made` negative.
    """
    raise NotImplementedError


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
        DraftRangeError: `seat` outside `1..teams`, or `picks_made` negative.
    """
    raise NotImplementedError
