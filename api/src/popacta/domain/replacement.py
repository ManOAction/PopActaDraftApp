"""Replacement level and positional demand.

See `docs/plan_phase2_decision_engine.md`, decision 2.

Two different demand numbers, for two different jobs. Keep them distinct and label them
in the UI — conflating them is a ~77-point error on every QB.

- **Draft demand** — how many at this position come off the board in the whole draft.
  Answers *"what am I stuck with if I punt this position?"* and sets replacement level.
- **Starter demand** — how many get *started* league-wide. Answers *"how many are
  genuinely startable?"* and drives run detection and the UI sensitivity band.

**This league uses draft demand** (decided 2026-08-01). Measured on real superflex ADP,
**32 QBs go inside the top 160**, so punting QB does not leave you QB21 — a projected
493-attempt starter — it leaves you QB33. Starter demand would produce a board saying
"essentially never draft a QB" in a superflex league, which is an extraordinary claim
against a projection set whose own publisher ranks QBs 1-6.
"""

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

from popacta.domain.errors import ImportDataError
from popacta.domain.league import LeagueConfig
from popacta.domain.players import Player
from popacta.domain.positions import RANKED_POSITIONS, Position

# `_augment` is Kuhn's augmenting-path step, and decision 10 of the Phase 2 plan says to
# reuse it here rather than write a second matching implementation. It stays private to
# `roster` on purpose — this is a sibling module inside the same package, not an external
# caller, and duplicating the recursion is how the two copies drift apart.
from popacta.domain.roster import _augment

__all__ = ["draft_demand", "replacement_levels", "starter_demand"]

_RANKED_ORDER: Final[tuple[Position, ...]] = tuple(p for p in Position if p in RANKED_POSITIONS)
"""`RANKED_POSITIONS` in declaration order, so every result mapping iterates identically.

`RANKED_POSITIONS` is a frozenset; iterating it directly would give a hash-ordered result
that looks stable in one process and different in the next. Every mapping this module
returns is keyed by exactly these four positions — `DEF` and `K` never appear.
"""


def draft_demand(pool: Sequence[Player], config: LeagueConfig) -> Mapping[Position, int]:
    """How many players at each position are taken in `teams * rounds` picks.

    Counted from **superflex ADP** where available, falling back to consensus order.
    Expected on the pinned data: `QB = 32`, from the real market rather than an estimate.

    Raises:
        ImportDataError: a player inside the draftable window has no ADP — that would
            silently understate the position's demand.
    """
    ranked = _ranked_players(pool)

    window_size = config.total_picks
    if len(ranked) < window_size:
        # Fewer ranked players than picks means the pool is truncated. Counting demand
        # over what survived would understate every position and lift every replacement
        # level, so the whole board would read optimistic without anything looking wrong.
        raise ImportDataError(
            f"player pool holds only {len(ranked)} ranked players but the draft makes "
            f"{window_size} picks ({config.teams} teams x {config.rounds} rounds); "
            "the pool is truncated and draft demand would be understated"
        )

    # Stable sort: players carrying ADP first, in ADP order; players without ADP keep
    # their position in `pool`, which is consensus order. That is the documented fallback
    # — but a player who reaches the draftable window on it has no market signal at all,
    # and is rejected below rather than counted or skipped.
    ordered = sorted(ranked, key=lambda p: (p.adp is None, p.adp.adp if p.adp is not None else 0.0))
    window = ordered[:window_size]

    counts = dict.fromkeys(_RANKED_ORDER, 0)
    for index, player in enumerate(window):
        if player.adp is None:
            raise ImportDataError(
                f"player {player.name!r} ({player.player_id}, {player.position}) reaches "
                f"draftable position {index + 1} of {window_size} with no ADP; refusing to "
                "count or skip a player the market has not priced"
            )
        counts[player.position] += 1

    return MappingProxyType(counts)


