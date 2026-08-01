"""Tests for gap-based tier detection.

The centre of gravity is `test_removing_any_player_changes_nothing_but_his_own_boundary`.
Tier detection was not chosen for accuracy — it scores *worse* than Jenks on agreement with
FantasyPros' own labels (ARI 0.336 vs 0.392). It was chosen because it is **local**: removing
one player can only change the partition at that player's own position. Mid-draft, a display
whose tier line jumps 65 positions away on someone else's pick is worse than no display at
all. So locality is the property under test, and it is tested exhaustively rather than by
example.

A boundary is represented as the **pair of adjacent player ids it separates**, not as an
index, so the representation survives a player being removed from the middle of the board.
"""

import csv
from collections.abc import Mapping
from pathlib import Path

import pytest

from popacta.domain.errors import InvalidPlayerError
from popacta.domain.positions import Position
from popacta.domain.tiers import (
    DEFAULT_MIN_TIER_SIZE,
    DEFAULT_THRESHOLD,
    TieredBoard,
    detect_tiers,
    detect_tiers_by_position,
)

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "fantasypros"

THRESHOLDS = (2.0, 3.5, 6.0, 6.0000001, 9.0, 25.0)


# --- helpers --------------------------------------------------------------------------


def board_from(points: list[float], prefix: str = "p") -> dict[str, float]:
    """Ids in descending-value order by construction, so tests read positionally."""
    return {f"{prefix}{i}": v for i, v in enumerate(points)}


def _stepped_packs() -> list[float]:
    """One outlier, then three tight packs separated by a large, medium and small drop."""
    values = [600.0]
    top = 300.0
    for drop in (0.0, 50.0, 10.0):
        top -= drop
        values.extend(top - 4.0 * i for i in range(10))
        top -= 4.0 * 9
    return values


def ordered_ids(values: Mapping[str, float]) -> list[str]:
    return [pid for pid, _ in sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))]


def cuts(board: TieredBoard) -> set[tuple[str, str]]:
    """Every tier boundary, as the (above, below) id pair it separates."""
    flat = [pid for tier in board.tiers for pid in tier.player_ids]
    out: set[tuple[str, str]] = set()
    index = 0
    for tier in board.tiers[:-1]:
        index += len(tier.player_ids)
        out.add((flat[index - 1], flat[index]))
    return out


def partition(board: TieredBoard) -> tuple[tuple[str, ...], ...]:
    return tuple(tier.player_ids for tier in board.tiers)


def non_local_changes(
    values: Mapping[str, float], *, threshold: float, min_tier_size: int
) -> list[tuple[str, set[tuple[str, str]], int]]:
    """Remove each player in turn; report every boundary change away from his own slot.

    Removing player `x` between `a` and `b` merges the two gaps `a-x` and `x-b` into one
    gap `a-b`. So the *only* legitimate difference between the two partitions is: the
    boundaries touching `x` disappear, and a boundary `(a, b)` may appear. Anything else
    is a boundary that moved because of a player it does not sit next to.

    Returns `(removed_id, offending_boundaries, worst_distance_in_positions)` per failure.
    """
    ids = ordered_ids(values)
    rank = {pid: i for i, pid in enumerate(ids)}
    before = cuts(detect_tiers(values, threshold=threshold, min_tier_size=min_tier_size))

    failures = []
    for i, removed in enumerate(ids):
        reduced = {pid: v for pid, v in values.items() if pid != removed}
        if not reduced:
            continue
        after = cuts(detect_tiers(reduced, threshold=threshold, min_tier_size=min_tier_size))
        merged = (ids[i - 1], ids[i + 1]) if 0 < i < len(ids) - 1 else None
        expected = {c for c in before if removed not in c}
        actual = {c for c in after if c != merged}
        offending = expected ^ actual
        if offending:
            distance = max(max(abs(rank[a] - i), abs(rank[b] - i)) for a, b in offending)
            failures.append((removed, offending, distance))
    return failures


