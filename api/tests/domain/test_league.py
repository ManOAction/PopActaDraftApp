"""Tests for `LeagueConfig`, against the real Sleeper payloads.

These run against committed fixtures rather than invented dicts, because "never invent
league settings" is the rule that the 2025 app broke hardest (LEG-1).
"""

import json
from pathlib import Path
from typing import Any

import pytest

from popacta.domain.league import LeagueConfig, SlotInstance
from popacta.domain.positions import Position

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def sleeper_league() -> dict[str, Any]:
    return json.loads((FIXTURES / "sleeper_league.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sleeper_draft() -> dict[str, Any]:
    return json.loads((FIXTURES / "sleeper_draft.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def config(sleeper_league: dict[str, Any], sleeper_draft: dict[str, Any]) -> LeagueConfig:
    return LeagueConfig.from_sleeper(sleeper_league, sleeper_draft)


def test_structure_matches_the_real_league(config: LeagueConfig) -> None:
    assert config.teams == 10
    assert config.rounds == 16
    assert config.reversal_round == 0
    assert config.total_picks == 160
    assert config.bench_count == 6


def test_rounds_come_from_the_draft_not_the_league(
    config: LeagueConfig, sleeper_league: dict[str, Any]
) -> None:
    """The league payload's `draft_rounds` is stale; reading it truncates the draft.

    This is the trap that motivated `from_sleeper` taking both payloads. If this test ever
    fails because the two agree, the trap is gone — but do not remove the two-payload
    signature on that basis, because agreement is not guaranteed to persist.
    """
    stale = sleeper_league["settings"]["draft_rounds"]
    assert stale == 3, "fixture changed; re-check which field is authoritative"
    assert config.rounds == 16
    assert config.rounds != stale


def test_starter_slots_are_eligibility_sets_not_position_counts(config: LeagueConfig) -> None:
    by_id = {slot.id: slot for slot in config.starter_slots}

    assert [slot.id for slot in config.starter_slots] == [
        "QB.1",
        "RB.1",
        "RB.2",
        "WR.1",
        "WR.2",
        "TE.1",
        "FLEX.1",
        "FLEX.2",
        "SUPER_FLEX.1",
        "DEF.1",
    ]
    assert by_id["FLEX.1"].eligible == {Position.RB, Position.WR, Position.TE}
    assert by_id["SUPER_FLEX.1"].eligible == {
        Position.QB,
        Position.RB,
        Position.WR,
        Position.TE,
    }


def test_superflex_accepts_a_quarterback(config: LeagueConfig) -> None:
    """The single fact the 2025 schema could not express (LEG-1)."""
    superflex = next(s for s in config.starter_slots if s.name == "SUPER_FLEX")
    flex = next(s for s in config.starter_slots if s.name == "FLEX")

    assert superflex.accepts(Position.QB)
    assert not flex.accepts(Position.QB)


def test_def_slot_is_parsed_but_not_ranked(config: LeagueConfig) -> None:
    """Defenses are streamed: DEF must exist on the roster but never be a need."""
    assert any(slot.name == "DEF" for slot in config.starter_slots)
    assert not any(slot.name == "DEF" for slot in config.ranked_starter_slots)
    assert len(config.ranked_starter_slots) == len(config.starter_slots) - 1


def test_excluded_positions_are_def_and_k(config: LeagueConfig) -> None:
    assert config.excluded_positions == {Position.DEF, Position.K}


def test_bench_slots_are_not_starter_slots(config: LeagueConfig) -> None:
    assert not any(slot.name == "BN" for slot in config.starter_slots)
    assert config.bench_count == 6


def test_config_is_immutable(config: LeagueConfig) -> None:
    with pytest.raises(AttributeError):
        config.teams = 12  # type: ignore[misc]


# --- failure modes: bad data must raise, never default -------------------------------


def test_unrecognised_slot_name_raises(sleeper_draft: dict[str, Any]) -> None:
    league = {"roster_positions": ["QB", "WOMBAT", "BN"]}

    with pytest.raises(ValueError, match="WOMBAT"):
        LeagueConfig.from_sleeper(league, sleeper_draft)


def test_a_kicker_slot_raises(sleeper_draft: dict[str, Any]) -> None:
    """Kickers are out of scope. If the league adds a K slot, that is a change to notice."""
    league = {"roster_positions": ["QB", "K", "BN"]}

    with pytest.raises(ValueError, match="K slot"):
        LeagueConfig.from_sleeper(league, sleeper_draft)


def test_missing_roster_positions_raises(sleeper_draft: dict[str, Any]) -> None:
    with pytest.raises(KeyError):
        LeagueConfig.from_sleeper({}, sleeper_draft)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("teams", 1, "teams"),
        ("rounds", 0, "rounds"),
        ("reversal_round", 99, "reversal_round"),
    ],
)
def test_structural_values_out_of_range_raise(
    sleeper_league: dict[str, Any],
    sleeper_draft: dict[str, Any],
    field: str,
    value: int,
    match: str,
) -> None:
    draft = {**sleeper_draft, "settings": {**sleeper_draft["settings"], field: value}}

    with pytest.raises(ValueError, match=match):
        LeagueConfig.from_sleeper(sleeper_league, draft)


def test_repeated_slot_names_get_distinct_ids() -> None:
    """`RB` twice must become two assignable slots, not one slot with a count of 2."""
    config = LeagueConfig.from_sleeper(
        {"roster_positions": ["RB", "RB", "RB", "BN"]},
        {"type": "snake", "settings": {"teams": 10, "rounds": 16, "reversal_round": 0}},
    )

    assert [slot.id for slot in config.starter_slots] == ["RB.1", "RB.2", "RB.3"]
    assert config.bench_count == 1


def test_slot_instance_accepts_only_eligible_positions() -> None:
    slot = SlotInstance(id="FLEX.1", name="FLEX", eligible=frozenset({Position.RB, Position.WR}))

    assert slot.accepts(Position.RB)
    assert not slot.accepts(Position.QB)
