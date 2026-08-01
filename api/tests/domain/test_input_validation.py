"""Regression tests for defects found by the adversarial verification pass (2026-07-31).

Every finding in that pass was the same shape: **the domain silently absorbed bad or
changed input and produced a plausible wrong answer** rather than raising. No arithmetic
was wrong. That is precisely the LEG-4 failure mode — the 2025 app defaulted a failed bye
week parse to `0` and displayed "Bye: 0" for 527 players all season.

These tests are grouped here rather than scattered into the per-module files because they
share an origin and a rationale: "fail loudly at import time, never silently at draft
time" is the project's central rule, and each of these was a hole in it.
"""

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from popacta.domain import snake
from popacta.domain.draft import DraftState
from popacta.domain.errors import (
    DraftError,
    DraftRangeError,
    InvalidPlayerError,
    LeagueConfigError,
    NoSuchPickError,
)
from popacta.domain.league import LeagueConfig
from popacta.domain.positions import Position
from popacta.domain.roster import assign_starters

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


# --- the draft must actually be a snake ------------------------------------------------


@pytest.mark.parametrize("draft_type", ["auction", "linear", "", None])
def test_a_non_snake_draft_is_refused(
    sleeper_league: dict[str, Any], sleeper_draft: dict[str, Any], draft_type: object
) -> None:
    """Every seat, roster and survival estimate in this app assumes snake order.

    An auction or linear draft used to build a config identically and be entirely wrong,
    with nothing raising anywhere.
    """
    draft = {**sleeper_draft, "type": draft_type}

    with pytest.raises(LeagueConfigError, match="snake"):
        LeagueConfig.from_sleeper(sleeper_league, draft)


def test_a_missing_draft_type_raises(
    sleeper_league: dict[str, Any], sleeper_draft: dict[str, Any]
) -> None:
    draft = {key: value for key, value in sleeper_draft.items() if key != "type"}

    with pytest.raises(KeyError):
        LeagueConfig.from_sleeper(sleeper_league, draft)


def test_the_fixture_really_is_a_snake_draft(sleeper_draft: dict[str, Any]) -> None:
    """Guards the tests above from passing vacuously if the fixture ever changes."""
    assert sleeper_draft["type"] == "snake"


# --- no defaulting of values that must be present --------------------------------------


def test_a_missing_reversal_round_raises_rather_than_defaulting_to_zero(
    sleeper_league: dict[str, Any], sleeper_draft: dict[str, Any]
) -> None:
    """Was `.get("reversal_round", 0)` — a direct violation of api/CLAUDE.md.

    If third-round reversal were ever enabled and the key renamed or absent, rounds 3-16
    would have been drafted against a board that never existed.
    """
    settings = {k: v for k, v in sleeper_draft["settings"].items() if k != "reversal_round"}
    draft = {**sleeper_draft, "settings": settings}

    with pytest.raises(KeyError):
        LeagueConfig.from_sleeper(sleeper_league, draft)


def test_payloads_disagreeing_about_team_count_raises(
    sleeper_league: dict[str, Any], sleeper_draft: dict[str, Any]
) -> None:
    """Cross-checking the two payloads is the stated reason `from_sleeper` takes both.

    Previously `draft.settings.teams = 12` silently produced a 192-pick draft while
    `league.total_rosters` still said 10.
    """
    draft = {**sleeper_draft, "settings": {**sleeper_draft["settings"], "teams": 12}}

    with pytest.raises(LeagueConfigError, match="refusing to guess"):
        LeagueConfig.from_sleeper(sleeper_league, draft)


def test_agreeing_payloads_are_accepted(config: LeagueConfig) -> None:
    assert config.teams == 10


# --- snake rejects a reversal_round that could never apply -----------------------------


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda rr: snake.pick_number(2, 1, 10, rr), id="pick_number"),
        pytest.param(lambda rr: snake.round_and_seat(11, 10, rr), id="round_and_seat"),
        pytest.param(lambda rr: snake.seat_picks(1, 10, 16, rr), id="seat_picks"),
        pytest.param(lambda rr: snake.next_pick_for_seat(1, 0, 10, 16, rr), id="next_pick"),
        pytest.param(
            lambda rr: snake.picks_until_next_turn(1, 0, 10, 16, rr), id="picks_until_next_turn"
        ),
    ],
)
def test_a_negative_reversal_round_raises(call: Any) -> None:
    """`_descends` used to treat a negative value as plain snake and carry on silently."""
    with pytest.raises(DraftRangeError, match="reversal_round"):
        call(-5)


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda rr: snake.seat_picks(1, 10, 3, rr), id="seat_picks"),
        pytest.param(lambda rr: snake.next_pick_for_seat(1, 0, 10, 3, rr), id="next_pick"),
    ],
)
def test_a_reversal_round_past_the_last_round_raises(call: Any) -> None:
    """`seat_picks(1, 10, 3, 99)` used to return plain snake order without complaint."""
    with pytest.raises(DraftRangeError, match="past the last round"):
        call(99)