def read_projection_points() -> dict[Position, dict[str, float]]:
    """A deliberately minimal read of the projection exports — no ingest dependency.

    `QB` + `FLX` is the whole ranked universe (518 rows); see
    `docs/reference_fantasypros_exports.md`. Only the player name and the final `FPTS`
    column are needed here, so the column-order trap that makes a real parser hard does
    not apply — but `FPTS` is still read as the **last** column by index, never by name.
    """
    out: dict[Position, dict[str, float]] = {
        p: {} for p in (Position.QB, Position.RB, Position.WR, Position.TE)
    }

    def rows(name: str) -> list[list[str]]:
        with (DATA_DIR / name).open(encoding="utf-8-sig", newline="") as handle:
            # Row 2 of every projections export is a junk spacer with a blank first field.
            return [r for r in csv.reader(handle) if r and r[0].strip() and r[0] != "Player"]

    for row in rows("FantasyPros_Fantasy_Football_Projections_QB.csv"):
        out[Position.QB][row[0]] = float(row[-1].replace(",", ""))
    for row in rows("FantasyPros_Fantasy_Football_Projections_FLX.csv"):
        # `POS` embeds position and positional rank: "RB1", "WR12".
        out[Position(row[2][:2])][row[0]] = float(row[-1].replace(",", ""))
    return out


@pytest.fixture(scope="module")
def real_points() -> dict[Position, dict[str, float]]:
    points = read_projection_points()
    assert sum(len(v) for v in points.values()) == 518, "QB + FLX must cover all 518 players"
    return points


# --- input validation -----------------------------------------------------------------


def test_an_empty_board_raises() -> None:
    with pytest.raises(ValueError, match="at least one player"):
        detect_tiers({})


@pytest.mark.parametrize("threshold", [0.0, -1.0, -6.0])
def test_a_non_positive_threshold_raises(threshold: float) -> None:
    """A zero threshold puts every player in his own tier — a silently useless display."""
    with pytest.raises(ValueError, match="threshold must be positive"):
        detect_tiers(board_from([100.0, 90.0]), threshold=threshold)


@pytest.mark.parametrize("min_tier_size", [0, -1])
def test_a_min_tier_size_below_one_raises(min_tier_size: int) -> None:
    with pytest.raises(ValueError, match="min_tier_size must be at least 1"):
        detect_tiers(board_from([100.0, 90.0]), min_tier_size=min_tier_size)


def test_an_unknown_player_id_raises() -> None:
    board = detect_tiers(board_from([100.0, 90.0]))

    with pytest.raises(InvalidPlayerError, match="not on the"):
        board.tier_of("nobody")


def test_players_until_cliff_and_value_of_cliff_also_raise_on_an_unknown_id() -> None:
    board = detect_tiers(board_from([100.0, 90.0]))

    with pytest.raises(InvalidPlayerError):
        board.players_until_cliff("nobody")
    with pytest.raises(InvalidPlayerError):
        board.value_of_cliff("nobody")


# --- the partition --------------------------------------------------------------------


def test_a_single_player_is_one_tier() -> None:
    board = detect_tiers({"solo": 300.0})

    assert partition(board) == (("solo",),)
    assert board.tiers[0].gap_below is None


def test_gaps_below_the_threshold_do_not_break_a_tier() -> None:
    board = detect_tiers(board_from([100.0, 97.0, 94.0, 91.0]), threshold=6.0)

    assert partition(board) == (("p0", "p1", "p2", "p3"),)


def test_a_gap_at_or_above_the_threshold_breaks_the_tier() -> None:
    board = detect_tiers(board_from([100.0, 93.0, 90.0]), threshold=6.0)

    assert partition(board) == (("p0",), ("p1", "p2"))


def test_a_gap_exactly_equal_to_the_threshold_breaks_the_tier() -> None:
    """`>=`, stated explicitly, so the boundary does not flip on float noise."""
    board = detect_tiers(board_from([100.0, 94.0, 88.0]), threshold=6.0)

    assert partition(board) == (("p0",), ("p1",), ("p2",))


def test_a_gap_a_hair_under_the_threshold_does_not_break_the_tier() -> None:
    board = detect_tiers(board_from([100.0, 94.001, 88.002]), threshold=6.0)

    assert partition(board) == (("p0", "p1", "p2"),)


def test_input_order_does_not_matter() -> None:
    ascending = {"p2": 80.0, "p1": 93.0, "p0": 100.0}

    assert partition(detect_tiers(ascending, threshold=6.0)) == (("p0",), ("p1",), ("p2",))


def test_tied_values_are_ordered_deterministically_by_id() -> None:
    """Two identical projections must not reshuffle the display between picks."""
    first = detect_tiers({"b": 100.0, "a": 100.0, "c": 100.0}, threshold=6.0)
    second = detect_tiers({"c": 100.0, "b": 100.0, "a": 100.0}, threshold=6.0)

    assert partition(first) == partition(second) == (("a", "b", "c"),)


