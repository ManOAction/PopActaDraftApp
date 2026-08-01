"""The player pool: who exists, what they project, and what the market thinks.

Shared vocabulary for Phase 2 — see `docs/plan_phase2_decision_engine.md`. Every other
Phase 2 module consumes these types, so they are single-authored on purpose.

`DraftState` (Phase 1) holds player *ids* only, deliberately: the domain core needs no
knowledge of who a player is. Phase 2 is where identity, projections and ADP arrive.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from popacta.domain.errors import InvalidPlayerError
from popacta.domain.positions import RANKED_POSITIONS, Position

__all__ = ["AdpEstimate", "Player", "PlayerPool"]


@dataclass(frozen=True, slots=True)
class AdpEstimate:
    """Average draft position and its dispersion — the inputs to survival probability.

    `adp` is on the **same scale as pick numbers**, verified against the superflex export
    (top-160 values run 1.5 to 164.0). `sd` is the standard deviation of that draft
    position, **not** the standard deviation of expert ranks.

    Both fields must come from a **superflex** source. Standard 1QB ADP places elite QBs
    roughly 20 picks too late and makes every QB decision wrong in the same direction.
    """

    adp: float
    sd: float

    def __post_init__(self) -> None:
        """Reject values that would silently produce a wrong probability.

        `sd <= 0` is never a real ADP sample — it means an empty cell, a `'-'`, or a
        parse that produced a string — and it would divide by zero in the survival model.
        Fail here, at import, rather than mid-draft.
        """
        if self.adp <= 0:
            raise InvalidPlayerError(f"adp must be positive, got {self.adp!r}")
        if self.sd <= 0:
            raise InvalidPlayerError(
                f"sd must be positive, got {self.sd!r}; a zero or missing standard "
                "deviation is a data defect, not a confident consensus"
            )


@dataclass(frozen=True, slots=True)
class Player:
    """One draftable player, keyed by the id Sleeper will send during the draft.

    `player_id` must be the **Sleeper** id, not a FantasyPros name — that resolution
    happens once at import (`ingest.matching`) and is then frozen. Re-matching at draft
    time is forbidden; see OPEN-1.
    """

    player_id: str
    name: str
    position: Position
    points: float
    team: str | None = None
    bye_week: int | None = None
    adp: AdpEstimate | None = None

    @property
    def is_ranked(self) -> bool:
        """Whether this app ranks the player at all.

        `DEF` and `K` parse and occupy picks but are never projected or recommended —
        defenses are streamed and the league has no kicker slot.
        """
        return self.position in RANKED_POSITIONS


@dataclass(frozen=True, slots=True)
class PlayerPool:
    """Every player the board knows about, plus the ids it deliberately does not rank.

    `excluded_ids` holds Sleeper ids for `DEF` and `K` — other teams draft defenses, and
    those picks arrive during the draft. Recording them is required (they consume picks
    and shift next-turn maths); ranking them is not. Keeping them here is what lets
    `available()` distinguish "a pick we deliberately ignore" from "a pick we cannot
    explain", which is the difference between a healthy board and a desynchronised one.
    """

    players: Mapping[str, Player]
    excluded_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        """Freeze the mapping and reject a pool that overlaps its own exclusions."""
        overlap = set(self.players) & set(self.excluded_ids)
        if overlap:
            raise InvalidPlayerError(
                f"{len(overlap)} player id(s) are both ranked and excluded: {sorted(overlap)[:5]}"
            )
        object.__setattr__(self, "players", MappingProxyType(dict(self.players)))

    def available(self, drafted_ids: Iterable[str]) -> tuple[Player, ...]:
        """Ranked players still on the board, in pool order.

        This is the one place a desynchronised board becomes visible, so it asserts
        rather than filters: every drafted id must be either a player we know or an id we
        deliberately excluded. An id that is neither means Sleeper sent a pick we cannot
        account for — on draft night that is a player silently still shown as available.

        Raises:
            InvalidPlayerError: a drafted id is neither in the pool nor excluded.
        """
        drafted = frozenset(drafted_ids)
        unknown = drafted - set(self.players) - self.excluded_ids
        if unknown:
            raise InvalidPlayerError(
                f"{len(unknown)} drafted id(s) are neither in the player pool nor a known "
                f"DEF/K exclusion: {sorted(unknown)[:5]}; the board is out of sync with Sleeper"
            )
        return tuple(p for pid, p in self.players.items() if pid not in drafted)

    def ranked(self) -> tuple[Player, ...]:
        """Every player this app ranks, ignoring draft state."""
        return tuple(p for p in self.players.values() if p.is_ranked)

    def by_position(self, position: Position) -> tuple[Player, ...]:
        """Every player at one position, ignoring draft state."""
        return tuple(p for p in self.players.values() if p.position is position)
