"""FantasyPros -> Sleeper id resolution (OPEN-1).

The numbers asserted here were measured against a live 12,204-row Sleeper dump before the
module was specified. They are reproduced against a **trimmed fixture** —
`api/tests/fixtures/sleeper_players_subset.json` — because 14 MB is not committable and a
live fetch would make the counts non-deterministic on a machine with no network.

The subset is built so the fixture cannot flatter the code: it keeps *every* Sleeper row
sharing a normalized name with any FantasyPros row, so the same-name collisions the
tie-break ladder exists to resolve (`Frank Gore` father and son, three `Kyle Williams`)
survive into it. Run `python api/tests/ingest/test_matching.py <dump.json>` to rebuild.
"""

import csv
import json
import re
from pathlib import Path

import pytest

from popacta.domain.errors import ImportDataError
from popacta.ingest import matching
from popacta.ingest.matching import MANUAL_OVERRIDES, normalize_name, resolve_players

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data" / "fantasypros"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sleeper_players_subset.json"

RANKINGS_CSV = DATA_DIR / "FantasyPros_2026_Draft_OP_Rankings.csv"
QB_CSV = DATA_DIR / "FantasyPros_Fantasy_Football_Projections_QB.csv"
FLX_CSV = DATA_DIR / "FantasyPros_Fantasy_Football_Projections_FLX.csv"


# --------------------------------------------------------------------------------------
# FantasyPros source rows
#
# Read directly here rather than through ingest/fantasypros.py: this module's contract is
# {name: (team, position)}, and depending on a sibling parser would make a failure in it
# look like a failure in matching.
# --------------------------------------------------------------------------------------


def _rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.reader(handle) if row and row[0].strip()][1:]


def _bare_position(value: str) -> str:
    """`RB1` -> `RB`. FantasyPros embeds positional rank in the POS column."""
    return re.sub(r"\d+$", "", value.strip())


def _rankings_names() -> dict[str, tuple[str | None, str]]:
    return {
        row[2].strip(): (row[3].strip() or None, _bare_position(row[4]))
        for row in _rows(RANKINGS_CSV)
    }


def _projection_names() -> dict[str, tuple[str | None, str]]:
    names = {row[0].strip(): (row[1].strip() or None, "QB") for row in _rows(QB_CSV)}
    names.update(
        {row[0].strip(): (row[1].strip() or None, _bare_position(row[2])) for row in _rows(FLX_CSV)}
    )
    return names


@pytest.fixture(scope="module")
def rankings() -> dict[str, tuple[str | None, str]]:
    return _rankings_names()


@pytest.fixture(scope="module")
def projections() -> dict[str, tuple[str | None, str]]:
    return _projection_names()


def _write_dump(tmp_path: Path, rows: dict[str, dict[str, object]]) -> Path:
    path = tmp_path / "dump.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def _player(player_id: str, full_name: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "player_id": player_id,
        "full_name": full_name,
        "position": "RB",
        "fantasy_positions": ["RB"],
        "team": None,
        "active": True,
        "search_rank": None,
    }
    row.update(overrides)
    return row


# --------------------------------------------------------------------------------------
# normalize_name
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Patrick Mahomes II", "patrickmahomes"),
        ("James Cook III", "jamescook"),
        ("Kenneth Walker III", "kennethwalker"),
        ("Frank Gore Jr.", "frankgore"),
        ("Odell Beckham Jr", "odellbeckham"),
        ("Marvin Harrison Sr.", "marvinharrison"),
        ("Michael Penix IV", "michaelpenix"),
        ("Roman Wilson V", "romanwilson"),
    ],
)
def test_normalize_strips_all_six_suffixes(name, expected):
    assert normalize_name(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ja'Marr Chase", "jamarrchase"),  # apostrophe
        ("Amon-Ra St. Brown", "amonrastbrown"),  # hyphen and a dotted abbreviation
        ("A.J. Brown", "ajbrown"),  # dotted initials
        ("DK Metcalf", "dkmetcalf"),  # undotted initials
        ("D.J. Moore", "djmoore"),
        ("Nikola Jokić", "nikolajokic"),  # accent
        ("José Añez", "joseanez"),  # multiple accents
        ("  Bijan   Robinson  ", "bijanrobinson"),  # stray whitespace
    ],
)
def test_normalize_handles_punctuation_initials_and_accents(name, expected):
    assert normalize_name(name) == expected


def test_normalize_never_pops_the_only_token():
    """A one-token name that *is* a suffix must survive — popping it yields an empty key,
    and an empty key would collide with every other empty key."""
    for suffix in ("Jr", "Sr", "II", "III", "IV", "V"):
        assert normalize_name(suffix) == suffix.lower()


def test_normalize_pops_stacked_suffixes():
    assert normalize_name("Someone Jr III") == "someone"