def test_tier_metadata_reports_the_edges_and_the_drop() -> None:
    board = detect_tiers(board_from([100.0, 96.0, 80.0, 78.0]), threshold=6.0)

    top, bottom = board.tiers
    assert (top.number, top.top_value, top.bottom_value, top.gap_below) == (1, 100.0, 96.0, 16.0)
    assert (bottom.number, bottom.top_value, bottom.bottom_value) == (2, 80.0, 78.0)
    assert bottom.gap_below is None


def test_the_board_records_its_own_parameters() -> None:
    board = detect_tiers(board_from([100.0]), threshold=7.5, min_tier_size=3, position=Position.TE)

    assert (board.position, board.threshold, board.min_tier_size) == (Position.TE, 7.5, 3)


def test_a_pooled_board_is_marked_with_a_none_position() -> None:
    assert detect_tiers(board_from([100.0])).position is None


def test_every_player_appears_in_exactly_one_tier() -> None:
    values = board_from([100.0, 99.0, 80.0, 79.0, 40.0, 39.0, 38.0])
    board = detect_tiers(values, threshold=6.0)

    flat = [pid for tier in board.tiers for pid in tier.player_ids]
    assert sorted(flat) == sorted(values)
    assert len(flat) == len(set(flat))


# --- the UI numbers -------------------------------------------------------------------


def test_players_until_cliff_counts_the_player_himself_and_everyone_below_him() -> None:
    """ "2 left before the cliff" means him and one more — the number on screen."""
    board = detect_tiers(board_from([100.0, 99.0, 98.0, 97.0, 50.0]), threshold=6.0)

    assert board.players_until_cliff("p0") == 4
    assert board.players_until_cliff("p2") == 2
    assert board.players_until_cliff("p3") == 1


def test_value_of_cliff_is_the_drop_below_the_tier() -> None:
    board = detect_tiers(board_from([100.0, 99.0, 50.0]), threshold=6.0)

    assert board.value_of_cliff("p0") == pytest.approx(49.0)
    assert board.value_of_cliff("p1") == pytest.approx(49.0)


def test_value_of_cliff_is_none_for_the_last_tier() -> None:
    """There is nothing below the bottom tier to fall off."""
    board = detect_tiers(board_from([100.0, 50.0]), threshold=6.0)

    assert board.value_of_cliff("p1") is None


def test_tier_of_returns_the_tier_containing_the_player() -> None:
    board = detect_tiers(board_from([100.0, 50.0, 49.0]), threshold=6.0)

    assert board.tier_of("p2").number == 2
    assert board.tier_of("p0").player_ids == ("p0",)


# --- min_tier_size --------------------------------------------------------------------


def test_min_tier_size_one_leaves_the_raw_gap_partition_alone() -> None:
    values = board_from([100.0, 90.0, 80.0, 70.0])

    assert partition(detect_tiers(values, threshold=6.0, min_tier_size=1)) == (
        ("p0",),
        ("p1",),
        ("p2",),
        ("p3",),
    )


def test_min_tier_size_merges_a_run_of_singletons_and_drops_the_tier_count() -> None:
    """The top of a real board is a run of singletons; showing four is not a display."""
    values = board_from([100.0, 90.0, 80.0, 70.0, 60.0, 50.0])

    raw = detect_tiers(values, threshold=6.0, min_tier_size=1)
    merged = detect_tiers(values, threshold=6.0, min_tier_size=2)
    coarse = detect_tiers(values, threshold=6.0, min_tier_size=3)

    assert len(raw.tiers) == 6
    assert partition(merged) == (("p0", "p1"), ("p2", "p3"), ("p4", "p5"))
    assert partition(coarse) == (("p0", "p1", "p2"), ("p3", "p4", "p5"))


def test_an_undersized_run_merges_into_the_tier_below() -> None:
    values = board_from([100.0, 90.0, 89.0, 88.0])

    assert partition(detect_tiers(values, threshold=6.0, min_tier_size=2)) == (
        ("p0", "p1", "p2", "p3"),
    )


def test_an_undersized_trailing_remnant_merges_upward_instead() -> None:
    """The bottom tier has no tier below it; merging up is the only direction there is."""
    values = board_from([100.0, 99.0, 50.0])

    assert partition(detect_tiers(values, threshold=6.0, min_tier_size=2)) == (("p0", "p1", "p2"),)


def test_a_min_tier_size_larger_than_the_board_yields_one_tier() -> None:
    values = board_from([100.0, 90.0, 80.0])

    assert partition(detect_tiers(values, threshold=6.0, min_tier_size=99)) == (("p0", "p1", "p2"),)


