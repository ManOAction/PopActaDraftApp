"""Tests for positional demand and replacement level.

Two numbers live in this module and they must never be confused: **draft demand** (how
many come off the board in `teams * rounds` picks, which sets replacement level) and
**starter demand** (how many are started league-wide, which drives the sensitivity band).
On the pinned data they differ by 12 at QB and by 160.7 points of `r_QB`.

Three groups of tests:

- **Synthetic** — small hand-built pools where the right answer is countable by eye, plus
  a brute-force oracle for the greedy allocation.
- **Pinned data** — the real FantasyPros exports, reproducing the numbers the Phase 2 plan
  was decided on. The CSV reader below is a throwaway for this file only; `ingest/` owns
  the real one. It exists so these tests do not have to wait on it.
- **LEG-1 regression** — the 2025 app's fudged per-position slot counts, re-run through
  the same allocation, documenting what integer columns cost.
"""

import csv
import itertools
import json
import random
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from popacta.domain.errors import ImportDataError
from popacta.domain.league import SLOT_ELIGIBILITY, LeagueConfig, SlotInstance
from popacta.domain.players import AdpEstimate, Player
from popacta.domain.positions import RANKED_POSITIONS, Position
from popacta.domain.replacement import draft_demand, replacement_levels, starter_demand

FIXTURES = Path(__file__).parent.parent / "fixtures"
DATA = Path(__file__).parents[3] / "data" / "fantasypros"


# --- helpers ------------------------------------------------------------------------


def slot(name: str, number: int = 1) -> SlotInstance:
    """A slot instance built from the real eligibility map, not a hand-typed set."""
    return SlotInstance(id=f"{name}.{number}", name=name, eligible=SLOT_ELIGIBILITY[name])


def player(
    pid: str,
    position: Position = Position.RB,
    points: float = 100.0,
    adp: float | None = None,
) -> Player:
    return Player(
        player_id=pid,
        name=f"Player {pid}",
        position=position,
        points=points,
        # `sd` is irrelevant to every number in this module — only the ADP *order*
        # matters — but `AdpEstimate` rejects a non-positive one, correctly.
        adp=None if adp is None else AdpEstimate(adp=adp, sd=1.0),
    )


def config_of(slot_names: list[str], teams: int = 2, rounds: int = 3) -> LeagueConfig:
    """A config built directly, so a test can use a slot layout Sleeper never sends."""
    return LeagueConfig(
        teams=teams,
        rounds=rounds,
        reversal_round=0,
        starter_slots=tuple(slot(name, i + 1) for i, name in enumerate(slot_names)),
        bench_count=0,
    )


@pytest.fixture(scope="module")
def league_config() -> LeagueConfig:
    """The real league: 10 teams, 16 rounds, 9 ranked starter slots."""
    league = json.loads((FIXTURES / "sleeper_league.json").read_text(encoding="utf-8"))
    draft: dict[str, Any] = json.loads(
        (FIXTURES / "sleeper_draft.json").read_text(encoding="utf-8")
    )
    return LeagueConfig.from_sleeper(league, draft)


# --- draft demand ---------------------------------------------------------------------


def test_draft_demand_counts_positions_inside_the_window() -> None:
    """teams 2 x rounds 3 = a 6-pick window; the 7th-best ADP is outside it."""
    pool = [
        player("a", Position.QB, adp=1.0),
        player("b", Position.RB, adp=2.0),
        player("c", Position.QB, adp=3.0),
        player("d", Position.WR, adp=4.0),
        player("e", Position.RB, adp=5.0),
        player("f", Position.TE, adp=6.0),
        player("g", Position.QB, adp=7.0),
        player("h", Position.WR, adp=8.0),
    ]

    demand = draft_demand(pool, config_of(["QB"], teams=2, rounds=3))

    assert dict(demand) == {Position.QB: 2, Position.RB: 2, Position.WR: 1, Position.TE: 1}
    assert sum(demand.values()) == 6


