"""`ingest.fantasypros` — parsed against the committed exports in `data/fantasypros/`.

No network, no mocks: these tests read the same pinned CSVs the app reads. Mocking the
thing we are trying to verify would defeat the point — the failures this module guards
against are all *format* failures.

The load-bearing tests here are:

* `test_recomputed_points_match_the_published_fpts` — the headline. Recomputing from raw
  stats reproduces FantasyPros' own `FPTS` across all 518 players.
* `test_flx_receiving_and_rushing_are_not_swapped` and its cross-file sibling — the
  `(file, column index)` trap. `WR.csv` lists receiving first, `FLX.csv` lists rushing
  first, under the same repeated header names. A name-keyed parser swaps them silently.
  **Note that the swap is invisible to `FPTS`**: rushing and receiving yards are both
  worth 0.1 and both TDs 6, so the points test alone would never catch it. Only comparing
  the stat lines does.
"""

import csv
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from popacta.domain.errors import ImportDataError
from popacta.domain.players import AdpEstimate
from popacta.domain.scoring import fantasy_points
from popacta.ingest import fantasypros
from popacta.ingest.fantasypros import (
    DRAFTABLE_PICKS,
    EM_DASH,
    FLX_COLUMNS,
    QB_COLUMNS,
    UNSCORED_STATS,
    AdpRow,
    RawProjection,
    RawRanking,
    parse_adp,
    parse_adp_rows,
    parse_projections,
    parse_rankings,
)

DATA = Path(__file__).resolve().parents[3] / "data" / "fantasypros"
QB_CSV = DATA / "FantasyPros_Fantasy_Football_Projections_QB.csv"
FLX_CSV = DATA / "FantasyPros_Fantasy_Football_Projections_FLX.csv"
WR_CSV = DATA / "FantasyPros_Fantasy_Football_Projections_WR.csv"
RB_CSV = DATA / "FantasyPros_Fantasy_Football_Projections_RB.csv"
TE_CSV = DATA / "FantasyPros_Fantasy_Football_Projections_TE.csv"
RANKINGS_CSV = DATA / "FantasyPros_2026_Draft_OP_Rankings.csv"
ADP_CSV = DATA / "FantasyPros_2026_Superflex_ADP_Rankings.csv"

# Verified counts, `docs/reference_fantasypros_exports.md`.
QB_ROWS = 82
FLX_ROWS = 436
ALL_PROJECTED = QB_ROWS + FLX_ROWS  # 518
RANKING_ROWS = 768
ADP_ROWS = 278

HALF_PPR: Mapping[str, float] = {
    "pass_yd": 0.04,
    "pass_td": 4.0,
    "pass_int": -1.0,
    "rush_yd": 0.1,
    "rush_td": 6.0,
    "rec": 0.5,
    "rec_yd": 0.1,
    "rec_td": 6.0,
    "fum_lost": -2.0,
}
"""The league's offensive scoring, verified identical to FantasyPros' default Half PPR.

Spelled out here rather than loaded from the Sleeper fixture so that these tests fail on a
*parsing* regression and not on a fixture change; `tests/domain/test_scoring.py` is what
ties these weights back to the real league payload.
"""

# `WR.csv` puts receiving before rushing. `FLX.csv` puts rushing before receiving. Same
# header names in both. This is the layout a name-keyed parser gets wrong.
WR_FILE_COLUMNS = (
    "player",
    "team",
    "rec",
    "rec_yd",
    "rec_td",
    "rush_att",
    "rush_yd",
    "rush_td",
    "fum_lost",
    "fpts",
)
RB_FILE_COLUMNS = (
    "player",
    "team",
    "rush_att",
    "rush_yd",
    "rush_td",
    "rec",
    "rec_yd",
    "rec_td",
    "fum_lost",
    "fpts",
)
TE_FILE_COLUMNS = ("player", "team", "rec", "rec_yd", "rec_td", "fum_lost", "fpts")


