"""Starting-lineup value, and a player's marginal contribution to it.

See `docs/plan_phase2_decision_engine.md`, decisions 1 and 10.

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
from typing import Final

from popacta.domain.errors import InvalidPlayerError, LeagueConfigError
from popacta.domain.league import SlotInstance
from popacta.domain.players import Player
from popacta.domain.positions import RANKED_POSITIONS, Position

__all__ = ["lineup_value", "marginal_value"]

_MAX_SLOTS: Final[int] = 20
"""Refuse to run the DP on a slot layout it cannot finish.

This league has 9 ranked starter slots, so `2^S` is 512 and the whole DP is ~74k
operations. The bound is here so that a league whose shape changed beyond recognition
fails in a second with a readable message rather than hanging on the clock.
"""


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
    slot_list = tuple(slots)
    floors = _slot_floors(slot_list, replacement)
    _check_roster(roster, replacement)
    return sum(floors) + _best_gain(roster, slot_list, floors)


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
    slot_list = tuple(slots)
    floors = _slot_floors(slot_list, replacement)
    extended = (*roster, player)
    _check_roster(extended, replacement)

    # Subtract the *gain* terms rather than two `lineup_value` results. The all-floors
    # baseline is identical in both, but `(S + a) - (S + b)` is not exactly `a - b` in
    # floating point, and two guarantees depend on exactness: `u(p | {}) == F(p) - r_pos`
    # on an empty roster, and `u >= 0` rather than `u >= -1e-13`.
    #
    # `extended` appends the candidate **last** and `_best_gain` never reorders players,
    # so its first `len(roster)` passes are bit-for-bit the passes below. Each further
    # pass can only take a max against what it already had, so `with_player >= without`
    # holds exactly, not approximately.
    without = _best_gain(roster, slot_list, floors)
    with_player = _best_gain(extended, slot_list, floors)
    return with_player - without


def _slot_floors(
    slots: Sequence[SlotInstance],
    replacement: Mapping[Position, float],
) -> tuple[float, ...]:
    """`floor(s) = max over p in s.eligible of r_p`, one value per slot.

    An unfilled slot contributes this rather than zero — you are not forced to start
    nobody, you will stream someone at replacement level.

    This is also the entire superflex pricing, with no free parameter:
    `floor(SUPER_FLEX) = max(r_QB, r_RB, r_WR, r_TE) = r_QB` is the largest of the four,
    so an RB nets `F - r_RB` in RB or FLEX but only `F - r_QB` in SUPER_FLEX and never
    takes it while the others are free. The premium is derived, not asserted.

    Raises:
        InvalidPlayerError: a slot accepts a position `replacement` has no level for.
            A `DEF` slot lands here, which is the intended outcome — pass
            `config.ranked_starter_slots`, not `config.starter_slots`.
    """
    floors: list[float] = []
    for slot in slots:
        if not slot.eligible:
            raise InvalidPlayerError(
                f"slot {slot.id!r} accepts no positions, so it has no replacement floor"
            )
        missing = sorted(str(p) for p in slot.eligible if p not in replacement)
        if missing:
            raise InvalidPlayerError(
                f"slot {slot.id!r} accepts {missing} but `replacement` has no level for "
                f"them (it covers {sorted(str(p) for p in replacement)}); a missing "
                "replacement level is a data defect, not a zero baseline. Pass "
                "config.ranked_starter_slots if this is the DEF slot"
            )
        floors.append(max(replacement[p] for p in slot.eligible))
    return tuple(floors)


def _check_roster(roster: Sequence[Player], replacement: Mapping[Position, float]) -> None:
    """Reject a roster this module cannot score. Asserted, never assumed.

    A `DEF` or `K` reaching the DP matches no slot, is silently benched, and is counted
    as bench surplus — the Phase 1 `bench`-conflation limitation reappearing as a wrong
    number instead of an error. That is the LEG-4 shape and it must raise.
    """
    for player in roster:
        if player.position not in RANKED_POSITIONS:
            raise InvalidPlayerError(
                f"player {player.player_id!r} ({player.name!r}) has position "
                f"{str(player.position)!r}, which this app does not rank; filter the roster "
                f"through RANKED_POSITIONS ({sorted(str(p) for p in RANKED_POSITIONS)}) "
                "before scoring, or it is counted as bench surplus"
            )
        if player.position not in replacement:
            raise InvalidPlayerError(
                f"no replacement level for position {str(player.position)!r} "
                f"(player {player.player_id!r}); `replacement` covers "
                f"{sorted(str(p) for p in replacement)}"
            )


def _best_gain(
    roster: Sequence[Player],
    slots: Sequence[SlotInstance],
    floors: Sequence[float],
) -> float:
    """The most a roster can add on top of the all-floors baseline. Bitmask DP over slots.

    `W(R) = sum(floors) + _best_gain(...)`, because a player assigned to slot `j` moves it
    from `floor_j` to `max(F, floor_j)` — a gain of `max(0, F - floor_j)`, and never
    negative, so benching a player is always an option the DP can take.

    `dp[mask]` is the best gain from the players seen so far using a *subset* of the slots
    in `mask`. That framing makes `dp` monotone in `mask`, so the answer is `dp[full]` and
    no unreachable sentinel is needed. `O(n * 2^S * S)`; ~74k operations at `S = 9`.

    **Greedy is not a valid substitute here**, even though it is exact for
    `roster.assign_starters`. Slot-dependent floors break the matroid structure. Measured
    on this league's nine ranked slots: greedy-by-value-into-first-eligible-slot is
    suboptimal 0/20000 times in Sleeper's slot order and 11773/20000 times under a
    randomised one, worst shortfall 546.8 points. Sleeper listing `SUPER_FLEX` last is
    received data, not a guarantee.

    Players are processed in the order given and are **never sorted** — `marginal_value`
    relies on that for its exact non-negativity argument.
    """
    n_slots = len(slots)
    if n_slots > _MAX_SLOTS:
        raise LeagueConfigError(
            f"{n_slots} starter slots exceeds the {_MAX_SLOTS}-slot ceiling of the lineup DP; "
            "this league is not the shape the engine was built for"
        )

    full = (1 << n_slots) - 1
    dp = [0.0] * (full + 1)

    for player in roster:
        eligible_mask = 0
        gains = [0.0] * n_slots
        for index, slot in enumerate(slots):
            if slot.accepts(player.position):
                eligible_mask |= 1 << index
                gains[index] = max(0.0, player.points - floors[index])
        if not eligible_mask:
            # No slot takes him, so every dp entry would copy across unchanged.
            continue

        nxt = [0.0] * (full + 1)
        for mask in range(full + 1):
            best = dp[mask]  # this player benched
            for index in range(n_slots):
                bit = 1 << index
                if mask & bit and eligible_mask & bit:
                    candidate = dp[mask ^ bit] + gains[index]
                    if candidate > best:
                        best = candidate
            nxt[mask] = best
        dp = nxt

    return dp[full]