def test_a_valid_reversal_round_still_works() -> None:
    """The guard must not break real third-round reversal."""
    assert snake.seat_picks(1, 10, 4, 3) == (1, 20, 30, 31)


# --- roster: an unknown position must not be silently benched --------------------------


@pytest.mark.parametrize("bad_position", ["DST", "D/ST", "PK", "", "qb"])
def test_an_unknown_position_raises_rather_than_benching(
    config: LeagueConfig, bad_position: str
) -> None:
    """The LEG-4 shape: a wrong roster-needs answer instead of a crash.

    `assign_starters({"X1": "DST"}, ...)` used to return nine unfilled slots, one benched
    player, and no error — so a FantasyPros `DST` string reaching this layer in Phase 4
    would quietly understate what the roster covers.
    """
    with pytest.raises(InvalidPlayerError, match="X1"):
        assign_starters({"X1": bad_position}, config.ranked_starter_slots)  # type: ignore[dict-item]


def test_a_raw_position_string_is_still_accepted(config: LeagueConfig) -> None:
    """`Position` is a `StrEnum`, so "QB" is a legitimate value — only junk is refused."""
    result = assign_starters({"X1": "QB"}, config.ranked_starter_slots)  # type: ignore[dict-item]

    assert result.filled == {"QB.1": "X1"}


def test_duplicate_slot_ids_raise_inside_the_shared_hierarchy(config: LeagueConfig) -> None:
    slot = config.ranked_starter_slots[0]

    with pytest.raises(LeagueConfigError, match="duplicate slot ids"):
        assign_starters({}, [slot, slot])


# --- immutability ----------------------------------------------------------------------


def test_filled_cannot_be_mutated_after_the_fact(config: LeagueConfig) -> None:
    """Decision 4 is immutability; `filled` was a live dict on a frozen dataclass."""
    result = assign_starters({"QB1": Position.QB}, config.ranked_starter_slots)

    assert isinstance(result.filled, MappingProxyType)
    with pytest.raises(TypeError):
        result.filled["QB.1"] = "TAMPERED"  # type: ignore[index]
    with pytest.raises(TypeError):
        result.filled["NOT_A_SLOT"] = "X"  # type: ignore[index]


# --- draft state rejects junk ----------------------------------------------------------


@pytest.mark.parametrize("bad_id", [None, 0, 1, "", (), 3.5])
def test_recording_a_non_player_raises(config: LeagueConfig, bad_id: object) -> None:
    """`record(None)` used to put a `Pick(player_id=None)` on the board."""
    state = DraftState(config=config, numbering=snake)

    with pytest.raises(InvalidPlayerError):
        state.record(bad_id)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_pick", [True, False, 2.5, "1", None])
def test_undoing_with_a_non_integer_raises_a_domain_error(
    config: LeagueConfig, bad_pick: object
) -> None:
    """`undo(True)` silently undid pick 1; `undo(2.5)` raised a bare slice `TypeError`."""
    state = DraftState(config=config, numbering=snake).record("P001").record("P002")

    with pytest.raises(NoSuchPickError):
        state.undo(bad_pick)  # type: ignore[arg-type]

    assert state.picks_made == 2, "a rejected undo must not mutate state"


# --- everything domain-level is catchable as DraftError --------------------------------


def test_config_and_player_errors_are_draft_errors(
    sleeper_league: dict[str, Any], sleeper_draft: dict[str, Any], config: LeagueConfig
) -> None:
    """`errors.py` promises one hierarchy; these two seams used to escape it."""
    with pytest.raises(DraftError):
        LeagueConfig.from_sleeper(sleeper_league, {**sleeper_draft, "type": "auction"})

    with pytest.raises(DraftError):
        assign_starters({"X1": "DST"}, config.ranked_starter_slots)  # type: ignore[dict-item]


def test_config_errors_are_still_value_errors(
    sleeper_league: dict[str, Any], sleeper_draft: dict[str, Any]
) -> None:
    """Existing `except ValueError` handlers must keep working."""
    with pytest.raises(ValueError, match="expected 'snake'"):
        LeagueConfig.from_sleeper(sleeper_league, {**sleeper_draft, "type": "auction"})