def test_normalize_matches_sleeper_search_full_name_on_suffixless_rows():
    """Verified across all 12,204 live rows: `search_full_name == normalize(full_name)`."""
    dump = json.loads(FIXTURE.read_bytes())
    checked = 0
    for row in dump.values():
        full_name, search = row.get("full_name"), row.get("search_full_name")
        if not full_name or not search:
            continue
        if normalize_name(full_name) != re.sub(r"[^a-z0-9]", "", full_name.lower()):
            continue  # a suffix row: normalize deliberately goes further than Sleeper
        assert normalize_name(full_name) == search, full_name
        checked += 1
    assert checked > 500


# --------------------------------------------------------------------------------------
# The measured match rates
# --------------------------------------------------------------------------------------


def test_rankings_resolve_at_the_measured_rate(rankings):
    assert len(rankings) == 768
    resolved = resolve_players(rankings, FIXTURE)
    # 763 = 768 rows - the 5 MANUAL_OVERRIDES entries pinned to None (absent from Sleeper).
    assert len(resolved) == 763
    assert len(resolved) / len(rankings) >= 0.99


def test_projections_resolve_at_the_measured_rate(projections):
    assert len(projections) == 518
    resolved = resolve_players(projections, FIXTURE)
    assert len(resolved) == 518
    assert len(resolved) / len(projections) >= 0.99


def test_resolution_is_injective_across_both_sources(rankings, projections):
    """Two names resolving to one id would mask one player's board entry with another's.
    `resolve_players` raises on it; this asserts it never has to."""
    combined = dict(rankings)
    combined.update(projections)
    resolved = resolve_players(combined, FIXTURE)
    assert len(set(resolved.values())) == len(resolved)


def test_no_ambiguity_survives_the_ladder_on_real_data(rankings, projections):
    """Ambiguity raises, so a clean return *is* the assertion — but state it, because it is
    the wrong-player-silently case OPEN-1 exists for."""
    resolve_players(rankings, FIXTURE)
    resolve_players(projections, FIXTURE)


# --------------------------------------------------------------------------------------
# MANUAL_OVERRIDES is exactly the unresolved set
# --------------------------------------------------------------------------------------


def test_unresolved_set_is_exactly_manual_overrides(monkeypatch, rankings, projections):
    """With the override table emptied, the names that fail must be precisely its keys.
    An extra failure means Sleeper's dump changed underneath us; a missing one means an
    override has gone stale and is masking a name that now resolves on its own."""
    monkeypatch.setattr(matching, "MANUAL_OVERRIDES", {})
    combined = dict(rankings)
    combined.update(projections)

    with pytest.raises(ImportDataError) as excinfo:
        resolve_players(combined, FIXTURE)

    message = str(excinfo.value)
    assert message.startswith(f"{len(MANUAL_OVERRIDES)} FantasyPros name(s) matched no Sleeper")
    for name in MANUAL_OVERRIDES:
        assert repr(name) in message


def test_override_ids_all_exist_in_the_dump(rankings):
    resolved = resolve_players(rankings, FIXTURE)
    for name, player_id in MANUAL_OVERRIDES.items():
        if player_id is None:
            assert name not in resolved, f"{name} is pinned to None but was resolved"
        else:
            assert resolved[name] == player_id


def test_nicknames_resolve_to_their_real_players(rankings):
    resolved = resolve_players(rankings, FIXTURE)
    dump = json.loads(FIXTURE.read_bytes())
    assert dump[resolved["Hollywood Brown"]]["full_name"] == "Marquise Brown"
    assert dump[resolved["Bam Knight"]]["full_name"] == "Zonovan Knight"
    assert dump[resolved["Chip Trayanum"]]["full_name"] == "DeaMonte Trayanum"


def test_a_stale_override_id_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(matching, "MANUAL_OVERRIDES", {"Hollywood Brown": "no-such-id"})
    dump = _write_dump(tmp_path, {"5848": _player("5848", "Marquise Brown", position="WR")})
    with pytest.raises(ImportDataError, match="no-such-id"):
        resolve_players({"Hollywood Brown": ("PHI", "WR")}, dump)


# --------------------------------------------------------------------------------------
# Frank Gore — the silent-wrong-player case
# --------------------------------------------------------------------------------------


def test_frank_gore_jr_resolves_to_the_son(rankings):
    resolved = resolve_players(rankings, FIXTURE)
    dump = json.loads(FIXTURE.read_bytes())
    son = dump[resolved["Frank Gore Jr."]]
    assert son["player_id"] == "11573"
    assert son["team"] == "BUF"


