"""Draft state: an ordered record of every pick, with safe undo.

SIGNATURES ONLY — implemented by wave 1, agent C. See `docs/plan_phase1_domain_core.md`.

The central design choice, and the direct fix for LEG-3: **pick numbers are derived from
position in `player_ids`, never stored.** The 2025 app assigned
`max(actual_pick_number) + 1`, so undoing a mid-draft pick left a permanent hole in the
sequence. Here a hole is unrepresentable rather than merely avoided.

State covers **all ten teams**, not just yours — Phase 2's VORP baseline needs to know who
is globally gone. Your roster is derived from your seat.
"""

from dataclasses import dataclass, field
from typing import Protocol, Self

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
            DuplicatePickError: the player is already off the board.
            DraftCompleteError: every pick has already been made.
        """
        raise NotImplementedError

    def undo(self, pick_number: int) -> Self:
        """Return new state with pick `pick_number` removed.

        Accepts **any** existing pick, not only the last — LEG-3 is about correcting a
        mis-recorded pick mid-draft. Because numbering is derived, later picks shift down
        and their seats recompute automatically: the pick simply never happened.

        Raises:
            NoSuchPickError: no pick with that number has been made.
        """
        raise NotImplementedError

    def picks(self) -> tuple[Pick, ...]:
        """Every pick made, as derived views, ascending by pick number."""
        raise NotImplementedError

    def roster_for_seat(self, seat: int) -> tuple[str, ...]:
        """Player IDs taken by `seat`, in pick order.

        Raises:
            DraftRangeError: `seat` outside `1..config.teams`.
        """
        raise NotImplementedError

    @property
    def drafted_ids(self) -> frozenset[str]:
        """Every player already off the board, across all teams."""
        raise NotImplementedError

    @property
    def picks_made(self) -> int:
        """How many picks have been recorded."""
        raise NotImplementedError

    @property
    def next_pick_number(self) -> int | None:
        """The overall number of the next pick, or `None` when the draft is complete."""
        raise NotImplementedError

    @property
    def seat_on_the_clock(self) -> int | None:
        """Which seat picks next, or `None` when the draft is complete."""
        raise NotImplementedError


def linear_numbering() -> SnakeNumbering:
    """A non-snake stub: pick `n` belongs to seat `((n - 1) % teams) + 1`, always ascending.

    For unit-testing state transitions without depending on the real snake arithmetic.
    Never use in production paths.
    """
    raise NotImplementedError