def read_projection_file(path: Path, columns: Sequence[str]) -> dict[str, dict[str, float]]:
    """An independent, deliberately dumb positional reader for the per-position files.

    Written out longhand rather than reusing the module under test: its whole job is to be
    a second opinion about which column means what.
    """
    out: dict[str, dict[str, float]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        assert len(row) == len(columns), (path.name, row)
        cells = dict(zip(columns, row, strict=True))
        out[cells["player"].strip()] = {
            key: float(value.replace(",", ""))
            for key, value in cells.items()
            if key not in {"player", "team", "pos"}
        }
    return out


@pytest.fixture(scope="module")
def projections() -> Sequence[RawProjection]:
    return parse_projections(QB_CSV, FLX_CSV)


@pytest.fixture(scope="module")
def rankings() -> Sequence[RawRanking]:
    return parse_rankings(RANKINGS_CSV)


@pytest.fixture(scope="module")
def adp_rows() -> Sequence[AdpRow]:
    return parse_adp_rows(ADP_CSV)


# --------------------------------------------------------------------------------------
# Projections
# --------------------------------------------------------------------------------------


def test_qb_union_flx_is_the_whole_ranked_universe(projections: Sequence[RawProjection]) -> None:
    assert len(projections) == ALL_PROJECTED
    assert len({p.name for p in projections}) == ALL_PROJECTED
    by_position: dict[str, int] = {}
    for projection in projections:
        by_position[projection.position] = by_position.get(projection.position, 0) + 1
    # Note: these are `FLX.csv`'s own labels, and they are not the per-position files'
    # labels. `RB.csv` has 131 rows, three of which (Andrew Beck, Connor Heyward, Riley
    # Nowakowski - fullbacks) `FLX.csv` calls TEs. The union of FLX and QB is the
    # authority here because it is the file pair we import; the discrepancy is why the
    # cross-file stat comparison below matches on name rather than on position.
    assert by_position == {"QB": QB_ROWS, "RB": 128, "WR": 189, "TE": 119}


def test_junk_spacer_and_trailing_rows_are_skipped(projections: Sequence[RawProjection]) -> None:
    """Row 2 of every projections file is `" ","","",""`, and two blank rows trail it.

    If any of them survived, the count above would be wrong and a player would have an
    empty name.
    """
    assert all(projection.name.strip() for projection in projections)
    assert not any(projection.name.strip() == "" for projection in projections)


def test_thousands_separators_inside_quotes_are_parsed(
    projections: Sequence[RawProjection],
) -> None:
    """`"1,381.0"` must become `1381.0`, not `1.0` and not a crash."""
    gibbs = next(p for p in projections if p.name == "Jahmyr Gibbs")
    assert gibbs.stats["rush_yd"] == pytest.approx(1381.0)


def test_recomputed_points_match_the_published_fpts(
    projections: Sequence[RawProjection],
) -> None:
    """The headline test: our arithmetic reproduces FantasyPros' own `FPTS`.

    The residual is rounding — FantasyPros publishes stats to one decimal, so recomputing
    from rounded inputs drifts a couple of tenths. Verified max deviation 0.62 across all
    518 players, with no systematic sign.
    """
    published = {
        **{name: stats["fpts"] for name, stats in read_projection_file(QB_CSV, QB_COLUMNS).items()},
        **{
            name: stats["fpts"]
            for name, stats in read_projection_file(FLX_CSV, FLX_COLUMNS).items()
        },
    }
    assert len(published) == ALL_PROJECTED

    deviations = []
    for projection in projections:
        recomputed = fantasy_points(projection.stats, HALF_PPR)
        deviations.append((abs(recomputed - published[projection.name]), projection.name))

    worst, worst_player = max(deviations)
    assert worst < 0.7, f"{worst_player} deviates by {worst}"
    mean_deviation = sum(d for d, _ in deviations) / len(deviations)
    assert mean_deviation < 0.25


def test_every_parsed_stat_has_a_scoring_rule(projections: Sequence[RawProjection]) -> None:
    """`fantasy_points` raises on an unscored key, so this is the contract that lets the
    headline test above run at all."""
    for projection in projections:
        assert set(projection.stats) <= set(HALF_PPR), projection.name


def test_unscored_volume_columns_are_dropped(projections: Sequence[RawProjection]) -> None:
    """Attempts and completions are parsed (so a malformed cell still fails) then dropped
    by name, because this league's `scoring_settings` has no rule for them."""
    allen = next(p for p in projections if p.name == "Josh Allen")
    assert UNSCORED_STATS.isdisjoint(allen.stats)
    assert allen.stats["pass_yd"] == pytest.approx(3812.7)
    assert set(allen.stats) == {"pass_yd", "pass_td", "pass_int", "rush_yd", "rush_td", "fum_lost"}


# ---- the (file, column index) trap ----------------------------------------------------


def test_flx_receiving_and_rushing_are_not_swapped(projections: Sequence[RawProjection]) -> None:
    """Pinned values for a receiver read out of `FLX.csv`, where rushing comes first.

    Puka Nacua's row in `FLX.csv` is
    `"Puka Nacua","LAR","WR1","13.6","85.0","1.4","117.0","1,539.0","9.0","1.0","281.3"` —
    rushing (13.6 att / 85 yd / 1.4 td) *then* receiving (117 rec / 1539 yd / 9 td).

    A parser keyed on header names reads `YDS` and `TDS` as receiving in both files and
    lands 85.0 in `rec_yd`. It does not crash, and it does not change `FPTS` either, since
    rushing and receiving yards are both worth 0.1. Only this assertion catches it.
    """
    nacua = next(p for p in projections if p.name == "Puka Nacua")
    assert nacua.position == "WR"
    assert nacua.stats["rec"] == pytest.approx(117.0)
    assert nacua.stats["rec_yd"] == pytest.approx(1539.0)
    assert nacua.stats["rec_td"] == pytest.approx(9.0)
    assert nacua.stats["rush_yd"] == pytest.approx(85.0)
    assert nacua.stats["rush_td"] == pytest.approx(1.4)
    # The swap's signature: a WR's receiving yards dwarf his rushing yards.
    assert nacua.stats["rec_yd"] > 10 * nacua.stats["rush_yd"]


SOURCE_DISAGREEMENTS = frozenset({"Connor Heyward"})
"""The one player FantasyPros itself projects differently in `FLX.csv` and `RB.csv`/`TE.csv`.

A fullback, listed as an RB in `RB.csv` and a TE in `FLX.csv`, with different receiving
numbers in each. It is a defect in the source, not in the parser — pinned by name so that a
*new* disagreement fails this test instead of hiding inside a tolerance.
"""


@pytest.mark.parametrize(
    ("per_position_csv", "per_position_columns", "expected_disagreements"),
    [
        (WR_CSV, WR_FILE_COLUMNS, frozenset()),
        (RB_CSV, RB_FILE_COLUMNS, SOURCE_DISAGREEMENTS),
        (TE_CSV, TE_FILE_COLUMNS, SOURCE_DISAGREEMENTS),
    ],
)
def test_flx_stats_agree_with_the_per_position_file(
    projections: Sequence[RawProjection],
    per_position_csv: Path,
    per_position_columns: Sequence[str],
    expected_disagreements: frozenset[str],
) -> None:
    """Cross-file agreement, player by player and stat by stat.

    `WR.csv` is the case that matters, and it is the case with **zero** tolerated
    exceptions: it orders receiving before rushing while `FLX.csv` orders rushing before
    receiving, using the *same* repeated header names. If `FLX.csv` were keyed on those
    names, every one of the 189 WRs would mismatch here.

    Matched on name, not position: three fullbacks are RBs in `RB.csv` and TEs in
    `FLX.csv`, which is a labelling disagreement rather than a stat one.
    """
    reference = read_projection_file(per_position_csv, per_position_columns)
    parsed = {p.name: p for p in projections}
    assert reference.keys() <= parsed.keys()

    mismatched: set[str] = set()
    for name, stats in reference.items():
        for stat, value in stats.items():
            if stat == "fpts" or stat in UNSCORED_STATS:
                continue
            if parsed[name].stats[stat] != pytest.approx(value):
                mismatched.add(name)
    assert mismatched == expected_disagreements


def test_wr_and_flx_really_do_disagree_about_column_order() -> None:
    """The premise of the test above, asserted rather than assumed.

    If a future re-pull harmonised the two layouts, the swap test would still pass while
    silently testing nothing. This fails loudly instead.
    """
    with WR_CSV.open(encoding="utf-8-sig", newline="") as handle:
        wr_header = next(csv.reader(handle))
    with FLX_CSV.open(encoding="utf-8-sig", newline="") as handle:
        flx_header = next(csv.reader(handle))

    assert wr_header == ["Player", "Team", "REC", "YDS", "TDS", "ATT", "YDS", "TDS", "FL", "FPTS"]
    assert flx_header == [
        "Player",
        "Team",
        "POS",
        "ATT",
        "YDS",
        "TDS",
        "REC",
        "YDS",
        "TDS",
        "FL",
        "FPTS",
    ]
    # Duplicated names, in different orders: the header cannot identify a column.
    assert wr_header.count("YDS") == flx_header.count("YDS") == 2
    assert wr_header.index("REC") < wr_header.index("ATT")
    assert flx_header.index("ATT") < flx_header.index("REC")


# ---- projections: failure modes --------------------------------------------------------


def test_wrong_column_count_raises(tmp_path: Path) -> None:
    bad = tmp_path / "flx.csv"
    bad.write_text('"Player","Team","POS"\n"A","BUF","RB1"\n', encoding="utf-8")
    with pytest.raises(ImportDataError, match="columns, expected 11"):
        parse_projections(QB_CSV, bad)


def test_short_data_row_raises(tmp_path: Path) -> None:
    header = ",".join(f"c{i}" for i in range(len(FLX_COLUMNS)))
    bad = tmp_path / "flx.csv"
    bad.write_text(f"{header}\nA,BUF,RB1,1,2,3\n", encoding="utf-8")
    with pytest.raises(ImportDataError, match="fields, expected 11"):
        parse_projections(QB_CSV, bad)


def test_unparseable_stat_raises_and_names_the_cell(tmp_path: Path) -> None:
    header = ",".join(f"c{i}" for i in range(len(FLX_COLUMNS)))
    bad = tmp_path / "flx.csv"
    bad.write_text(f"{header}\nA,BUF,RB1,1,n/a,3,4,5,6,7,8\n", encoding="utf-8")
    with pytest.raises(ImportDataError) as excinfo:
        parse_projections(QB_CSV, bad)
    assert "rush_yd" in str(excinfo.value)
    assert "'n/a'" in str(excinfo.value)


def test_duplicate_player_name_raises(tmp_path: Path) -> None:
    """Sleeper matching is keyed by FantasyPros name, so a duplicate masks a player."""
    header = ",".join(f"c{i}" for i in range(len(FLX_COLUMNS)))
    row = "Jahmyr Gibbs,DET,RB1,1,2,3,4,5,6,7,8"
    bad = tmp_path / "flx.csv"
    bad.write_text(f"{header}\n{row}\n{row}\n", encoding="utf-8")
    with pytest.raises(ImportDataError, match="appears twice"):
        parse_projections(QB_CSV, bad)


def test_unknown_position_in_flx_raises(tmp_path: Path) -> None:
    header = ",".join(f"c{i}" for i in range(len(FLX_COLUMNS)))
    bad = tmp_path / "flx.csv"
    bad.write_text(f"{header}\nA,BUF,LB3,1,2,3,4,5,6,7,8\n", encoding="utf-8")
    with pytest.raises(ImportDataError, match="unknown position"):
        parse_projections(QB_CSV, bad)


# --------------------------------------------------------------------------------------
# Rankings
# --------------------------------------------------------------------------------------


def test_rankings_parse_every_row(rankings: Sequence[RawRanking]) -> None:
    assert len(rankings) == RANKING_ROWS
    assert [r.overall_rank for r in rankings] == list(range(1, RANKING_ROWS + 1))
    assert {r.position for r in rankings} == {"QB", "RB", "WR", "TE"}


def test_rankings_first_row_is_pinned(rankings: Sequence[RawRanking]) -> None:
    assert rankings[0] == RawRanking(
        name="Josh Allen",
        team="BUF",
        position="QB",
        overall_rank=1,
        positional_rank=1,
        tier=1,
        bye_week=7,
    )


def test_rankings_export_is_superflex(rankings: Sequence[RawRanking]) -> None:
    """The 1QB variant shares this header and puts the first QB at 26."""
    first_qb = next(r for r in rankings if r.position == "QB")
    assert first_qb.overall_rank == 1
    assert sum(1 for r in rankings if r.position == "QB" and r.overall_rank <= 24) == 13


def test_one_qb_rankings_export_is_rejected(tmp_path: Path) -> None:
    """A 1QB export must not load: it makes every QB decision wrong the same way."""
    header = ",".join(f"c{i}" for i in range(12))
    lines = [header]
    for rank in range(1, 30):
        position = "QB1" if rank == 26 else f"WR{rank}"
        lines.append(f"{rank},1,Player {rank},BUF,{position},7,,,,,,")
    bad = tmp_path / "rankings.csv"
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ImportDataError, match="1QB export"):
        parse_rankings(bad)