def test_draft_demand_uses_adp_order_not_pool_order() -> None:
    """The pool arrives in consensus order; the window is the *market's* top picks.

    If this read pool order instead of ADP, the two QBs at the front would be counted and
    the answer would be 2, not 0.
    """
    pool = [
        player("qb1", Position.QB, adp=90.0),
        player("qb2", Position.QB, adp=91.0),
        player("rb1", Position.RB, adp=1.0),
        player("rb2", Position.RB, adp=2.0),
    ]

    demand = draft_demand(pool, config_of(["RB"], teams=1, rounds=2))

    assert demand[Position.QB] == 0
    assert demand[Position.RB] == 2


def test_draft_demand_never_reports_def_or_k() -> None:
    """DEF and K occupy real picks but are never ranked, so they never enter the window."""
    pool = [
        player("def1", Position.DEF, adp=1.0),
        player("k1", Position.K, adp=2.0),
        player("rb1", Position.RB, adp=3.0),
        player("wr1", Position.WR, adp=4.0),
    ]

    demand = draft_demand(pool, config_of(["RB"], teams=1, rounds=2))

    assert set(demand) == RANKED_POSITIONS
    assert dict(demand) == {Position.QB: 0, Position.RB: 1, Position.WR: 1, Position.TE: 0}


def test_draft_demand_raises_when_a_window_player_has_no_adp() -> None:
    """Skipping him would understate his position; counting him would invent a market."""
    pool = [
        player("a", Position.RB, adp=1.0),
        player("b", Position.WR, adp=2.0),
        player("unpriced", Position.QB),
    ]

    with pytest.raises(ImportDataError, match="no ADP"):
        draft_demand(pool, config_of(["RB"], teams=1, rounds=3))


def test_draft_demand_tolerates_missing_adp_outside_the_window() -> None:
    """Consensus order is the documented fallback, and outside the window it is harmless.

    Players 200 picks deep have no market price and never will; only the window matters.
    """
    pool = [
        player("a", Position.RB, adp=1.0),
        player("b", Position.WR, adp=2.0),
        player("deep1", Position.QB),
        player("deep2", Position.TE),
    ]

    demand = draft_demand(pool, config_of(["RB"], teams=1, rounds=2))

    assert dict(demand) == {Position.QB: 0, Position.RB: 1, Position.WR: 1, Position.TE: 0}


def test_draft_demand_raises_on_a_pool_smaller_than_the_draft() -> None:
    """A truncated pool would understate demand and lift every replacement level."""
    pool = [player("a", Position.RB, adp=1.0), player("b", Position.WR, adp=2.0)]

    with pytest.raises(ImportDataError, match="truncated"):
        draft_demand(pool, config_of(["RB"], teams=2, rounds=3))


# --- starter demand -------------------------------------------------------------------


def test_starter_demand_fills_every_slot_when_the_pool_is_deep() -> None:
    """9 ranked slots x 10 teams = 90 starters, no more and no fewer."""
    pool = [
        player(f"{position}{i}", position, points=float(500 - i))
        for position in RANKED_POSITIONS
        for i in range(40)
    ]

    demand = starter_demand(pool, config_of(["QB", "RB", "WR", "FLEX", "SUPER_FLEX"], teams=4))

    assert sum(demand.values()) == 5 * 4


def test_starter_demand_sends_the_superflex_to_qbs_when_qbs_score_more() -> None:
    """The superflex premium is derived from points, never asserted.

    One QB slot and one SUPER_FLEX per team, QBs outscoring everyone: both go to QBs, so
    QB starter demand is 2x teams. Nothing in the code says "superflex means QB".
    """
    pool = [player(f"qb{i}", Position.QB, points=float(400 - i)) for i in range(10)] + [
        player(f"rb{i}", Position.RB, points=float(200 - i)) for i in range(10)
    ]

    demand = starter_demand(pool, config_of(["QB", "RB", "SUPER_FLEX"], teams=3))

    assert demand[Position.QB] == 6
    assert demand[Position.RB] == 3


def test_starter_demand_leaves_the_superflex_to_a_flex_position_when_qbs_are_thin() -> None:
    """The mirror image: only two QBs exist league-wide, so WRs take all three SUPER_FLEX.

    Three teams, each with QB / WR / SUPER_FLEX. The two QBs start; one QB slot stays
    empty and cannot be back-filled, while WRs fill 3 WR slots and all 3 SUPER_FLEX.
    """
    pool = [player(f"qb{i}", Position.QB, points=float(400 - i)) for i in range(2)] + [
        player(f"wr{i}", Position.WR, points=float(200 - i)) for i in range(10)
    ]

    demand = starter_demand(pool, config_of(["QB", "WR", "SUPER_FLEX"], teams=3))

    assert demand[Position.QB] == 2
    assert demand[Position.WR] == 6