def test_both_frank_gores_are_in_the_fixture():
    """The father must be present, or the collision this guards against cannot occur and
    the test above proves nothing."""
    dump = json.loads(FIXTURE.read_bytes())
    gores = [r for r in dump.values() if r.get("full_name") == "Frank Gore"]
    assert {r["player_id"] for r in gores} == {"232", "11573"}
    assert all(r["active"] for r in gores)
    assert {r["position"] for r in gores} == {"RB"}  # position cannot separate them


def test_position_only_tie_break_is_insufficient_for_frank_gore(monkeypatch, rankings):
    """Truncate the ladder to its first rung and the father/son pair becomes ambiguous.
    This is the teeth check for the ambiguity guard, kept as a regression test."""

    def position_only(candidates, team, position):
        del team  # the rung under test is deliberately the only one applied
        matched = [
            row
            for row in candidates
            if row.get("position") == position or position in (row.get("fantasy_positions") or [])
        ]
        return matched or candidates

    monkeypatch.setattr(matching, "_tie_break", position_only)
    with pytest.raises(ImportDataError) as excinfo:
        resolve_players(rankings, FIXTURE)

    message = str(excinfo.value)
    assert "still ambiguous after the full tie-break ladder" in message
    assert "'Frank Gore Jr.'" in message
    assert "232=" in message  # the father
    assert "11573=" in message  # the son


@pytest.mark.parametrize(
    ("name", "player_id"),
    [
        ("Josh Allen", "4984"),  # vs. an inactive G
        ("Lamar Jackson", "4881"),  # vs. a CB
        ("Justin Jefferson", "6794"),  # vs. a CB
        ("DeVonta Smith", "7525"),  # vs. "Devonta Smith", a CB — case differs, key does not
        ("Michael Carter", "7607"),  # vs. an active CB on another team
        ("Kyle Williams", "12547"),  # four Sleeper rows share this key, three of them WR
    ],
)
def test_duplicate_names_resolve_to_the_fantasy_relevant_player(rankings, name, player_id):
    assert resolve_players(rankings, FIXTURE)[name] == player_id


# --------------------------------------------------------------------------------------
# Team is a tie-break, never a match requirement
# --------------------------------------------------------------------------------------


def test_a_stale_fantasypros_team_still_matches(tmp_path):
    """12 real players have been released since the export. Requiring team drops all 12."""
    dump = _write_dump(tmp_path, {"1": _player("1", "Released Guy", team=None)})
    assert resolve_players({"Released Guy": ("BUF", "RB")}, dump) == {"Released Guy": "1"}


def test_jac_is_aliased_to_jax(tmp_path):
    dump = _write_dump(
        tmp_path,
        {
            "1": _player("1", "Same Name", team="JAX"),
            "2": _player("2", "Same Name", team="TEN"),
        },
    )
    assert resolve_players({"Same Name": ("JAC", "RB")}, dump) == {"Same Name": "1"}


def test_fa_is_treated_as_no_team_not_as_a_team_code(tmp_path):
    """`FA` must skip the team rung entirely and fall through to has-a-team, rather than
    being compared literally against a Sleeper `team` value."""
    dump = _write_dump(
        tmp_path,
        {
            "1": _player("1", "Same Name", team=None),
            "2": _player("2", "Same Name", team="TEN"),
        },
    )
    assert resolve_players({"Same Name": ("FA", "RB")}, dump) == {"Same Name": "2"}


def test_ladder_falls_through_to_active_then_search_rank(tmp_path):
    dump = _write_dump(
        tmp_path,
        {
            "1": _player("1", "Same Name", team="BUF", active=False, search_rank=1),
            "2": _player("2", "Same Name", team="BUF", active=True, search_rank=500),
            "3": _player("3", "Same Name", team="BUF", active=True, search_rank=40),
        },
    )
    assert resolve_players({"Same Name": ("BUF", "RB")}, dump) == {"Same Name": "3"}


def test_missing_search_rank_sorts_last(tmp_path):
    dump = _write_dump(
        tmp_path,
        {
            "1": _player("1", "Same Name", team="BUF", search_rank=None),
            "2": _player("2", "Same Name", team="BUF", search_rank=900),
        },
    )
    assert resolve_players({"Same Name": ("BUF", "RB")}, dump) == {"Same Name": "2"}


# --------------------------------------------------------------------------------------
# The three failure modes
# --------------------------------------------------------------------------------------


def test_indistinguishable_candidates_raise_rather_than_guess(tmp_path):
    dump = _write_dump(
        tmp_path,
        {
            "1": _player("1", "Same Name", team="BUF"),
            "2": _player("2", "Same Name", team="BUF"),
        },
    )
    with pytest.raises(ImportDataError, match="still ambiguous"):
        resolve_players({"Same Name": ("BUF", "RB")}, dump)


def test_two_names_resolving_to_one_id_raise(tmp_path):
    dump = _write_dump(tmp_path, {"1": _player("1", "Same Name", team="BUF")})
    with pytest.raises(ImportDataError, match="claimed by more than one FantasyPros name"):
        resolve_players({"Same Name": ("BUF", "RB"), "Same Name Jr.": ("BUF", "RB")}, dump)


