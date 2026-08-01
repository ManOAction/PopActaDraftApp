"""`domain.scoring` — recomputing fantasy points from raw stats.

The point of this module is that it is a *pure* function of two mappings, so it is tested
exhaustively and without any I/O. The end-to-end agreement with FantasyPros' own `FPTS`
across all 518 players lives in `tests/ingest/test_fantasypros.py`, where the raw stats
come from.
"""

import json
from pathlib import Path

import pytest

from popacta.domain.errors import ImportDataError
from popacta.domain.scoring import fantasy_points

LEAGUE_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sleeper_league.json"


@pytest.fixture(scope="module")
def scoring() -> dict[str, float]:
    """The league's real `scoring_settings`, straight from a captured Sleeper payload.

    Never hand-entered: hardcoding league settings is what broke the 2025 app.
    """
    return json.loads(LEAGUE_FIXTURE.read_text(encoding="utf-8"))["scoring_settings"]


def test_league_scoring_is_half_ppr(scoring: dict[str, float]) -> None:
    """Pin the settings the rest of this suite reasons about."""
    assert scoring["rec"] == 0.5
    assert scoring["pass_yd"] == 0.04
    assert scoring["pass_td"] == 4.0
    assert scoring["pass_int"] == -1.0
    assert scoring["rush_yd"] == 0.1
    assert scoring["rec_yd"] == 0.1
    assert scoring["rush_td"] == scoring["rec_td"] == 6.0
    assert scoring["fum_lost"] == -2.0


def test_hand_computed_quarterback_line(scoring: dict[str, float]) -> None:
    stats = {
        "pass_yd": 4000.0,
        "pass_td": 30.0,
        "pass_int": 10.0,
        "rush_yd": 500.0,
        "rush_td": 5.0,
        "fum_lost": 3.0,
    }
    expected = 4000 * 0.04 + 30 * 4 - 10 * 1 + 500 * 0.1 + 5 * 6 - 3 * 2
    assert fantasy_points(stats, scoring) == pytest.approx(expected)
    assert fantasy_points(stats, scoring) == pytest.approx(344.0)


def test_hand_computed_receiver_line(scoring: dict[str, float]) -> None:
    stats = {"rec": 100.0, "rec_yd": 1200.0, "rec_td": 8.0, "fum_lost": 1.0}
    assert fantasy_points(stats, scoring) == pytest.approx(100 * 0.5 + 120.0 + 48.0 - 2.0)


def test_empty_stat_line_scores_zero(scoring: dict[str, float]) -> None:
    assert fantasy_points({}, scoring) == 0.0


def test_zero_weighted_rule_is_applied_not_skipped(scoring: dict[str, float]) -> None:
    """`fum` is worth 0.0 in this league — a real rule, not a missing one."""
    assert scoring["fum"] == 0.0
    assert fantasy_points({"fum": 12.0}, scoring) == 0.0


def test_unknown_stat_raises_rather_than_being_skipped(scoring: dict[str, float]) -> None:
    """A stat we cannot score is a projection that is quietly too low. Fail loudly."""
    with pytest.raises(ImportDataError) as excinfo:
        fantasy_points({"rec_yd": 100.0, "punt_return_yd": 250.0}, scoring)
    assert "punt_return_yd" in str(excinfo.value)


def test_unknown_stat_raises_even_when_its_value_is_zero(scoring: dict[str, float]) -> None:
    """A zero-valued unknown stat still means the ruleset and the export disagree."""
    with pytest.raises(ImportDataError, match="pass_att"):
        fantasy_points({"pass_att": 0.0}, scoring)


def test_unscored_volume_columns_are_not_in_sleeper_settings(scoring: dict[str, float]) -> None:
    """The reason `ingest.fantasypros.UNSCORED_STATS` exists, asserted at the source."""
    for stat in ("pass_att", "pass_cmp", "rush_att"):
        assert stat not in scoring


def test_a_scoring_change_changes_the_answer(scoring: dict[str, float]) -> None:
    """The whole justification for recomputing instead of reading `FPTS`.

    If the commissioner flips half-PPR to full PPR in mid-August, reading the CSV's
    `FPTS` would silently keep the old rules. Recomputation moves.
    """
    stats = {"rec": 100.0, "rec_yd": 1000.0, "rec_td": 5.0}
    full_ppr = {**scoring, "rec": 1.0}
    assert fantasy_points(stats, full_ppr) - fantasy_points(stats, scoring) == pytest.approx(50.0)


def test_scoring_is_a_pure_function_of_its_arguments(scoring: dict[str, float]) -> None:
    stats = {"rec": 10.0, "rec_yd": 100.0}
    before = dict(stats), dict(scoring)
    fantasy_points(stats, scoring)
    assert (stats, scoring) == before