def test_bye_weeks_are_complete_inside_the_draftable_window(
    rankings: Sequence[RawRanking],
) -> None:
    """LEG-4 defaulted these to `0` and shipped "Bye: 0" for 527 players."""
    inside = [r for r in rankings if r.overall_rank <= DRAFTABLE_PICKS]
    assert len(inside) == DRAFTABLE_PICKS
    assert all(r.bye_week is not None for r in inside)
    assert all(1 <= r.bye_week <= 18 for r in inside if r.bye_week is not None)


def test_missing_bye_outside_the_window_is_none_not_an_error(
    rankings: Sequence[RawRanking],
) -> None:
    """`BYE` is `'-'` on 125 rows from `RK 200` — free agents. That is the truth, not a
    defect, and it must not raise for a player nobody can draft."""
    missing = [r for r in rankings if r.bye_week is None]
    assert len(missing) == 125
    assert min(r.overall_rank for r in missing) == 200
    diggs = next(r for r in rankings if r.name == "Stefon Diggs")
    assert (diggs.overall_rank, diggs.team, diggs.bye_week) == (200, None, None)


def test_missing_bye_inside_the_window_raises(tmp_path: Path) -> None:
    header = ",".join(f"c{i}" for i in range(12))
    bad = tmp_path / "rankings.csv"
    bad.write_text(f"{header}\n1,1,Josh Allen,BUF,QB1,-,,,,,,\n", encoding="utf-8")
    with pytest.raises(ImportDataError, match="no bye week"):
        parse_rankings(bad)