def test_merging_never_loses_or_duplicates_a_player() -> None:
    values = board_from([100.0, 90.0, 89.0, 70.0, 69.0, 68.0, 40.0, 20.0])

    for size in range(1, 10):
        flat = [
            pid
            for tier in detect_tiers(values, threshold=6.0, min_tier_size=size).tiers
            for pid in tier.player_ids
        ]
        assert sorted(flat) == sorted(values)


def test_tier_numbers_are_contiguous_and_one_based_after_merging() -> None:
    values = board_from([100.0, 90.0, 80.0, 70.0, 60.0])
    board = detect_tiers(values, threshold=6.0, min_tier_size=2)

    assert [tier.number for tier in board.tiers] == list(range(1, len(board.tiers) + 1))


# --- locality: the reason this algorithm was chosen ------------------------------------


LOCALITY_BOARDS: dict[str, dict[str, float]] = {
    "clean_tiers": board_from([100.0, 99.0, 98.0, 70.0, 69.0, 68.0, 40.0, 39.0]),
    "all_singletons": board_from([100.0, 80.0, 60.0, 40.0, 20.0, 10.0, 1.0]),
    "one_flat_run": board_from([100.0 - 0.5 * i for i in range(20)]),
    "near_threshold_gaps": board_from([100.0 - 5.9 * i for i in range(15)]),
    "exact_threshold_gaps": board_from([100.0 - 6.0 * i for i in range(15)]),
    "ties": board_from([100.0, 100.0, 100.0, 60.0, 60.0, 30.0]),
    "long_tail": board_from([300.0, 280.0, 279.0, 250.0] + [100.0 - 0.3 * i for i in range(60)]),
    # The board that gives this test its teeth. One unicorn sits far above three dense
    # packs separated by a large, a medium and a small drop. Removing the unicorn removes
    # most of the board's range, so any `k * mean(gap)` or `k * median(gap)` threshold
    # collapses and the small drop 20 positions below him suddenly becomes a tier
    # boundary. Verified against a derived threshold: it fails here. A frozen absolute
    # threshold does not notice him leave, which is the entire argument for decision 9.
    "unicorn_over_packs": board_from(_stepped_packs()),
}


@pytest.mark.parametrize("threshold", THRESHOLDS)
@pytest.mark.parametrize("name", sorted(LOCALITY_BOARDS))
def test_removing_any_player_changes_nothing_but_his_own_boundary(
    name: str, threshold: float
) -> None:
    """**The single most important test in this module.**

    Remove every player in turn and confirm the partition changes only where he was. The
    property is structural: removing a player merges the two gaps he sat between, so no
    other comparison in the algorithm can change its answer. Jenks moves boundaries up to
    37 positions away and a largest-N-gaps rule up to 99 — that is what a data-derived or
    globally-coupled threshold buys you, and it is why the threshold is a frozen constant.
    """
    failures = non_local_changes(LOCALITY_BOARDS[name], threshold=threshold, min_tier_size=1)

    assert failures == [], (
        f"{len(failures)} removal(s) from board {name!r} at threshold {threshold} moved a "
        f"boundary away from the removed player: {failures[:3]}"
    )


@pytest.mark.parametrize("threshold", THRESHOLDS)
def test_locality_holds_on_the_real_projection_board(
    real_points: dict[Position, dict[str, float]], threshold: float
) -> None:
    """Same property, on the board that will actually be on screen on 2026-08-28."""
    for position, values in real_points.items():
        failures = non_local_changes(values, threshold=threshold, min_tier_size=1)
        assert failures == [], (
            f"{position}: {len(failures)} of {len(values)} removals moved a distant "
            f"boundary at threshold {threshold}: {failures[:3]}"
        )


def test_locality_is_not_a_property_of_the_min_tier_size_merge_pass() -> None:
    """**A documented limitation, pinned so it cannot regress silently.**

    The *gap rule* is local; the `min_tier_size` merge pass is a downward-accumulating
    scan, so removing a player can change which runs get absorbed further down the board.
    On an all-singletons board that is a parity flip affecting every boundary below him.

    This is a genuine departure from the "zero non-local changes" claim in decision 9,
    which is measured for the gap rule alone. Measured cost on the real projection board
    is small and near — see the next test — but it is not zero, and pretending otherwise
    is how a display quietly gets worse than no display.
    """
    singletons = board_from([100.0 - 20.0 * i for i in range(9)])

    assert non_local_changes(singletons, threshold=6.0, min_tier_size=1) == []
    assert non_local_changes(singletons, threshold=6.0, min_tier_size=2) != []