def test_starter_demand_ignores_def_and_k() -> None:
    """A DEF outscoring every RB must not take a FLEX slot it is not eligible for."""
    pool = [
        player("def1", Position.DEF, points=9999.0),
        player("k1", Position.K, points=9999.0),
        player("rb1", Position.RB, points=100.0),
        player("wr1", Position.WR, points=90.0),
    ]

    demand = starter_demand(pool, config_of(["FLEX"], teams=1))

    assert set(demand) == RANKED_POSITIONS
    assert dict(demand) == {Position.QB: 0, Position.RB: 1, Position.WR: 0, Position.TE: 0}


def test_starter_demand_raises_on_a_duplicate_player_id() -> None:
    """The allocation is keyed by id; a duplicate would silently drop one of the two."""
    pool = [player("same", Position.RB, points=200.0), player("same", Position.WR, points=190.0)]

    with pytest.raises(ImportDataError, match="duplicate player_id 'same'"):
        starter_demand(pool, config_of(["FLEX"], teams=1))


def test_starter_demand_raises_when_it_would_exceed_draft_demand() -> None:
    """A position cannot be started league-wide more often than it is drafted.

    Forced here by a league that starts 6 players out of a 4-pick draft — nonsense, but
    exactly the shape a mis-parsed `rounds` would produce, and it must not compute
    quietly. The check is in the module, not only in this test.
    """
    pool = [
        player("rb1", Position.RB, points=200.0, adp=1.0),
        player("rb2", Position.RB, points=190.0, adp=2.0),
        player("rb3", Position.RB, points=180.0, adp=3.0),
        player("rb4", Position.RB, points=170.0, adp=4.0),
        player("rb5", Position.RB, points=160.0, adp=5.0),
        player("rb6", Position.RB, points=150.0, adp=6.0),
    ]

    with pytest.raises(ImportDataError, match="exceeds draft demand"):
        starter_demand(pool, config_of(["RB", "FLEX", "SUPER_FLEX"], teams=2, rounds=2))


def test_starter_demand_skips_the_cross_check_without_enough_adp() -> None:
    """The ADP-free path is the documented degraded mode; it must still produce a number."""
    pool = [player(f"rb{i}", Position.RB, points=float(200 - i)) for i in range(10)]

    demand = starter_demand(pool, config_of(["RB", "FLEX"], teams=2, rounds=3))

    assert demand[Position.RB] == 4


# --- the greedy allocation, against a brute-force oracle ------------------------------


def _oracle_starter_counts(
    pool: list[Player], slots: tuple[SlotInstance, ...]
) -> dict[Position, int]:
    """Exhaustive maximum-weight allocation, sharing no code with the implementation.

    Enumerates every injective assignment of players to slots. Points are distinct in the
    property test, so the maximum-weight selection is unique and its position counts are
    well defined.
    """
    best_total = -1.0
    best_counts: dict[Position, int] = dict.fromkeys(RANKED_POSITIONS, 0)

    for size in range(min(len(pool), len(slots)) + 1):
        for chosen in itertools.combinations(pool, size):
            feasible = any(
                all(
                    slots[slot_index].accepts(chosen[i].position)
                    for i, slot_index in enumerate(slot_indices)
                )
                for slot_indices in itertools.permutations(range(len(slots)), size)
            )
            total = sum(p.points for p in chosen)
            if feasible and total > best_total:
                best_total = total
                counts = dict.fromkeys(RANKED_POSITIONS, 0)
                for p in chosen:
                    counts[p.position] += 1
                best_counts = counts

    return best_counts