def starter_demand(pool: Sequence[Player], config: LeagueConfig) -> Mapping[Position, int]:
    """How many players at each position are *started* league-wide.

    The maximum-weight allocation of the whole pool into every team's ranked starter slots
    — `config.ranked_starter_slots` repeated `config.teams` times (9 x 10 = 90 slots).
    "The slot goes to whoever provides most value over their alternative", made exact as a
    single global optimisation with no assumed share and no free parameter.

    **Greedy over raw points is exact here** — uniform floors make this a transversal
    matroid — so `roster._augment` can be reused, verified 0/20000 against an oracle. This
    is *not* true of `lineup.lineup_value`, which has slot-dependent floors; see that
    module.

    Expected on the pinned data: `QB = 20, RB = 31, WR = 29, TE = 10`. All 10 SUPER_FLEX
    slots go to QBs and **the contest is decided by 110 points** (QB20 at 274.5 versus the
    best flex-eligible alternative at 164.0), so "contested share" is 100% QB, robustly.
    Compute it anyway rather than hardcoding — it self-corrects if projections shift, and
    `starter_demand <= draft_demand` is a free consistency check.

    LEG-1 is what this replaces: re-running the allocation against the 2025 app's fudged
    settings gives replacement levels ~30 points wrong for every RB and WR, in a metric
    whose top-15 spread is ~90 points, and modelled 120 starters for a 90-starter league.

    Raises:
        ImportDataError: two players share a `player_id` (the matching is keyed by id, so
            one of them would be silently dropped), or the allocation started more players
            at a position than the market drafts there. The second is the free consistency
            check between the two bases: a position cannot be started more often than it
            comes off the board. It runs whenever draft demand is computable — that is,
            whenever the pool carries ADP for at least `teams * rounds` players.
    """
    ranked = _ranked_players(pool)

    # One slot instance per team per ranked starter slot: 9 x 10 = 90 for this league.
    # `ranked_starter_slots` drops DEF, which is what keeps a streamed defense out of the
    # league-wide allocation and therefore out of every replacement level.
    slots = tuple(config.ranked_starter_slots) * config.teams

    # Descending points, ties keeping pool order. Greedy in this order is *exact* because
    # every slot values a player identically (uniform floors), which makes the startable
    # sets a transversal matroid — verified 0/20000 against a brute-force oracle. That is
    # emphatically not true of `lineup.py`, where each slot floors at its own replacement
    # level; do not carry this shortcut across.
    order = sorted(ranked, key=lambda p: -p.points)

    eligible: dict[str, tuple[int, ...]] = {}
    for player in order:
        if player.player_id in eligible:
            raise ImportDataError(
                f"duplicate player_id {player.player_id!r} in the pool "
                f"({player.name!r}); the starter allocation is keyed by id and would "
                "silently drop one of them"
            )
        eligible[player.player_id] = tuple(
            index for index, slot in enumerate(slots) if slot.accepts(player.position)
        )

    slot_to_player: dict[int, str] = {}
    counts = dict.fromkeys(_RANKED_ORDER, 0)
    for player in order:
        # A successful augmenting path means the matching grew by one, i.e. this player is
        # startable somewhere league-wide once everyone better has been placed. Players
        # already placed may shuffle among their other eligible slots to make room — that
        # shuffle is exactly what a per-position quota cannot express, and is why a QB
        # never has to be assumed into SUPER_FLEX.
        if _augment(player.player_id, eligible, slot_to_player, set()):
            counts[player.position] += 1

    _check_within_draft_demand(counts, pool, config)

    return MappingProxyType(counts)


def replacement_levels(
    pool: Sequence[Player], demand: Mapping[Position, int]
) -> Mapping[Position, float]:
    """`r_pos`: the projected points of the best player you could still get for free.

    `r_pos` = points of the `(demand[pos] + 1)`-th best player at that position. In words:
    the guy you end up starting if you ignore the position entirely.

    Raises:
        ImportDataError: a position has fewer players than `demand + 1`, which means the
            pool is truncated and every downstream number would be quietly optimistic.
    """
    excluded = [position for position in demand if position not in RANKED_POSITIONS]
    if excluded:
        # DEF and K are streamed and unranked. A demand entry for one means the caller
        # built the mapping from something other than this module's two bases, and a
        # replacement level for a position we never recommend would be read as real.
        raise ImportDataError(
            f"demand carries unranked position(s) {sorted(excluded)}; this app ranks "
            f"only {sorted(RANKED_POSITIONS)}"
        )

    ranked = _ranked_players(pool)
    by_position: dict[Position, list[float]] = {position: [] for position in _RANKED_ORDER}
    for player in ranked:
        by_position[player.position].append(player.points)

    levels: dict[Position, float] = {}
    for position in _RANKED_ORDER:
        if position not in demand:
            raise ImportDataError(
                f"no demand given for {position}; replacement level is undefined without "
                f"one, and defaulting it to 0 would make every {position} look free"
            )
        count = demand[position]
        if count < 0:
            raise ImportDataError(f"demand for {position} is negative ({count})")

        points = sorted(by_position[position], reverse=True)
        if len(points) <= count:
            raise ImportDataError(
                f"{position} demand is {count}, so replacement level is the "
                f"{count + 1}th best {position}, but the pool holds only {len(points)}; "
                "the pool is truncated and every downstream value would be optimistic"
            )
        levels[position] = points[count]

    return MappingProxyType(levels)


def _ranked_players(pool: Sequence[Player]) -> tuple[Player, ...]:
    """The pool with `DEF` and `K` removed.

    Every number in this module is positional demand among positions the app ranks. The
    superflex ADP export is offence-only for the same reason, so filtering here is what
    makes the measured draft demand reproduce the plan's.
    """
    return tuple(player for player in pool if player.position in RANKED_POSITIONS)


def _check_within_draft_demand(
    starters: Mapping[Position, int], pool: Sequence[Player], config: LeagueConfig
) -> None:
    """Enforce `starter_demand[pos] <= draft_demand[pos]`.

    A position cannot be started more often league-wide than it comes off the board, so a
    violation means one of the two bases is wrong — and since they set replacement level
    and the sensitivity band respectively, a wrong one is a wrong number on every card.

    The check needs draft demand, which needs ADP on at least `teams * rounds` players.
    Below that threshold `draft_demand` raises by design (a truncated market), so the
    check is skipped rather than turned into a spurious failure of the ADP-free path.
    """
    priced = sum(1 for player in _ranked_players(pool) if player.adp is not None)
    if priced < config.total_picks:
        return

    drafted = draft_demand(pool, config)
    for position, started in starters.items():
        if started > drafted[position]:
            raise ImportDataError(
                f"{position} starter demand {started} exceeds draft demand "
                f"{drafted[position]}; a position cannot be started league-wide more "
                "often than it is drafted, so one of the two bases is wrong"
            )
