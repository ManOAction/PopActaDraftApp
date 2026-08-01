"""Replacement level and positional demand.

SIGNATURES ONLY — wave 1. See `docs/plan_phase2_decision_engine.md`, decision 2.

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

from popacta.domain.league import LeagueConfig
from popacta.domain.players import Player
from popacta.domain.positions import Position

__all__ = ["draft_demand", "replacement_levels", "starter_demand"]


def draft_demand(pool: Sequence[Player], config: LeagueConfig) -> Mapping[Position, int]:
    """How many players at each position are taken in `teams * rounds` picks.

    Counted from **superflex ADP** where available, falling back to consensus order.
    Expected on the pinned data: `QB = 32`, from the real market rather than an estimate.

    Raises:
        ImportDataError: a player inside the draftable window has no ADP — that would
            silently understate the position's demand.
    """
    raise NotImplementedError


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
    """
    raise NotImplementedError


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
    raise NotImplementedError