def test_zero_bye_week_raises(tmp_path: Path) -> None:
    """The literal LEG-4 signature."""
    header = ",".join(f"c{i}" for i in range(12))
    bad = tmp_path / "rankings.csv"
    bad.write_text(f"{header}\n1,1,Josh Allen,BUF,QB1,0,,,,,,\n", encoding="utf-8")
    with pytest.raises(ImportDataError, match="bye week 0"):
        parse_rankings(bad)


def test_free_agent_team_normalises_to_none(rankings: Sequence[RawRanking]) -> None:
    """FantasyPros writes `FA`; `ingest.matching` requires `None`."""
    assert any(r.team is None for r in rankings)
    assert all(r.team != "FA" for r in rankings)


def test_rankings_tiers_are_complete(rankings: Sequence[RawRanking]) -> None:
    assert all(r.tier >= 1 for r in rankings)


def test_rankings_positional_ranks_are_dense_per_position(
    rankings: Sequence[RawRanking],
) -> None:
    seen: dict[str, list[int]] = {}
    for ranking in rankings:
        seen.setdefault(ranking.position, []).append(ranking.positional_rank)
    for position, ranks in seen.items():
        assert ranks == list(range(1, len(ranks) + 1)), position


def test_non_dense_overall_rank_raises(tmp_path: Path) -> None:
    header = ",".join(f"c{i}" for i in range(12))
    bad = tmp_path / "rankings.csv"
    bad.write_text(
        f"{header}\n1,1,Josh Allen,BUF,QB1,7,,,,,,\n3,1,Lamar Jackson,BAL,QB2,13,,,,,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ImportDataError, match="dense"):
        parse_rankings(bad)


# --------------------------------------------------------------------------------------
# ADP
# --------------------------------------------------------------------------------------


def test_adp_rows_parse(adp_rows: Sequence[AdpRow]) -> None:
    assert len(adp_rows) == ADP_ROWS
    assert [row.superflex_rank for row in adp_rows] == list(range(1, ADP_ROWS + 1))


def test_op_is_the_superflex_rank_and_overall_is_the_1qb_one(
    adp_rows: Sequence[AdpRow],
) -> None:
    """The trap this project has now guarded against three times."""
    allen = adp_rows[0]
    assert allen.name == "Josh Allen"
    assert allen.superflex_rank == 1
    assert allen.one_qb_rank == 22
    assert allen.team == "BUF"
    assert allen.bye_week == 7
    assert allen.sleeper == pytest.approx(1.0)
    assert allen.ffpc == pytest.approx(2.0)
    assert allen.average == pytest.approx(1.5)
    assert allen.real_time == pytest.approx(3.0)


def test_composite_player_field_splits_on_a_multi_space_run(
    adp_rows: Sequence[AdpRow],
) -> None:
    """`'Amon-Ra St. Brown   DET (6)'` — single spaces live *inside* the name."""
    st_brown = next(row for row in adp_rows if row.name == "Amon-Ra St. Brown")
    assert (st_brown.team, st_brown.bye_week) == ("DET", 6)
    assert all("  " not in row.name for row in adp_rows)
    assert all("(" not in row.name for row in adp_rows)


def test_name_only_rows_parse_rather_than_raising(adp_rows: Sequence[AdpRow]) -> None:
    """Three free agents carry no team and no bye."""
    nameless = [row for row in adp_rows if row.team is None]
    assert {row.name for row in nameless} == {"Stefon Diggs", "Tyreek Hill", "Joe Mixon"}
    assert all(row.bye_week is None for row in nameless)


def test_em_dash_is_the_missing_value_marker(adp_rows: Sequence[AdpRow]) -> None:
    """U+2014, not `'-'` and not empty. `AVG` is present on every row; the others are not."""
    assert EM_DASH == "—"
    assert sum(1 for row in adp_rows if row.one_qb_rank is None) == 10
    assert sum(1 for row in adp_rows if row.sleeper is None) == 16
    assert sum(1 for row in adp_rows if row.ffpc is None) == 37
    assert sum(1 for row in adp_rows if row.real_time is None) == 15
    assert all(row.average > 0 for row in adp_rows)


def test_the_export_really_does_contain_em_dashes() -> None:
    """Guards the test above from a re-pull that changed the marker to `'-'` or empty."""
    text = ADP_CSV.read_text(encoding="utf-8-sig")
    assert EM_DASH in text


def test_average_excludes_real_time(adp_rows: Sequence[AdpRow]) -> None:
    """Trap 5: `AVG == mean(Sleeper, FFPC)`, and `Real-Time` is a third, separate source."""
    for row in adp_rows:
        sources = [value for value in (row.sleeper, row.ffpc) if value is not None]
        assert sources, row.name
        assert row.average == pytest.approx(sum(sources) / len(sources), abs=0.051), row.name

    disagreeing = [
        row
        for row in adp_rows
        if row.real_time is not None and abs(row.real_time - row.average) > 1.0
    ]
    assert disagreeing, "Real-Time tracks AVG exactly; the invariant above is now vacuous"


def test_adp_is_on_the_same_scale_as_pick_numbers(adp_rows: Sequence[AdpRow]) -> None:
    window = [row for row in adp_rows if row.superflex_rank <= DRAFTABLE_PICKS]
    assert len(window) == DRAFTABLE_PICKS
    assert min(row.average for row in window) == pytest.approx(1.5)
    assert max(row.average for row in window) == pytest.approx(164.0)


def test_the_top_of_op_is_qb_heavy(adp_rows: Sequence[AdpRow]) -> None:
    """The acceptance criterion, measured exactly by joining positions from the rankings.

    The ADP export carries no position column, so the parser's own integrity check uses
    the position-free superflex signature (`OP` far better than the 1QB `Overall`). This
    test does the join the parser cannot, and pins the counts that decision 2 of
    `docs/plan_phase2_decision_engine.md` rests on: **8 QBs in the top 24, 32 in the top
    160.** A 1QB export would put roughly 1 in the top 24.
    """
    positions = {ranking.name: ranking.position for ranking in parse_rankings(RANKINGS_CSV)}
    window = [row for row in adp_rows if row.superflex_rank <= DRAFTABLE_PICKS]
    assert all(row.name in positions for row in window), "positions incomplete inside the window"

    quarterbacks = [row for row in window if positions[row.name] == "QB"]
    assert sum(1 for row in quarterbacks if row.superflex_rank <= 24) == 8
    assert len(quarterbacks) == 32


def test_a_secretly_1qb_adp_export_is_rejected(tmp_path: Path) -> None:
    """In a 1QB file `OP` and `Overall` agree, so the superflex QB lift vanishes."""
    lines = ["OP,Overall,Player (Bye),Sleeper,FFPC,AVG,Real-Time"]
    for rank in range(1, DRAFTABLE_PICKS + 1):
        lines.append(f"{rank},{rank},Player {rank}   BUF (7),{rank},{rank},{rank}.0,{rank}")
    bad = tmp_path / "adp.csv"
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ImportDataError, match="superflex ADP export"):
        parse_adp_rows(bad)


