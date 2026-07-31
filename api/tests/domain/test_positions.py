"""Tests for the position vocabulary.

The point of these is decision 1 in `docs/plan_phase1_domain_core.md`: DEF and K must
parse but never rank. "We don't draft it" is not the same as "it doesn't exist" — nine
other teams draft defenses and Sleeper sends us those picks.
"""

from popacta.domain.positions import EXCLUDED_POSITIONS, RANKED_POSITIONS, Position


def test_every_position_sleeper_can_send_is_parseable() -> None:
    for raw in ("QB", "RB", "WR", "TE", "DEF", "K"):
        assert Position(raw).value == raw


def test_ranked_positions_are_the_four_we_draft() -> None:
    expected = {Position.QB, Position.RB, Position.WR, Position.TE}

    assert expected == RANKED_POSITIONS


def test_defenses_and_kickers_are_excluded_but_still_exist() -> None:
    expected = {Position.DEF, Position.K}

    assert expected == EXCLUDED_POSITIONS
    assert Position.DEF not in RANKED_POSITIONS
    assert Position.K not in RANKED_POSITIONS


def test_the_two_sets_partition_all_positions() -> None:
    union = RANKED_POSITIONS | EXCLUDED_POSITIONS

    assert union == set(Position)
    assert not RANKED_POSITIONS & EXCLUDED_POSITIONS


def test_position_is_a_string_enum() -> None:
    """Lets positions flow into CSV parsing and JSON without conversion noise."""
    assert Position.QB == "QB"
    assert f"{Position.WR}" == "WR"
    assert sorted({Position.TE, Position.QB}) == ["QB", "TE"]
