"""Starting-lineup value, and a player's marginal contribution to it.

SIGNATURES ONLY — wave 1. See `docs/plan_phase2_decision_engine.md`, decisions 1 and 10.

Raw projected points are **not comparable across positions** — half-PPR QBs simply score
more, so a whole-board expectation over raw points returns a QB at every pick. Value is a
player's marginal contribution to *your starting lineup*:

    W(R)     = max over assignments of R into slots of  sum( max(F(assigned), floor(slot)) )
    floor(s) = max over p in s.eligible of r_p          # replacement level, see replacement.py
    u(p|R)   = W(R + {p}) - W(R)

Two consequences worth understanding before implementing:

- **`W` is a maximum, so its value is canonical even when the assignment achieving it is
  not.** `u` is a difference of two canonical maxima. This is why Phase 2 never reads
  `roster.assign_starters().unfilled` for scoring — that value is order-dependent, and
  Phase 1 recorded it as a known limitation. Display may show unfilled slots; nothing
  numeric may depend on them.
- **Superflex is priced with no free parameter.** `floor(SUPER_FLEX) = r_QB` (the highest
  replacement level among its eligible positions) while `floor(RB) = r_RB`, so an RB nets
  less in SUPER_FLEX than in RB or FLEX and never takes it until those are full.
"""

from collections.abc import Mapping, Sequence

from popacta.domain.league import SlotInstance
from popacta.domain.players import Player
from popacta.domain.positions import Position

__all__ = ["lineup_value", "marginal_value"]


def lineup_value(
    roster: Sequence[Player],
    slots: Sequence[SlotInstance],
    replacement: Mapping[Position, float],
) -> float:
    """`W(R)`: the best starting-lineup total this roster can produce.

    An unfilled slot contributes its floor rather than zero — you are not forced to leave
    it empty on draft day, you will stream someone at replacement level.

    **Use a bitmask DP over slots, not greedy.** Slot-dependent floors break the matroid
    structure that makes greedy optimal for `roster.assign_starters`. Measured against an
    exact oracle:

        production slot order   greedy suboptimal      0 / 20000
        randomised slot order   greedy suboptimal  12707 / 20000, worst shortfall 397 pts

    Greedy is exact only because Sleeper happens to list position-specific slots first and
    `SUPER_FLEX` last. **That ordering is received data, not a guarantee** — this is the
    third time this project has found production slot order hiding a greedy bug, so
    correctness must not depend on it. `O(n * 2^S * S)` with `S = 9` is ~74k operations
    against a 3600-second pick timer.

    Args:
        roster: players on one team. **Filter to `RANKED_POSITIONS` before calling** — a
            `DEF` reaching this function would be counted as bench surplus, which is the
            Phase 1 `bench`-conflation limitation. Assert it; do not assume it.
        slots: normally `config.ranked_starter_slots`.
        replacement: `r_pos` per position, from `replacement.py`.

    Raises:
        InvalidPlayerError: a roster entry's position is missing from `replacement`, or is
            an excluded position that should have been filtered out.
    """
    raise NotImplementedError


def marginal_value(
    player: Player,
    roster: Sequence[Player],
    slots: Sequence[SlotInstance],
    replacement: Mapping[Position, float],
) -> float:
    """`u(p|R)`: what adding this player is worth to your starting lineup.

    With an empty roster this reduces to `F(p) - r_pos(p)` — classic VORP with the correct
    baseline — so nothing is lost in round 1.

    Roster need is *inside* this number, not a separate multiplier: a third QB behind two
    better ones scores `u ~ 0` automatically. Applying a further "need" or "scarcity"
    factor on top would double-count, which is exactly how LEG-5 happened.

    Returns:
        `>= 0` always: adding a player can never lower the best achievable lineup.
    """
    raise NotImplementedError