def test_average_that_is_not_the_mean_of_its_sources_raises(tmp_path: Path) -> None:
    lines = [
        "OP,Overall,Player (Bye),Sleeper,FFPC,AVG,Real-Time",
        "1,22,Josh Allen   BUF (7),1,2,9.9,3",
    ]
    bad = tmp_path / "adp.csv"
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ImportDataError, match="mean of those two"):
        parse_adp_rows(bad)


def test_adp_wrong_column_count_raises(tmp_path: Path) -> None:
    bad = tmp_path / "adp.csv"
    bad.write_text("OP,Overall,Player (Bye)\n1,22,Josh Allen   BUF (7)\n", encoding="utf-8")
    with pytest.raises(ImportDataError, match="columns, expected 7"):
        parse_adp_rows(bad)


# ---- BLK-1: no Std Dev source -----------------------------------------------------------


def test_parse_adp_raises_because_no_std_dev_source_exists() -> None:
    """`AdpEstimate` requires `sd > 0` and this export has no `Std Dev` column.

    Modelling `sd = f(adp)` means choosing a dispersion coefficient with no data behind
    it. That is LEG-1 and LEG-5. The parse underneath is fine — see the tests above — so
    this raises about the *missing source*, not about the data.
    """
    assert fantasypros.STANDARD_DEVIATION_SOURCE is None
    with pytest.raises(ImportDataError) as excinfo:
        parse_adp(ADP_CSV)
    message = str(excinfo.value)
    assert "Std Dev" in message
    assert "BLK-1" in message
    assert "parsed cleanly" in message


