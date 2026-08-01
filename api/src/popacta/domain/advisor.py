"""The recommendation: who should I take?

SIGNATURES ONLY — **wave 2, single-authored.** This is the assembly point, and it is where
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

from collections.abc import Sequence
from dataclasses import dataclass

from popacta.domain.players import Player

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
    picks_made: int,
    picks_until_turn: int | None,
    *,
    top_n: int = 40,
) -> tuple[Recommendation, ...]:
    """Rank the board, best first.

    Args:
        picks_until_turn: `k`, from `snake.picks_until_next_turn(seat, picks_made + 1, …)`.
            `None` at your final pick.

    Behaviour that must not be special-cased away:
        - **`picks_until_turn is None`** (final pick): `B(p) = 0`, so `Plan(p) = u(p | R)`.
          "An empty window has expectation zero" is the whole rule — no branch needed.
        - **`k == 0`** (at the turn, picking back-to-back): every survival is exactly 1.0
          and the 2-ply model is indifferent between your two picks, which is correct but
          useless. Extend one ply using `snake.picks_until_nth_turn(..., n=2)`.
        - **No ADP available** (BLK-1): fall back to ranking on `u(p | R)` alone — classic
          VORP with the correct replacement level. Label it in the UI. It is a genuinely
          useful board, not a stub, and it exercises everything except the survival path.

    Raises:
        InvalidPlayerError: a player in `available` is already in `roster`.

    Note:
        Assert `|sum(1 - s) - k| <= 0.15 * k` over the available pool and **fail loudly**.
        The expected number of players taken in the window must equal `k` by construction,
        so this is the cheapest available detector of a miscalibrated `sd` or a stale
        export. Synthetic data already runs 2-9% hot.
    """
    raise NotImplementedError