def test_an_unknown_name_raises_and_names_the_row(tmp_path):
    dump = _write_dump(tmp_path, {"1": _player("1", "Someone Else")})
    with pytest.raises(ImportDataError) as excinfo:
        resolve_players({"Nobody At All": ("BUF", "RB")}, dump)
    assert "'Nobody At All'" in str(excinfo.value)
    assert "BUF" in str(excinfo.value)


def test_every_failure_is_reported_not_just_the_first(tmp_path):
    dump = _write_dump(tmp_path, {"1": _player("1", "Someone Else")})
    with pytest.raises(ImportDataError) as excinfo:
        resolve_players({"Ghost One": (None, "RB"), "Ghost Two": (None, "WR")}, dump)
    assert "'Ghost One'" in str(excinfo.value)
    assert "'Ghost Two'" in str(excinfo.value)


def test_an_empty_dump_raises(tmp_path):
    dump = _write_dump(tmp_path, {})
    with pytest.raises(ImportDataError, match="non-empty"):
        resolve_players({}, dump)


# --------------------------------------------------------------------------------------
# DEF — by id, before any name path
# --------------------------------------------------------------------------------------


def test_def_rows_carry_no_full_name_at_all():
    """Not `None` — the key is absent. `row["full_name"].lower()` would raise
    `AttributeError` mid-draft; `row.get("full_name")` on a dict without the key is the
    only safe read."""
    dump = json.loads(FIXTURE.read_bytes())
    defenses = [r for r in dump.values() if r.get("position") == "DEF"]
    assert len(defenses) == 32
    assert all("full_name" not in r for r in defenses)
    assert all("search_full_name" not in r for r in defenses)


def test_a_def_pick_resolves_by_team_abbreviation():
    """~10 of 160 live picks are defenses. Sleeper's `player_id` *is* the abbreviation."""
    assert resolve_players({"SF": ("SF", "DEF")}, FIXTURE) == {"SF": "SF"}


def test_a_def_pick_resolves_by_spelled_out_club_name():
    assert resolve_players({"San Francisco 49ers": (None, "DEF")}, FIXTURE) == {
        "San Francisco 49ers": "SF"
    }


def test_every_defense_resolves():
    dump = json.loads(FIXTURE.read_bytes())
    ids = [pid for pid, row in dump.items() if row.get("position") == "DEF"]
    resolved = resolve_players({pid: (pid, "DEF") for pid in ids}, FIXTURE)
    assert resolved == {pid: pid for pid in ids}


def test_an_unknown_defense_raises(tmp_path):
    dump = _write_dump(tmp_path, {"SF": {"player_id": "SF", "position": "DEF", "team": "SF"}})
    with pytest.raises(ImportDataError, match="no Sleeper defense"):
        resolve_players({"XX": ("XX", "DEF")}, dump)


def test_defenses_mixed_with_named_players_do_not_break_the_index(rankings):
    """The whole-file resolution runs over a fixture that contains all 32 DEF rows, so the
    name index must skip them without ever touching a missing `full_name`."""
    combined = dict(rankings)
    combined["SF"] = ("SF", "DEF")
    resolved = resolve_players(combined, FIXTURE)
    assert resolved["SF"] == "SF"


# --------------------------------------------------------------------------------------
# Fixture regeneration — never runs under pytest
# --------------------------------------------------------------------------------------


def _regenerate_fixture(dump_path: Path, out_path: Path = FIXTURE) -> None:
    """Trim a full Sleeper dump to the rows these tests need.

    Usage: `python api/tests/ingest/test_matching.py path/to/sleeper_players.json`
    Fetch a fresh dump from https://api.sleeper.app/v1/players/nfl (14 MB).
    """
    dump = json.loads(dump_path.read_bytes())
    wanted_keys = {normalize_name(n) for n in (_rankings_names() | _projection_names())}
    pinned = {pid for pid in MANUAL_OVERRIDES.values() if pid is not None}

    subset: dict[str, dict[str, object]] = {}
    for player_id, row in dump.items():
        full_name = row.get("full_name")
        keep = (
            row.get("position") == "DEF"
            or player_id in pinned
            or (full_name and normalize_name(full_name) in wanted_keys)
        )
        if keep:
            subset[player_id] = {key: row[key] for key in matching._FIXTURE_FIELDS if key in row}

    out_path.write_text(json.dumps(subset, indent=0, sort_keys=True), encoding="utf-8")
    print(
        f"wrote {len(subset)} of {len(dump)} rows to {out_path} ({out_path.stat().st_size} bytes)"
    )


if __name__ == "__main__":
    import sys

    _regenerate_fixture(Path(sys.argv[1]))