def test_parse_adp_rejects_a_1qb_file_before_it_complains_about_std_dev(
    tmp_path: Path,
) -> None:
    """A bad file must fail for the reason it is bad, not for a missing config."""
    lines = ["OP,Overall,Player (Bye),Sleeper,FFPC,AVG,Real-Time"]
    for rank in range(1, DRAFTABLE_PICKS + 1):
        lines.append(f"{rank},{rank},Player {rank}   BUF (7),{rank},{rank},{rank}.0,{rank}")
    bad = tmp_path / "adp.csv"
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ImportDataError, match="superflex ADP export"):
        parse_adp(bad)


def test_wiring_in_a_std_dev_source_is_the_only_change_needed(
    monkeypatch: pytest.MonkeyPatch, adp_rows: Sequence[AdpRow]
) -> None:
    """Proves BLK-1 is a one-line fix rather than a rewrite.

    Uses a deliberately fake dispersion — that is fine in a test, and exactly not fine in
    the shipping parser.
    """
    fake = {row.name: 1.0 + row.average / 10.0 for row in adp_rows}
    monkeypatch.setattr(fantasypros, "STANDARD_DEVIATION_SOURCE", fake)

    estimates = parse_adp(ADP_CSV)
    assert len(estimates) == ADP_ROWS
    allen = estimates["Josh Allen"]
    assert isinstance(allen, AdpEstimate)
    assert allen.adp == pytest.approx(1.5)
    assert allen.sd == pytest.approx(1.15)