@pytest.mark.parametrize("threshold", [5.0, 6.0, 7.0])
def test_the_merge_pass_stays_in_the_neighbourhood_on_the_real_board(
    real_points: dict[Position, dict[str, float]], threshold: float
) -> None:
    """Bounded, if not zero: the merge pass moves boundaries a few slots, not 37 or 99.

    Measured 2026-08-01 on the pinned projections at `t=6.0, min_tier_size=2`: 8/82 QB,
    6/128 RB, 5/189 WR, 3/119 TE removals produce a non-local change, and the worst
    distance is 7 positions (QB) — versus 37 for Jenks and 99 for largest-N-gaps. The
    display is still stable enough to trust; the bound is what makes that true.
    """
    for position, values in real_points.items():
        failures = non_local_changes(values, threshold=threshold, min_tier_size=2)
        affected = len(failures) / len(values)
        worst = max((distance for _, _, distance in failures), default=0)

        assert affected <= 0.15, f"{position}: {affected:.0%} of removals perturb the board"
        assert worst <= 10, f"{position}: a boundary moved {worst} positions away"


# --- points vs VORP -------------------------------------------------------------------


@pytest.mark.parametrize("baseline", [0.0, 12.5, 192.8, -30.0])
@pytest.mark.parametrize("min_tier_size", [1, 2, 3])
def test_points_and_vorp_produce_identical_partitions(baseline: float, min_tier_size: int) -> None:
    """VORP is points minus a **per-position constant**, so within a position the gaps —
    and therefore the tiers — are unchanged. Assert it so nobody "fixes" it later by
    re-tiering on VORP and expecting a different answer.
    """
    points = board_from([320.0, 318.0, 300.0, 299.0, 250.0, 249.0, 248.0, 100.0])
    vorp = {pid: value - baseline for pid, value in points.items()}

    assert partition(detect_tiers(points, threshold=6.0, min_tier_size=min_tier_size)) == partition(
        detect_tiers(vorp, threshold=6.0, min_tier_size=min_tier_size)
    )


def test_points_and_vorp_agree_on_the_real_board(
    real_points: dict[Position, dict[str, float]],
) -> None:
    """The same claim on 518 real players, with a plausible replacement level per position."""
    baselines = {Position.QB: 192.8, Position.RB: 110.4, Position.WR: 118.7, Position.TE: 86.2}

    for position, values in real_points.items():
        vorp = {pid: v - baselines[position] for pid, v in values.items()}
        by_points = detect_tiers(values, threshold=DEFAULT_THRESHOLD, position=position)
        by_vorp = detect_tiers(vorp, threshold=DEFAULT_THRESHOLD, position=position)

        assert partition(by_points) == partition(by_vorp), f"{position} partitions diverged"


# --- detect_tiers_by_position ---------------------------------------------------------


def test_positions_are_tiered_separately_and_never_pooled() -> None:
    """Interleaved positions fill in exactly the holes tier detection is looking for."""
    values = {"qb1": 300.0, "rb1": 297.0, "qb2": 294.0, "rb2": 291.0}
    positions = {
        "qb1": Position.QB,
        "qb2": Position.QB,
        "rb1": Position.RB,
        "rb2": Position.RB,
    }

    pooled = detect_tiers(values, threshold=6.0)
    boards = detect_tiers_by_position(values, positions, threshold=6.0, min_tier_size=1)

    assert len(pooled.tiers) == 1, "pooling hides every gap — this is the failure mode"
    assert partition(boards[Position.QB]) == (("qb1",), ("qb2",))
    assert partition(boards[Position.RB]) == (("rb1",), ("rb2",))


def test_each_board_records_its_own_position() -> None:
    values = {"qb1": 300.0, "te1": 150.0}
    positions = {"qb1": Position.QB, "te1": Position.TE}

    boards = detect_tiers_by_position(values, positions)

    assert boards[Position.QB].position is Position.QB
    assert boards[Position.TE].position is Position.TE


def test_only_positions_present_in_the_values_get_a_board() -> None:
    boards = detect_tiers_by_position({"qb1": 300.0}, {"qb1": Position.QB})

    assert set(boards) == {Position.QB}


