"""Tests for the Phase 2 shared vocabulary: `AdpEstimate`, `Player`, `PlayerPool`.

The centre of gravity is `PlayerPool.available()`. It is the one place a board that has
drifted out of sync with Sleeper becomes visible, so it asserts rather than filters — a
drafted id we cannot account for means a player is silently still shown as available.
"""

import pytest

from popacta.domain.errors import InvalidPlayerError
from popacta.domain.players import AdpEstimate, Player, PlayerPool
from popacta.domain.positions import Position


def player(pid: str, position: Position = Position.RB, points: float = 200.0) -> Player:
    return Player(player_id=pid, name=f"Player {pid}", position=position, points=points)


# --- AdpEstimate ----------------------------------------------------------------------


def test_a_valid_adp_estimate_is_accepted() -> None:
    adp = AdpEstimate(adp=12.0, sd=5.0)

    assert adp.adp == 12.0
    assert adp.sd == 5.0


@pytest.mark.parametrize("sd", [0.0, -1.0])
def test_a_non_positive_std_dev_raises(sd: float) -> None:
    """No real ADP sample has zero variance; a 0 means an empty cell or a bad parse.

    It would also divide by zero in the survival model. Fail at import, not at draft time.
    """
    with pytest.raises(InvalidPlayerError, match="sd must be positive"):
        AdpEstimate(adp=12.0, sd=sd)


@pytest.mark.parametrize("adp", [0.0, -3.0])
def test_a_non_positive_adp_raises(adp: float) -> None:
    with pytest.raises(InvalidPlayerError, match="adp must be positive"):
        AdpEstimate(adp=adp, sd=5.0)


def test_a_small_but_real_std_dev_is_legitimate() -> None:
    """Consensus on pick 1.01 really is that tight. Near-step behaviour is correct."""
    assert AdpEstimate(adp=1.5, sd=0.4).sd == 0.4


# --- Player ---------------------------------------------------------------------------


def test_ranked_positions_are_ranked() -> None:
    for position in (Position.QB, Position.RB, Position.WR, Position.TE):
        assert player("x", position).is_ranked


def test_defenses_and_kickers_are_not_ranked() -> None:
    """They parse and occupy picks; they are never projected or recommended."""
    assert not player("SF", Position.DEF).is_ranked
    assert not player("k1", Position.K).is_ranked


def test_player_is_immutable() -> None:
    with pytest.raises(AttributeError):
        player("p1").points = 999.0  # type: ignore[misc]


# --- PlayerPool.available -------------------------------------------------------------


@pytest.fixture
def pool() -> PlayerPool:
    return PlayerPool(
        players={f"p{i}": player(f"p{i}") for i in range(1, 6)},
        excluded_ids=frozenset({"SF", "KC"}),
    )


def test_available_excludes_drafted_players(pool: PlayerPool) -> None:
    remaining = pool.available({"p2", "p4"})

    assert [p.player_id for p in remaining] == ["p1", "p3", "p5"]


def test_available_with_nothing_drafted_returns_everyone(pool: PlayerPool) -> None:
    assert len(pool.available(set())) == 5


def test_a_drafted_defense_is_accepted_and_not_returned(pool: PlayerPool) -> None:
    """Nine other teams draft defenses; those picks arrive and must not break anything."""
    remaining = pool.available({"p1", "SF"})

    assert [p.player_id for p in remaining] == ["p2", "p3", "p4", "p5"]


def test_an_unaccountable_drafted_id_raises(pool: PlayerPool) -> None:
    """The board is out of sync with Sleeper — the one failure that must never be silent.

    Filtering instead of raising leaves a drafted player showing as available, which is
    exactly the draft-night outcome OPEN-1 exists to prevent.
    """
    with pytest.raises(InvalidPlayerError, match="out of sync"):
        pool.available({"p1", "who_is_this"})


def test_available_does_not_mutate_the_pool(pool: PlayerPool) -> None:
    pool.available({"p1", "p2"})

    assert len(pool.players) == 5


# --- PlayerPool construction ----------------------------------------------------------


def test_a_pool_cannot_both_rank_and_exclude_an_id() -> None:
    with pytest.raises(InvalidPlayerError, match="both ranked and excluded"):
        PlayerPool(players={"p1": player("p1")}, excluded_ids=frozenset({"p1"}))


def test_the_pool_mapping_is_read_only() -> None:
    pool = PlayerPool(players={"p1": player("p1")})

    with pytest.raises(TypeError):
        pool.players["p2"] = player("p2")  # type: ignore[index]


def test_the_pool_copies_its_input() -> None:
    """Mutating the dict you passed in must not change the pool."""
    source = {"p1": player("p1")}
    pool = PlayerPool(players=source)

    source["p2"] = player("p2")

    assert set(pool.players) == {"p1"}


def test_ranked_and_by_position_filter_correctly() -> None:
    pool = PlayerPool(
        players={
            "qb": player("qb", Position.QB),
            "rb": player("rb", Position.RB),
            "def": player("def", Position.DEF),
        }
    )

    assert {p.player_id for p in pool.ranked()} == {"qb", "rb"}
    assert [p.player_id for p in pool.by_position(Position.QB)] == ["qb"]
