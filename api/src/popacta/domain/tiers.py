"""Tier detection: where the cliff is, so you can see it before you fall off it.

SIGNATURES ONLY — wave 1. See `docs/plan_phase2_decision_engine.md`, decision 9.

**A fixed absolute gap threshold on projected points, computed per position.** Chosen on
measured evidence against FantasyPros' own `TIERS` labels over 768 rows, and the
justification is stability rather than accuracy:

- It scores slightly *worse* on label agreement than Jenks (ARI 0.336 vs 0.392, ceiling
  0.446) and decisively better on stability.
- Under single-player removal it produces **zero** non-local boundary changes — verified
  independently — while Jenks moves boundaries up to 37 positions away and a
  largest-N-gaps rule up to 99. Mid-draft, one pick shifting a tier line 65 positions
  away is what makes a tier display worse than no tier display.

The locality is structural, not luck: removing a player merges two adjacent gaps, so the
only possible change is at that player's own position. Every alternative couples the whole
board through a global statistic, a fixed cluster count, or a bandwidth.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from popacta.domain.positions import Position

__all__ = ["Tier", "TieredBoard", "detect_tiers", "detect_tiers_by_position"]

DEFAULT_THRESHOLD: float = 6.0
"""Gap threshold in season half-PPR points. Frozen constant — see the module notes."""

DEFAULT_MIN_TIER_SIZE: int = 2
"""Collapses runs of singleton tiers at the top of a board into something readable."""


@dataclass(frozen=True, slots=True)
class Tier:
    """One tier, best first. `number` is 1-based; tier 1 is the best."""

    number: int
    player_ids: tuple[str, ...]
    top_value: float
    bottom_value: float
    gap_below: float | None


@dataclass(frozen=True, slots=True)
class TieredBoard:
    """A tiered board for one position, or a deliberately pooled one."""

    position: Position | None
    threshold: float
    min_tier_size: int
    tiers: tuple[Tier, ...]

    def tier_of(self, player_id: str) -> Tier:
        """The tier containing this player. Raises if the id is not on the board."""
        raise NotImplementedError

    def players_until_cliff(self, player_id: str) -> int:
        """How many players remain in this tier at or below him — the number the UI shows."""
        raise NotImplementedError

    def value_of_cliff(self, player_id: str) -> float | None:
        """How large the drop is below this tier; `None` for the last tier."""
        raise NotImplementedError


def detect_tiers(
    values: Mapping[str, float],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    min_tier_size: int = 1,
    position: Position | None = None,
) -> TieredBoard:
    """Break a tier wherever `value[i-1] - value[i] >= threshold`.

    Args:
        values: player id -> value on **one** axis, **available players only**. The caller
            filters against `DraftState.drafted_ids`. Recomputing every pick is the
            intended use and is safe precisely because the estimator is local.
        threshold: an **absolute** gap in the units of `values`, and a **frozen constant**.
            Passing a freshly-derived `k * median(gap)` each pick re-introduces the global
            coupling this whole design exists to avoid.
        min_tier_size: merge tiers smaller than this into the one below.
        position: recorded for display; `None` marks a deliberately pooled board.

    Notes:
        - **Cluster on points, never on rank.** `RK` in the rankings export is a dense
          1..768 sequence, so every gap is exactly 1 — there is no cliff on an axis with
          no gaps. Verified.
        - Points and VORP produce **identical** per-position partitions, because VORP
          differs from points by a per-position constant. Assert this in a test so nobody
          "fixes" it later.
        - Ties (`gap == threshold`) break the tier. `>=`, stated explicitly, so the
          boundary does not flip on float noise.

    Raises:
        ValueError: empty `values`, non-positive `threshold`, or `min_tier_size < 1`.
    """
    raise NotImplementedError


def detect_tiers_by_position(
    values: Mapping[str, float],
    positions: Mapping[str, Position],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    min_tier_size: int = DEFAULT_MIN_TIER_SIZE,
) -> Mapping[Position, TieredBoard]:
    """One board per ranked position. `DEF` and `K` are never tiered.

    **Per position, never pooled.** Pooling cuts the median gap ~4x — four interleaved
    positions fill in exactly the holes you are trying to detect, giving a display that
    never changes and never warns you. Cross-position comparison is the job of the VORP
    ranking axis; the *cliff* is a positional fact.

    Raises:
        InvalidPlayerError: a `player_id` in `values` is missing from `positions`, or its
            position is `DEF`/`K`.
    """
    raise NotImplementedError