def test_an_incomplete_std_dev_source_raises(
    monkeypatch: pytest.MonkeyPatch, adp_rows: Sequence[AdpRow]
) -> None:
    partial = {row.name: 5.0 for row in adp_rows[1:]}
    monkeypatch.setattr(fantasypros, "STANDARD_DEVIATION_SOURCE", partial)
    with pytest.raises(ImportDataError, match="no ADP standard deviation for 'Josh Allen'"):
        parse_adp(ADP_CSV)


# --------------------------------------------------------------------------------------
# Cross-file coherence
# --------------------------------------------------------------------------------------


def test_projections_cover_the_draftable_window_of_the_rankings(
    projections: Sequence[RawProjection], rankings: Sequence[RawRanking]
) -> None:
    """Every player who can actually be drafted must have a projection to rank him by."""
    projected = {p.name for p in projections}
    missing = [
        r.name for r in rankings if r.overall_rank <= DRAFTABLE_PICKS and r.name not in projected
    ]
    assert missing == []


def test_positions_agree_between_projections_and_rankings(
    projections: Sequence[RawProjection], rankings: Sequence[RawRanking]
) -> None:
    ranked = {r.name: r.position for r in rankings}
    disagreements = [
        (p.name, p.position, ranked[p.name])
        for p in projections
        if p.name in ranked and ranked[p.name] != p.position
    ]
    assert disagreements == []


def test_no_stray_whitespace_survives_parsing(
    projections: Sequence[RawProjection], rankings: Sequence[RawRanking]
) -> None:
    for name in [p.name for p in projections] + [r.name for r in rankings]:
        assert name == name.strip()
        assert not re.search(r"\s{2,}", name)