def test_the_returned_mapping_is_read_only() -> None:
    boards = detect_tiers_by_position({"qb1": 300.0}, {"qb1": Position.QB})

    with pytest.raises(TypeError):
        boards[Position.RB] = boards[Position.QB]  # type: ignore[index]


def test_the_default_min_tier_size_is_two_by_position() -> None:
    """`detect_tiers` defaults to the raw partition; the display default is 2."""
    boards = detect_tiers_by_position({"qb1": 300.0}, {"qb1": Position.QB})

    assert boards[Position.QB].min_tier_size == DEFAULT_MIN_TIER_SIZE
    assert boards[Position.QB].threshold == DEFAULT_THRESHOLD
    assert detect_tiers({"qb1": 300.0}).min_tier_size == 1


@pytest.mark.parametrize("position", [Position.DEF, Position.K])
def test_a_defense_or_kicker_reaching_tier_detection_raises(position: Position) -> None:
    """Neither is projected, so a value for one means the caller filtered nothing."""
    with pytest.raises(InvalidPlayerError, match="never tiered"):
        detect_tiers_by_position({"x": 90.0}, {"x": position})


def test_a_player_with_no_position_raises() -> None:
    """Silently dropping him is how a player disappears from the board mid-draft."""
    with pytest.raises(InvalidPlayerError, match="no position for player id"):
        detect_tiers_by_position({"qb1": 300.0, "ghost": 280.0}, {"qb1": Position.QB})


def test_extra_entries_in_positions_are_harmless() -> None:
    """`positions` is a lookup table for the whole pool; `values` is the available subset."""
    positions = {f"p{i}": Position.RB for i in range(50)}

    boards = detect_tiers_by_position({"p0": 300.0, "p1": 200.0}, positions)

    assert sum(len(t.player_ids) for t in boards[Position.RB].tiers) == 2


# --- the real board -------------------------------------------------------------------


def test_real_projection_tier_counts_are_in_a_sane_range(
    real_points: dict[Position, dict[str, float]],
) -> None:
    """A tier count near 1 means the display never warns; near n means it always does.

    Measured 2026-08-01 on the pinned projections at `t=6.0, min_tier_size=2` over the
    full 518-player board: **QB 8, RB 10, WR 7, TE 5**. Research reported roughly QB 5,
    RB 10, WR 6, TE 4 on draft-depth boards; restricting to the top 33 per position here
    gives QB 6, RB 7, WR 6, TE 5, so the two agree to within a tier or two. The range
    below is deliberately wide — this test guards against a collapse to 1 or an explosion
    to 40, not against a threshold sweep moving a count by one.
    """
    positions = {pid: pos for pos, group in real_points.items() for pid in group}
    values = {pid: v for group in real_points.values() for pid, v in group.items()}

    boards = detect_tiers_by_position(values, positions)
    counts = {position: len(board.tiers) for position, board in boards.items()}

    assert set(counts) == {Position.QB, Position.RB, Position.WR, Position.TE}
    for position, count in counts.items():
        assert 3 <= count <= 20, f"{position} produced {count} tiers, which is not a display"
    assert min(len(t.player_ids) for b in boards.values() for t in b.tiers) >= DEFAULT_MIN_TIER_SIZE


def test_the_top_of_the_real_qb_board_is_not_one_flat_tier(
    real_points: dict[Position, dict[str, float]],
) -> None:
    """The QB cliff is the decision this app exists to get right — it must be visible."""
    board = detect_tiers(real_points[Position.QB], position=Position.QB)
    best = max(real_points[Position.QB], key=lambda pid: real_points[Position.QB][pid])

    assert best == "Josh Allen"
    assert board.players_until_cliff(best) < len(real_points[Position.QB])
    assert board.value_of_cliff(best) is not None
    assert board.value_of_cliff(best) >= DEFAULT_THRESHOLD


def test_recomputing_on_a_partly_drafted_real_board_is_stable(
    real_points: dict[Position, dict[str, float]],
) -> None:
    """The intended usage: recompute every pick against the available players only.

    Drafting the top 20 RBs must not reorganise the tiers of the RBs below them.
    """
    rbs = real_points[Position.RB]
    drafted = set(sorted(rbs, key=lambda pid: -rbs[pid])[:20])
    remaining = {pid: v for pid, v in rbs.items() if pid not in drafted}

    before = detect_tiers(rbs, min_tier_size=1, position=Position.RB)
    after = detect_tiers(remaining, min_tier_size=1, position=Position.RB)

    survived = {cut for cut in cuts(before) if not (set(cut) & drafted)}
    assert survived <= cuts(after)
