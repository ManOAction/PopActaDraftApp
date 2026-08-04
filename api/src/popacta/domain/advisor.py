"""The recommendation: who should I take?

The assembly point, single-authored. This is where
double-counting would creep in. See `docs/plan_phase2_decision_engine.md`, decisions 3-7
and 11.

    B(p)    = E[ max over q in A\\{p} of  u(q | R + {p}) * survives(q) ]
    Plan(p) = u(p | R) + B(p)
    cost_of_passing(p) = max_p' Plan(p') - Plan(p)          # the number displayed

`Plan(p)` is expected starting-lineup points across your next two picks.

> **The baseline is ADDED, not subtracted.** The `VONA` formula this replaces subtracted it
> and ranked backwards — it recommended the player you should *not* take. `F(p) - baseline`
> and `F(p) + baseline` share both terms and differ only in sign, so they rank oppositely
> whenever the baseline varies more than the projection does, which is most of the draft.
> The counterexample and arithmetic are in `docs/FeatureDescription_PickAdvisor.md`.

`B(p)` excludes `p` — he is on your roster in that branch — and is computed against
`R + {p}`, which is what makes taking a player degrade his own fallback value. That is the
roadmap's "best player still likely available at your next turn", correctly signed.

**Each signal enters exactly once.** Points via `F`; positional scarcity via `r_pos` into
the slot floors of `u`; roster need via slot occupancy inside `W(R)`; survival *only* as
the weights inside `B(p)`. Tier, positional run and bye collisions are **labels**, never
terms. Applying survival again as a multiplier on the final score would count it twice —
that is LEG-5's mistake in a new costume.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from popacta.domain.errors import InvalidPlayerError
from popacta.domain.league import SlotInstance
from popacta.domain.lineup import marginal_value
from popacta.domain.players import Player
from popacta.domain.positions import Position

__all__ = ["Recommendation", "recommend"]


@dataclass(frozen=True, slots=True)
class Recommendation:
    """One candidate, with every term the UI needs to narrate the number.

    The screen must be able to say, from these fields alone and with no post-hoc gloss:

        De'Von Achane, RB — 259.5 proj. Fills your RB2 slot: +134 over the RB you could
        still get late. 33% to last until pick 37 (13 picks away). Take him → likely at
        37: +118. Plan 253. Taking Derrick Henry instead costs you 2.6.

    Every number there is a term in the formula. That is the design constraint, not a
    presentation preference: this is a slow draft and legibility of the reasoning is the
    whole point.
    """

    player: Player
    marginal_value: float
    next_turn_baseline: float
    plan: float
    cost_of_passing: float
    survival: float | None
    slot_filled: str | None


def recommend(
    available: Sequence[Player],
    roster: Sequence[Player],
    slots: Sequence[SlotInstance],
    replacement: Mapping[Position, float],
    *,
    picks_until_turn: int | None = None,
    top_n: int = 40,
) -> tuple[Recommendation, ...]:
    """Rank the board, best first.

    **Degraded mode is what runs today.** `survival()` is blocked on BLK-1 (no `Std Dev`
    source), so `picks_until_turn` is currently always `None` in practice, `B(p)` is `0`,
    and `Plan(p)` collapses to `u(p | R)` — classic VORP against the correct replacement
    level. That is a genuinely useful board, not a stub: it is strictly better than
    anything the 2025 app produced, and it exercises every module except survival.

    `cost_of_passing` remains meaningful in this mode — it is the gap to the best
    alternative, which is exactly the question "what do I give up by not taking him".

    Args:
        available: ranked players still on the board, from `PlayerPool.available()`.
        roster: your players, **already filtered to `RANKED_POSITIONS`**. A `DEF` reaching
            `lineup` raises, which is the intended guard, not something to work around.
        slots: normally `config.ranked_starter_slots`.
        replacement: `r_pos`, from `replacement.replacement_levels`.
        picks_until_turn: `k`. `None` at your final pick **and** whenever survival is
            unavailable. Both mean the same thing here: an empty window has expectation
            zero, so no branch is needed.
        top_n: how many rows to return. The UI shows a board, not 488 rows.

    Raises:
        InvalidPlayerError: a player appears in both `available` and `roster`.
    """
    rostered = {p.player_id for p in roster}
    overlap = sorted(rostered & {p.player_id for p in available})
    if overlap:
        raise InvalidPlayerError(
            f"{len(overlap)} player(s) are both available and on the roster: {overlap[:5]}; "
            "the board is out of sync with the draft state"
        )

    # `B(p)` is zero without survival probability, so `Plan(p) == u(p | R)`. When BLK-1
    # lands this is the single place the baseline gets added — see decision 3.
    scored = [(player, marginal_value(player, roster, slots, replacement)) for player in available]
    scored.sort(key=lambda pair: (-pair[1], pair[0].name))

    best = scored[0][1] if scored else 0.0
    return tuple(
        Recommendation(
            player=player,
            marginal_value=value,
            next_turn_baseline=0.0,
            plan=value,
            cost_of_passing=best - value,
            survival=None,
            slot_filled=None,
        )
        for player, value in scored[:top_n]
    )
