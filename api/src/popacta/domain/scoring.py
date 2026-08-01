"""Recomputing fantasy points from raw stats using the league's own scoring settings.

**Recompute rather than read the CSV's `FPTS` column.** Verified 2026-07-31: the league's
offensive scoring is identical to FantasyPros' default Half PPR — recomputation reproduces
their `FPTS` across all 518 players, max deviation 0.62 points, all of it rounding. So this
buys nothing *today*.

It buys everything if the commissioner changes a scoring setting in mid-August. Reading
`FPTS` would silently keep using the old rules; recomputing makes it a non-event. It costs
~20 lines and is a pure function worth unit-testing.

Scoring settings come from Sleeper (`scoring_settings` on the league payload) and are never
hand-entered — hardcoding them is what broke the 2025 app.
"""

from collections.abc import Mapping

from popacta.domain.errors import ImportDataError

__all__ = ["fantasy_points"]


def fantasy_points(stats: Mapping[str, float], scoring: Mapping[str, float]) -> float:
    """Points for one raw stat line under one scoring ruleset.

    Args:
        stats: raw stats keyed by Sleeper's stat names (`pass_yd`, `pass_td`, `rush_yd`,
            `rec`, `fum_lost`, …), as produced by `ingest.fantasypros.RawProjection`.
        scoring: the league's `scoring_settings`, straight from Sleeper. For reference,
            this league: `rec 0.5`, `pass_yd 0.04`, `pass_td 4`, `pass_int -1`,
            `rush_yd`/`rec_yd 0.1`, all TDs 6, `fum_lost -2`.

    Returns:
        Projected season points.

    Raises:
        ImportDataError: a stat key has no corresponding scoring rule. **Do not skip
            unknown keys** — a stat we cannot score is a stat we are silently discarding,
            and this league's DST scoring is genuinely custom, so "unknown" is a real
            signal rather than noise.

    Note:
        DST scoring is points-allowed *tiers*, not a flat per-stat multiplier, and this
        function does not model it. That is fine — defenses are streamed and never ranked
        (BLK-2) — but do not extend this function to DST without revisiting that decision.
    """
    total = 0.0
    for stat, value in stats.items():
        # Not `scoring.get(stat, 0.0)`. A stat with no rule is a stat we would be
        # silently discarding, and a discarded stat is a projection that is quietly too
        # low for every player who accumulates it.
        if stat not in scoring:
            raise ImportDataError(
                f"stat {stat!r} (value {value!r}) has no scoring rule in the league's "
                f"scoring_settings; known rules: {sorted(scoring)}"
            )
        total += value * scoring[stat]
    return total
