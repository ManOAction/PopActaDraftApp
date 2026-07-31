"""Player positions, and the subset this copilot actually ranks.

Two sets exist on purpose, and the distinction is load-bearing — see decision 1 in
`docs/plan_phase1_domain_core.md`.
"""

from enum import StrEnum
from typing import Final


class Position(StrEnum):
    """Every position Sleeper can send us in a draft pick.

    `DEF` and `K` are included so that another team drafting a defense or a kicker
    parses cleanly. Nine other teams will draft defenses; a model that did not know
    `DEF` existed would raise on their picks and take down draft-night sync.
    """

    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    DEF = "DEF"
    K = "K"


RANKED_POSITIONS: Final[frozenset[Position]] = frozenset(
    {Position.QB, Position.RB, Position.WR, Position.TE}
)
"""Positions this copilot projects, ranks and recommends.

Excludes `DEF` (the strategy is to stream defenses) and `K` (the league has no kicker
slot at all). Excluded positions still parse and still mark a player unavailable when
someone drafts them — they are simply never recommended.
"""

EXCLUDED_POSITIONS: Final[frozenset[Position]] = frozenset(Position) - RANKED_POSITIONS
"""The complement of `RANKED_POSITIONS`: `{DEF, K}`.

Named rather than implied so a future reader can see this was a decision, not an
oversight.
"""