def test_starter_demand_matches_a_brute_force_oracle() -> None:
    """Greedy over raw points is exact here because every slot values a player equally.

    That is the transversal-matroid argument from decision 10, and this is the test that
    holds it up. It does **not** generalise to `lineup.py`, whose slots floor at their own
    replacement levels — reusing this shortcut there is a 397-point error.
    """
    rng = random.Random(20260801)
    names = [name for name in SLOT_ELIGIBILITY if name not in {"DEF", "K"}]
    positions = sorted(RANKED_POSITIONS)

    for _ in range(200):
        slot_names = [rng.choice(names) for _ in range(rng.randint(1, 3))]
        config = config_of(slot_names, teams=rng.randint(1, 2), rounds=3)
        slots = tuple(config.ranked_starter_slots) * config.teams

        points = rng.sample(range(50, 400), rng.randint(1, 6))
        pool = [
            player(f"p{i}", rng.choice(positions), points=float(value))
            for i, value in enumerate(points)
        ]

        assert dict(starter_demand(pool, config)) == _oracle_starter_counts(pool, slots), (
            f"slots={slot_names} x{config.teams} "
            f"pool={[(p.player_id, p.position, p.points) for p in pool]}"
        )


# --- replacement levels ---------------------------------------------------------------


def test_replacement_level_is_the_demand_plus_one_player() -> None:
    """Demand 2 at RB means the third-best RB is what you get for free."""
    pool = [player(f"rb{i}", Position.RB, points=float(300 - 10 * i)) for i in range(5)]
    pool += [player(f"wr{i}", Position.WR, points=float(200 - 10 * i)) for i in range(5)]
    pool += [player("qb1", Position.QB, points=50.0), player("te1", Position.TE, points=40.0)]

    levels = replacement_levels(
        pool,
        {Position.QB: 0, Position.RB: 2, Position.WR: 1, Position.TE: 0},
    )

    assert levels[Position.RB] == 280.0
    assert levels[Position.WR] == 190.0
    assert levels[Position.QB] == 50.0
    assert levels[Position.TE] == 40.0


def test_replacement_levels_never_report_def_or_k() -> None:
    pool = [
        player("def1", Position.DEF, points=999.0),
        player("qb1", Position.QB, points=300.0),
        player("rb1", Position.RB, points=200.0),
        player("wr1", Position.WR, points=190.0),
        player("te1", Position.TE, points=180.0),
    ]

    levels = replacement_levels(pool, dict.fromkeys(RANKED_POSITIONS, 0))

    assert set(levels) == RANKED_POSITIONS


def test_replacement_levels_raise_on_a_truncated_position() -> None:
    """Two QBs and a demand of 2 means QB3 does not exist — and QB3 *is* the baseline.

    Falling back to "the worst one we have" would make every QB look free.
    """
    pool = [
        player("qb1", Position.QB, points=300.0),
        player("qb2", Position.QB, points=290.0),
        player("rb1", Position.RB, points=200.0),
        player("wr1", Position.WR, points=190.0),
        player("te1", Position.TE, points=180.0),
    ]

    with pytest.raises(ImportDataError, match="pool holds only 2"):
        replacement_levels(pool, {Position.QB: 2, Position.RB: 0, Position.WR: 0, Position.TE: 0})


def test_replacement_levels_raise_on_a_demand_for_an_unranked_position() -> None:
    pool = [player("rb1", Position.RB, points=200.0)]

    with pytest.raises(ImportDataError, match="unranked position"):
        replacement_levels(pool, {Position.DEF: 1, Position.RB: 0})


def test_replacement_levels_raise_on_a_missing_position() -> None:
    pool = [player("rb1", Position.RB, points=200.0)]

    with pytest.raises(ImportDataError, match="no demand given for QB"):
        replacement_levels(pool, {Position.RB: 0})


# --- the pinned FantasyPros data ------------------------------------------------------


def _normalise(name: str) -> str:
    """Throwaway name key for this file only. `ingest/matching.py` owns the real one."""
    stripped = re.sub(r"\b(jr|sr|ii|iii|iv|v)\.?\b", "", name.strip().lower())
    return " ".join(re.sub(r"[^a-z ]", "", stripped).split())


def _projected_players() -> dict[str, Player]:
    """Every projected player, keyed by normalised name. FPTS is the last column."""
    players: dict[str, Player] = {}
    for position in (Position.QB, Position.RB, Position.WR, Position.TE):
        path = DATA / f"FantasyPros_Fantasy_Football_Projections_{position}.csv"
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle))
        width = len(rows[0])
        for row in rows[1:]:
            if len(row) < width or not row[0].strip():
                continue  # the blank spacer row the export writes under the header
            key = _normalise(row[0])
            players[key] = Player(
                player_id=f"{position}-{key}",
                name=row[0].strip(),
                position=position,
                points=float(row[width - 1].replace(",", "")),
            )
    return players


