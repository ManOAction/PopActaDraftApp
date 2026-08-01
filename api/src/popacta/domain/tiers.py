"""Tier detection: where the cliff is, so you can see it before you fall off it.

See `docs/plan_phase2_decision_engine.md`, decision 9.

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
from itertools import pairwise
from types import MappingProxyType

from popacta.domain.errors import InvalidPlayerError
from popacta.domain.positions import RANKED_POSITIONS, Position

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
        for tier in self.tiers:
            if player_id in tier.player_ids:
                return tier
        raise InvalidPlayerError(
            f"{player_id!r} is not on the {self.position or 'pooled'} tier board "
            f"({sum(len(t.player_ids) for t in self.tiers)} players); "
            "he is drafted, at another position, or the board is stale"
        )

    def players_until_cliff(self, player_id: str) -> int:
        """How many players remain in this tier at or below him — the number the UI shows."""
        tier = self.tier_of(player_id)
        return len(tier.player_ids) - tier.player_ids.index(player_id)

    def value_of_cliff(self, player_id: str) -> float | None:
        """How large the drop is below this tier; `None` for the last tier."""
        return self.tier_of(player_id).gap_below


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
    if not values:
        raise ValueError(
            "detect_tiers needs at least one player; got an empty `values` mapping "
            f"(position={position!r}) — an empty board is a caller bug, not a zero-tier board"
        )
    if threshold <= 0:
        raise ValueError(
            f"threshold must be positive, got {threshold!r}; a zero or negative gap "
            "threshold puts every player in his own tier"
        )
    if min_tier_size < 1:
        raise ValueError(f"min_tier_size must be at least 1, got {min_tier_size!r}")

    # Best first. The id is the tie-break so the partition is deterministic when two
    # players project identically — otherwise the display reorders itself between picks.
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))

    # The whole algorithm: cut wherever the gap to the next player reaches the threshold.
    # `>=` is deliberate — a gap of exactly `threshold` breaks the tier, so the boundary
    # does not flip on float noise.
    runs: list[list[tuple[str, float]]] = [[ordered[0]]]
    for previous, current in pairwise(ordered):
        if previous[1] - current[1] >= threshold:
            runs.append([current])
        else:
            runs[-1].append(current)

    grouped = _merge_small_runs(runs, min_tier_size)

    tiers: list[Tier] = []
    for number, run in enumerate(grouped, start=1):
        below = grouped[number] if number < len(grouped) else None
        tiers.append(
            Tier(
                number=number,
                player_ids=tuple(pid for pid, _ in run),
                top_value=run[0][1],
                bottom_value=run[-1][1],
                gap_below=None if below is None else run[-1][1] - below[0][1],
            )
        )

    return TieredBoard(
        position=position,
        threshold=threshold,
        min_tier_size=min_tier_size,
        tiers=tuple(tiers),
    )


def _merge_small_runs(
    runs: list[list[tuple[str, float]]], min_tier_size: int
) -> list[list[tuple[str, float]]]:
    """Absorb runs shorter than `min_tier_size` into the tier below, best first.

    A run of singleton tiers at the top of a board is true but unreadable — "tier 1: Josh
    Allen, tier 2: Lamar Jackson, tier 3: Jayden Daniels" tells you nothing a ranked list
    did not. Accumulating downward keeps the cut that survives at a real gap.

    The trailing remnant has no tier below it, so it merges upward instead; that is the
    only direction available and it is what keeps the partition a partition.

    **This pass is where the locality guarantee gets an asterisk.** The gap rule itself is
    perfectly local — measured zero non-local boundary changes over every single-player
    removal on the real board, at every threshold. This is a downward-accumulating scan, so
    removing a player can change which runs get absorbed further down. Measured cost on the
    pinned projections at `t=6.0, min_tier_size=2`: 3-10% of removals perturb something,
    never further than 7 positions away — against 37 for Jenks and 99 for largest-N-gaps.
    Bounded and near, therefore acceptable; not zero, and `min_tier_size=1` is the setting
    that is. See `test_locality_is_not_a_property_of_the_min_tier_size_merge_pass`.
    """
    merged: list[list[tuple[str, float]]] = []
    pending: list[tuple[str, float]] = []
    for run in runs:
        pending.extend(run)
        if len(pending) >= min_tier_size:
            merged.append(pending)
            pending = []
    if pending:
        if merged:
            merged[-1].extend(pending)
        else:
            merged.append(pending)
    return merged


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
    by_position: dict[Position, dict[str, float]] = {}
    for player_id, value in values.items():
        if player_id not in positions:
            raise InvalidPlayerError(
                f"no position for player id {player_id!r}; it is in `values` but not in "
                "`positions`, so the board cannot say which cliff he is near"
            )
        position = positions[player_id]
        if position not in RANKED_POSITIONS:
            raise InvalidPlayerError(
                f"player id {player_id!r} is a {position}; DEF and K are never tiered — "
                "defenses are streamed and the league has no kicker slot"
            )
        by_position.setdefault(position, {})[player_id] = value

    return MappingProxyType(
        {
            position: detect_tiers(
                group,
                threshold=threshold,
                min_tier_size=min_tier_size,
                position=position,
            )
            for position, group in by_position.items()
        }
    )
