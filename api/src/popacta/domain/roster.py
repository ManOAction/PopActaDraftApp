"""Assigning a roster to starter slots, and finding what is still unfilled.

SIGNATURES ONLY — implemented by wave 1, agent B. See `docs/plan_phase1_domain_core.md`.

**This is a maximum bipartite matching problem, and the obvious greedy implementation is
wrong.** Superflex is what makes it so: a QB is eligible for both `QB` and `SUPER_FLEX`,
and an RB for `RB`, `FLEX` and `SUPER_FLEX`, so a player placed carelessly can strand
another player who had fewer options.

The counterexample that must appear verbatim in the tests:

    roster {QB1: QB, RB1: RB}, open slots {SUPER_FLEX, RB}

    greedy in roster order:  RB1 -> SUPER_FLEX, then QB1 fits nothing
                             => reports 1 unfilled slot and 1 unplaced player  (WRONG)
    maximum matching:        QB1 -> SUPER_FLEX, RB1 -> RB
                             => everything filled                              (RIGHT)

Augmenting paths are sufficient — the graph is roughly 16 players by 9 slots, so
Hopcroft-Karp would be overkill.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from popacta.domain.league import SlotInstance
from popacta.domain.positions import Position

__all__ = ["StarterAssignment", "assign_starters"]


@dataclass(frozen=True, slots=True)
class StarterAssignment:
    """The result of fitting a roster into starter slots.

    `filled` maps slot id -> player id. `unfilled` lists the slot instances still open —
    slots, not a per-position count, because `SUPER_FLEX` has no single position and a
    `dict[Position, int]` cannot express the answer. `bench` holds rostered players that
    no starter slot took.
    """

    filled: Mapping[str, str]
    unfilled: tuple[SlotInstance, ...]
    bench: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        """Whether every starter slot has a player."""
        return not self.unfilled


def assign_starters(
    roster: Mapping[str, Position],
    slots: Sequence[SlotInstance],
) -> StarterAssignment:
    """Fit `roster` into `slots`, maximising the number of slots filled.

    Pass `config.ranked_starter_slots` to exclude `DEF` — defenses are streamed, so the
    `DEF` slot must never surface as an unfilled need. Pass `config.starter_slots` when
    you genuinely want the full legal roster shape.

    The result is a *maximum* matching: no other assignment fills more slots. When several
    maximum assignments exist, any one of them is acceptable — callers must not depend on
    which specific player landed in `FLEX` versus `SUPER_FLEX`.

    Args:
        roster: player id -> position, for players on one team's roster.
        slots: the starter slots to fill.

    Returns:
        A `StarterAssignment`. An empty roster yields every slot in `unfilled`.
    """
    raise NotImplementedError