def _superflex_adp(*, both_sources_only: bool) -> dict[str, float]:
    """`AVG` from the superflex ADP export, keyed by normalised name.

    `both_sources_only` drops rows where one of the two platform columns is a dash. Those
    averages are a single platform's opinion wearing a consensus label, and they are the
    entire difference between `QB = 32` and `QB = 33` — see the two tests below.
    """
    adp: dict[str, float] = {}
    with (DATA / "FantasyPros_2026_Superflex_ADP_Rankings.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        for row in csv.DictReader(handle):
            sources = (row["Sleeper"].strip(), row["FFPC"].strip())
            if both_sources_only and any(not value or value in {"-", "—"} for value in sources):
                continue
            name = re.sub(r"\s+[A-Z]{2,3}\s*\(\d+\)\s*$", "", row["Player (Bye)"].strip())
            adp[_normalise(name)] = float(row["AVG"])
    return adp


def _pinned_pool(*, both_sources_only: bool = True) -> list[Player]:
    players = _projected_players()
    adp = _superflex_adp(both_sources_only=both_sources_only)
    return [
        p if key not in adp else replace(p, adp=AdpEstimate(adp=adp[key], sd=1.0))
        for key, p in players.items()
    ]


@pytest.fixture(scope="module")
def pinned_pool() -> list[Player]:
    return _pinned_pool()


def test_the_pinned_export_still_holds_what_these_tests_assume(pinned_pool: list[Player]) -> None:
    """Guardrail: if the exports are re-pulled, this fails before the numbers below do.

    518, not 519: Connor Heyward is projected in both the RB and the TE export, and this
    reader keys by name so he counts once. That duplicate is `ingest`'s problem, not this
    module's — it is named here so the count is not read as a coincidence.
    """
    assert len(pinned_pool) == 518
    assert sum(1 for p in pinned_pool if p.adp is not None) >= 160


def test_draft_demand_on_the_pinned_data_is_32_qbs(
    pinned_pool: list[Player], league_config: LeagueConfig
) -> None:
    """The number decision 2 was made on, measured on real superflex market ADP.

    32 QBs inside 160 picks is why punting QB leaves you QB33, not QB21.
    """
    demand = draft_demand(pinned_pool, league_config)

    assert demand[Position.QB] == 32
    assert sum(demand.values()) == league_config.total_picks == 160
    assert set(demand) == RANKED_POSITIONS


def test_single_source_adp_rows_inflate_qb_draft_demand_to_33() -> None:
    """A documented disagreement with the plan, not a tolerance.

    The export's `AVG` column is a mean over the platforms that list a player. Three rows
    in this export carry one platform only — Ty Simpson (Sleeper 120, FFPC absent), Greg
    Dulcich and Trey Benson — and their averages therefore jump ~60 places ahead of
    FantasyPros' own published overall rank for the same row. Sorting the raw `AVG` column
    pulls Ty Simpson into the top 160 and reports 33 QBs; FantasyPros' own row order, and
    the two-source subset, both report 32.

    This module cannot see source coverage — it sees one float per player — so the choice
    belongs in `ingest`. Pinned here so that whichever way it is resolved, it is resolved
    deliberately.
    """
    league = json.loads((FIXTURES / "sleeper_league.json").read_text(encoding="utf-8"))
    draft = json.loads((FIXTURES / "sleeper_draft.json").read_text(encoding="utf-8"))
    config = LeagueConfig.from_sleeper(league, draft)

    demand = draft_demand(_pinned_pool(both_sources_only=False), config)

    assert demand[Position.QB] == 33


def test_starter_demand_on_the_pinned_data(
    pinned_pool: list[Player], league_config: LeagueConfig
) -> None:
    """20 / 31 / 29 / 10 — a 90-starter league, allocated with no assumed share.

    All 10 SUPER_FLEX slots go to QBs and the contest is not close: QB20 projects 274.5
    against 164.0 for the best flex-eligible alternative. The result is computed, not
    hardcoded, so it self-corrects if the projections move.
    """
    demand = starter_demand(pinned_pool, league_config)

    assert dict(demand) == {
        Position.QB: 20,
        Position.RB: 31,
        Position.WR: 29,
        Position.TE: 10,
    }
    assert sum(demand.values()) == len(league_config.ranked_starter_slots) * league_config.teams


def test_starter_demand_never_exceeds_draft_demand_on_the_pinned_data(
    pinned_pool: list[Player], league_config: LeagueConfig
) -> None:
    starters = starter_demand(pinned_pool, league_config)
    drafted = draft_demand(pinned_pool, league_config)

    assert all(starters[position] <= drafted[position] for position in RANKED_POSITIONS)


def test_replacement_levels_on_the_pinned_data_use_draft_demand(
    pinned_pool: list[Player], league_config: LeagueConfig
) -> None:
    """`r_QB` is QB33, not QB21. This is the test with teeth.

    Swap `draft_demand` for `starter_demand` in `replacement_levels`' caller and `r_QB`
    jumps from 108.9 to 269.6 — a 160.7-point error applied to every QB on the board, and
    the reason the two demand numbers are separate functions.
    """
    levels = replacement_levels(pinned_pool, draft_demand(pinned_pool, league_config))

    assert levels[Position.QB] == pytest.approx(108.9)
    assert levels[Position.RB] == pytest.approx(92.1)
    assert levels[Position.WR] == pytest.approx(118.2)
    assert levels[Position.TE] == pytest.approx(100.1)


def test_the_two_bases_disagree_by_160_points_at_qb(
    pinned_pool: list[Player], league_config: LeagueConfig
) -> None:
    """The sensitivity band the UI must show, and its size.

    Starter demand says a replacement QB projects 269.6 — a genuine starter — and produces
    a board reading "essentially never draft a QB" in a superflex league. Draft demand says
    108.9, because 32 QBs really do come off the board in 160 picks.
    """
    on_draft = replacement_levels(pinned_pool, draft_demand(pinned_pool, league_config))
    on_starters = replacement_levels(pinned_pool, starter_demand(pinned_pool, league_config))

    assert on_starters[Position.QB] == pytest.approx(269.6)
    assert on_starters[Position.QB] - on_draft[Position.QB] == pytest.approx(160.7)


# --- LEG-1 ----------------------------------------------------------------------------


def test_leg1_fudged_slot_counts_model_a_league_that_does_not_exist(
    pinned_pool: list[Player], league_config: LeagueConfig
) -> None:
    """The 2025 settings form: `qb=2, rb=3, wr=3, te=1, flex=3`, per-position integers.

    Integer columns cannot express SUPER_FLEX, so the user fudged them to something that
    "felt right". Re-run through the same allocation those numbers model **120** starters
    in a 90-starter league, and the replacement levels they produce are ~30 points wrong
    for RB and WR — in a metric whose whole top-15 spread is about 90 points.

    This is why a slot is a set of eligible positions with a count, and never a column.
    """
    fudged = LeagueConfig(
        teams=league_config.teams,
        rounds=league_config.rounds,
        reversal_round=league_config.reversal_round,
        starter_slots=tuple(
            slot(name, i + 1)
            for i, name in enumerate(["QB"] * 2 + ["RB"] * 3 + ["WR"] * 3 + ["TE"] + ["FLEX"] * 3)
        ),
        bench_count=0,
    )

    real = starter_demand(pinned_pool, league_config)
    wrong = starter_demand(pinned_pool, fudged)

    assert sum(real.values()) == 90
    assert sum(wrong.values()) == 120
    assert dict(wrong) == {
        Position.QB: 20,
        Position.RB: 38,
        Position.WR: 49,
        Position.TE: 13,
    }

    real_levels = replacement_levels(pinned_pool, real)
    wrong_levels = replacement_levels(pinned_pool, wrong)

    assert real_levels[Position.RB] - wrong_levels[Position.RB] == pytest.approx(29.2)
    assert real_levels[Position.WR] - wrong_levels[Position.WR] == pytest.approx(31.4)
    # The QB count coincides — 2 fixed slots x 10 teams also equals 20 — which is exactly
    # how a fudged setting survives a season unnoticed. It is right for the wrong reason:
    # remove SUPER_FLEX and a 3rd QB is never startable, so the agreement is luck.
    assert real_levels[Position.QB] == wrong_levels[Position.QB]
