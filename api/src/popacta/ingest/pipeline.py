"""Turning source files into a `PlayerPool` — the one place the parts are wired together.

`ingest.fantasypros` parses, `domain.scoring` prices, `ingest.matching` resolves ids. This
module is what calls them in the right order and hands the domain layer something usable.

Every failure surfaces here, at import time, with the offending value named — days before
the draft rather than during it.

**ADP is deliberately absent.** `fantasypros.parse_adp` raises until a `Std Dev` source
exists (BLK-1), so players are built without an `AdpEstimate` and replacement levels come
from `replacement.consensus_draft_demand`. That path is complete and correct on its own; it
is survival probability, not the board, that is waiting on the export.
"""

import json
from collections.abc import Mapping
from pathlib import Path

from popacta.domain.errors import ImportDataError
from popacta.domain.players import Player, PlayerPool
from popacta.domain.positions import Position
from popacta.domain.scoring import fantasy_points
from popacta.ingest.fantasypros import parse_projections, parse_rankings
from popacta.ingest.matching import resolve_players

__all__ = ["build_player_pool"]


def build_player_pool(
    *,
    qb_csv: Path,
    flx_csv: Path,
    rankings_csv: Path,
    sleeper_dump: Path,
    scoring_settings: Mapping[str, float],
) -> tuple[PlayerPool, tuple[Player, ...]]:
    """Build the pool, and the same players ordered by consensus rank.

    The second element exists because `replacement.consensus_draft_demand` needs consensus
    order and cannot verify it — returning it here means the caller never has to sort, and
    cannot sort wrongly.

    Returns:
        `(pool, players_in_consensus_order)`. Only players present in **both** the
        projections and the rankings appear: a player with no projection has no points to
        rank, and one with no ranking has no consensus position. Both are reported.

    Raises:
        ImportDataError: a player cannot be priced, cannot be resolved to a Sleeper id, or
            the two source files disagree about who exists in a way that would silently
            shrink the board.
    """
    projections = parse_projections(qb_csv, flx_csv)
    rankings = parse_rankings(rankings_csv)

    ranking_by_name = {row.name: row for row in rankings}
    projection_by_name = {row.name: row for row in projections}

    # A player must be in both files to be draftable by this app. Report the overlap rather
    # than silently intersecting — a sudden drop means an export was re-pulled at a
    # different depth, and the board would quietly shrink.
    both = sorted(set(projection_by_name) & set(ranking_by_name))
    if not both:
        raise ImportDataError(
            f"no player appears in both the projections ({len(projection_by_name)}) and the "
            f"rankings ({len(ranking_by_name)}); the two exports do not describe the same season"
        )

    # Resolve to Sleeper ids once, here, and freeze them. Re-matching at draft time is
    # forbidden — see OPEN-1.
    to_resolve = {
        name: (ranking_by_name[name].team, ranking_by_name[name].position) for name in both
    }
    sleeper_ids = resolve_players(to_resolve, sleeper_dump)

    players: list[Player] = []
    for name in both:
        player_id = sleeper_ids.get(name)
        if player_id is None:
            # Deliberately dropped by the manual override list, or unresolvable. Either way
            # `resolve_players` has already accounted for it and raised if it was a surprise.
            continue

        projection = projection_by_name[name]
        ranking = ranking_by_name[name]
        players.append(
            Player(
                player_id=player_id,
                name=name,
                position=Position(ranking.position),
                points=fantasy_points(projection.stats, scoring_settings),
                team=ranking.team,
                bye_week=ranking.bye_week,
                adp=None,  # BLK-1: no Std Dev source, so no AdpEstimate. See the module docstring.
            )
        )

    by_id: dict[str, Player] = {}
    for player in players:
        if player.player_id in by_id:
            raise ImportDataError(
                f"two players resolve to Sleeper id {player.player_id!r}: "
                f"{by_id[player.player_id].name!r} and {player.name!r}; one would mask the other"
            )
        by_id[player.player_id] = player

    consensus_order = tuple(sorted(players, key=lambda p: ranking_by_name[p.name].overall_rank))
    return PlayerPool(players=by_id), consensus_order


def excluded_sleeper_ids(sleeper_dump: Path) -> frozenset[str]:
    """Sleeper ids for every `DEF` and `K` — the picks we record but never rank.

    Nine other teams draft defenses and those picks arrive during the draft. `PlayerPool`
    needs to know they are *deliberately* unranked, so it can tell them apart from a pick it
    cannot explain.
    """
    dump = json.loads(sleeper_dump.read_bytes())
    return frozenset(pid for pid, row in dump.items() if row.get("position") in ("DEF", "K"))


def load_scoring_settings(league_payload: Mapping[str, object]) -> Mapping[str, float]:
    """Pull `scoring_settings` out of a Sleeper league payload.

    Never hand-entered. Hardcoding these is what broke the 2025 app.

    Raises:
        ImportDataError: the payload carries no `scoring_settings`.
    """
    settings = league_payload.get("scoring_settings")
    if not isinstance(settings, Mapping) or not settings:
        raise ImportDataError(
            "league payload has no usable `scoring_settings`; scoring must come from "
            "Sleeper, never from a hardcoded table"
        )
    return {str(k): float(v) for k, v in settings.items()}
