"""Assigning a roster to starter slots, and finding what is still unfilled.

See `docs/plan_phase1_domain_core.md`, decision 8.

**This is a maximum bipartite matching problem, and the obvious greedy implementation is
wrong.** Superflex is what makes it so: a QB is eligible for both `QB` and `SUPER_FLEX`,
and an RB for `RB`, `FLEX` and `SUPER_FLEX`, so a player placed carelessly can strand
another player who had fewer options.

The counterexample that must appear verbatim in the tests:

    roster {RB1: RB, QB1: QB}, open slots {SUPER_FLEX, RB}

    greedy, RB1 visited first:  RB1 -> SUPER_FLEX, then QB1 fits nothing
                                => 1 unfilled slot and 1 unplaced player  (WRONG)
    maximum matching:           QB1 -> SUPER_FLEX, RB1 -> RB
                                => everything filled                      (RIGHT)

**The iteration order matters, and it is easy to write a toothless test here.** With the
roster in the order `{QB1, RB1}` instead, player-major greedy happens to reach the right
answer, so a test using that order passes against a broken implementation. Pin the order
that actually strands the QB.

Augmenting paths are sufficient — the graph is roughly 16 players by 9 slots, so
Hopcroft-Karp would be overkill.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from popacta.domain.errors import InvalidPlayerError, LeagueConfigError
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

    Raises:
        LeagueConfigError: two slots share an id. `filled` is keyed by slot id, so
            duplicate ids would silently drop an assignment and under-report what the
            roster covers.
        InvalidPlayerError: a roster entry's position is not a `Position` member. Such a
            player would match no slot and be silently benched, understating what the
            roster covers instead of failing.
    """
    slot_list = tuple(slots)

    ids = [slot.id for slot in slot_list]
    if len(set(ids)) != len(ids):
        duplicates = sorted({slot_id for slot_id in ids if ids.count(slot_id) > 1})
        raise LeagueConfigError(f"duplicate slot ids {duplicates}; slot ids must be unique")

    # A position this module does not recognise would otherwise match no slot, land in
    # `bench`, and silently understate what the roster covers. That is the LEG-4 shape:
    # a wrong answer rather than a crash. A raw "QB" string is accepted (Position is a
    # StrEnum); "DST", "D/ST" or a typo is not.
    for player_id, position in roster.items():
        try:
            Position(position)
        except ValueError as exc:
            raise InvalidPlayerError(
                f"player {player_id!r} has unknown position {position!r}; "
                f"expected one of {sorted(p.value for p in Position)}"
            ) from exc

    # Player -> the slot indices it is eligible for. Indices, not ids, because the
    # matching only ever needs identity and they are cheap to compare.
    eligible: dict[str, tuple[int, ...]] = {
        player_id: tuple(index for index, slot in enumerate(slot_list) if slot.accepts(position))
        for player_id, position in roster.items()
    }

    # Kuhn's algorithm: take each player in turn and look for an augmenting path. If one
    # exists, the players already placed shuffle among their other eligible slots to make
    # room, and the matching grows by exactly one. Greedy placement cannot do that shuffle,
    # which is why it strands a QB whose only remaining home is a SUPER_FLEX an RB took.
    slot_to_player: dict[int, str] = {}
    for player_id in roster:
        _augment(player_id, eligible, slot_to_player, set())

    # Read-only: `StarterAssignment` is frozen, but a plain dict field would still be
    # mutable through the attribute, which decision 4 rules out.
    filled = MappingProxyType(
        {
            slot_list[index].id: slot_to_player[index]
            for index in range(len(slot_list))
            if index in slot_to_player
        }
    )
    unfilled = tuple(slot for index, slot in enumerate(slot_list) if index not in slot_to_player)
    placed = set(slot_to_player.values())
    bench = tuple(player_id for player_id in roster if player_id not in placed)

    return StarterAssignment(filled=filled, unfilled=unfilled, bench=bench)


def _augment(
    player_id: str,
    eligible: Mapping[str, tuple[int, ...]],
    slot_to_player: dict[int, str],
    visited: set[int],
) -> bool:
    """Try to place `player_id`, displacing already-placed players along the way.

    Mutates `slot_to_player` in place when it succeeds. `visited` guards against revisiting
    a slot within one search, which is what makes the recursion terminate.

    Returns:
        Whether an augmenting path was found, i.e. whether the matching grew by one.
    """
    for slot_index in eligible[player_id]:
        if slot_index in visited:
            continue
        visited.add(slot_index)
        occupant = slot_to_player.get(slot_index)
        if occupant is None or _augment(occupant, eligible, slot_to_player, visited):
            slot_to_player[slot_index] = player_id
            return True
    return False
