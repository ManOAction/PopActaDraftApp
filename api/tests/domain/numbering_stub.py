"""A deliberately non-snake `SnakeNumbering`, for unit-testing draft state in isolation.

This lives in the **test tree on purpose**. It was originally declared in
`popacta.domain.draft`, where it was importable from production code with nothing
preventing it being wired into a real `DraftState` — and a mis-wire produces entirely
plausible-looking seats and rosters rather than an error. A deliberately-wrong numbering
scheme has no business shipping beside the real one.

Production always passes the `snake` module itself as `numbering`.
"""

from dataclasses import dataclass

from popacta.domain.errors import DraftRangeError


@dataclass(frozen=True, slots=True)
class _LinearNumbering:
    """Plain ascending order: pick `n` belongs to seat `((n - 1) % teams) + 1`."""

    def round_and_seat(self, pick: int, teams: int, reversal_round: int = 0) -> tuple[int, int]:
        """Round and seat under plain ascending order; `reversal_round` is ignored."""
        del reversal_round  # a linear ordering never reverses
        if pick < 1:
            raise DraftRangeError(f"pick {pick} must be at least 1")
        if teams < 1:
            raise DraftRangeError(f"teams {teams} must be at least 1")
        return ((pick - 1) // teams) + 1, ((pick - 1) % teams) + 1


def linear_numbering() -> _LinearNumbering:
    """A non-snake stub for unit-testing state transitions. Never use in production."""
    return _LinearNumbering()
