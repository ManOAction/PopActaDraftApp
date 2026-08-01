"""Draft state: an ordered record of every pick, with safe undo.

See `docs/plan_phase1_domain_core.md` for the locked contract behind this module.

The central design choice, and the direct fix for LEG-3: **pick numbers are derived from
position in `player_ids`, never stored.** The 2025 app assigned
`max(actual_pick_number) + 1`, so undoing a mid-draft pick left a permanent hole in the
sequence. Here a hole is unrepresentable rather than merely avoided.

State covers **all ten teams**, not just yours — Phase 2's VORP baseline needs to know who
is globally gone. Your roster is derived from your seat.
"""

from dataclasses import dataclass, field, replace
from typing import Protocol, Self

from popacta.domain.errors import (
    DraftCompleteError,
    DraftRangeError,
    DuplicatePickError,
    InvalidPlayerError,
    NoSuchPickError,
)
from popacta.domain.league import LeagueConfig

__all__ = ["DraftState", "Pick", "SnakeNumbering"]


class SnakeNumbering(Protocol):
    """The slice of `snake` that `DraftState` depends on.

    Injected rather than imported so `draft.py` and `snake.py` can be written
    concurrently, and so state logic is unit-testable against a trivial linear stub
    instead of the real snake arithmetic.
    """

    def round_and_seat(self, pick: int, teams: int, reversal_round: int = 0) -> tuple[int, int]:
        """Which round and seat owns this overall pick."""
        ...


@dataclass(frozen=True, slots=True)
class Pick:
    """A derived view of one pick. Never stored — always computed from position."""

    pick_number: int
    round: int
    seat: int
    player_id: str


@dataclass(frozen=True, slots=True)
class DraftState:
    """Immutable draft state. Every operation returns a new instance.

    `player_ids[i]` is the player taken at pick number `i + 1`.
    """

    config: LeagueConfig
    numbering: SnakeNumbering
    player_ids: tuple[str, ...] = field(default=())

    def record(self, player_id: str) -> Self:
        """Return new state with `player_id` taken at the next pick.

        Raises:
            InvalidPlayerError: `player_id` is not a non-empty string.
            DuplicatePickError: the player is already off the board.
            DraftCompleteError: every pick has already been made.
        """
        # Without this, `record(None)` produces a Pick whose player_id is None and the
        # board quietly contains a player that does not exist.
        if not isinstance(player_id, str) or not player_id:
            raise InvalidPlayerError(f"player_id must be a non-empty string, got {player_id!r}")

        if player_id in self.drafted_ids:
            # index + 1 is the pick number, because numbering is positional.
            taken_at = self.player_ids.index(player_id) + 1
            raise DuplicatePickError(f"player {player_id!r} was already taken at pick {taken_at}")

        if self.picks_made >= self.config.total_picks:
            raise DraftCompleteError(
                f"cannot record {player_id!r}: all {self.config.total_picks} picks "
                f"({self.config.teams} teams x {self.config.rounds} rounds) have been made"
            )

        return replace(self, player_ids=(*self.player_ids, player_id))

    def undo(self, pick_number: int) -> Self:
        """Return new state with pick `pick_number` removed.

        Accepts **any** existing pick, not only the last — LEG-3 is about correcting a
        mis-recorded pick mid-draft. Because numbering is derived, later picks shift down
        and their seats recompute automatically: the pick simply never happened.

        Raises:
            NoSuchPickError: `pick_number` is not an integer, or no pick with that number
                has been made.
        """
        # `bool` is an `int`, so `undo(True)` would otherwise silently undo pick 1, and a
        # float would reach the slice below and raise a bare TypeError instead.
        if not isinstance(pick_number, int) or isinstance(pick_number, bool):
            raise NoSuchPickError(f"pick_number must be an int, got {pick_number!r}")

        if not 1 <= pick_number <= self.picks_made:
            raise NoSuchPickError(
                f"no pick {pick_number} to undo; {self.picks_made} picks have been made"
            )

        index = pick_number - 1  # the one conversion between 1-based picks and list indices
        return replace(self, player_ids=self.player_ids[:index] + self.player_ids[index + 1 :])

    def picks(self) -> tuple[Pick, ...]:
        """Every pick made, as derived views, ascending by pick number."""
        return tuple(self._pick_at(index) for index in range(len(self.player_ids)))

    def roster_for_seat(self, seat: int) -> tuple[str, ...]:
        """Player IDs taken by `seat`, in pick order.

        Raises:
            DraftRangeError: `seat` outside `1..config.teams`.
        """
        if not 1 <= seat <= self.config.teams:
            raise DraftRangeError(f"seat {seat} outside 1..{self.config.teams}")

        return tuple(pick.player_id for pick in self.picks() if pick.seat == seat)

    @property
    def drafted_ids(self) -> frozenset[str]:
        """Every player already off the board, across all teams."""
        return frozenset(self.player_ids)

    @property
    def picks_made(self) -> int:
        """How many picks have been recorded."""
        return len(self.player_ids)

    @property
    def next_pick_number(self) -> int | None:
        """The overall number of the next pick, or `None` when the draft is complete."""
        if self.picks_made >= self.config.total_picks:
            return None
        return self.picks_made + 1

    @property
    def seat_on_the_clock(self) -> int | None:
        """Which seat picks next, or `None` when the draft is complete."""
        pick_number = self.next_pick_number
        if pick_number is None:
            return None
        _round, seat = self.numbering.round_and_seat(
            pick_number, self.config.teams, self.config.reversal_round
        )
        return seat

    def _pick_at(self, index: int) -> Pick:
        """Derive the `Pick` view for list index `index` — pick number `index + 1`."""
        pick_number = index + 1
        round_, seat = self.numbering.round_and_seat(
            pick_number, self.config.teams, self.config.reversal_round
        )
        return Pick(
            pick_number=pick_number,
            round=round_,
            seat=seat,
            player_id=self.player_ids[index],
        )
