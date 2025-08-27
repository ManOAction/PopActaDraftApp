# app/services/vorp.py
from statistics import mean
from typing import Dict, Iterable, List

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import DraftSettings, Player


def _sorted_pool(db: Session, where) -> List[Player]:
    return db.query(Player).filter(where).order_by(Player.projected_points.desc()).all()


def _count_drafted(db: Session, pos: str) -> int:
    # Drafted = actual_pick_number is not NULL
    return db.query(Player).filter(Player.position == pos, Player.actual_pick_number.isnot(None)).count()


def _sum_projected(points: Iterable[Player]) -> float:
    return sum(p.projected_points for p in points if p.projected_points is not None)


def compute_vorp_drop(db: Session, k: int = 6) -> Dict[int, float]:
    """
    Returns {player_id: drop} where drop = projected - avg(projected of next k at same pool).
    Pools include QB, RB, WR, TE (by position), plus a FLEX pool (RB/WR/QB).
    Only positions with remaining *starter* slots contribute position-specific drops.
    FLEX contributes if FLEX slots remain after applying RB/WR/QB surpluses.
    """
    s: DraftSettings | None = db.query(DraftSettings).first()
    if not s:
        return {}

    # Read slot config (TE may not exist yet -> treat as 0)
    teams = s.total_teams
    qb_slots = getattr(s, "qb_slots", 0)
    rb_slots = getattr(s, "rb_slots", 0)
    wr_slots = getattr(s, "wr_slots", 0)
    te_slots = getattr(s, "te_slots", 0)  # NEW (defensive default = 0)
    flex_slots = getattr(s, "flex_slots", 0)

    total_needed_qb = teams * qb_slots
    total_needed_rb = teams * rb_slots
    total_needed_wr = teams * wr_slots
    total_needed_te = teams * te_slots
    total_needed_flex = teams * flex_slots

    drafted_qb = _count_drafted(db, "QB")
    drafted_rb = _count_drafted(db, "RB")
    drafted_wr = _count_drafted(db, "WR")
    drafted_te = _count_drafted(db, "TE")

    need_qb = max(0, total_needed_qb - drafted_qb)
    need_rb = max(0, total_needed_rb - drafted_rb)
    need_wr = max(0, total_needed_wr - drafted_wr)
    need_te = max(0, total_needed_te - drafted_te)

    # FLEX eligibility now includes QB as requested
    flex_eligible_positions = ("RB", "WR", "QB")

    # Surplus from eligible positions (beyond their locked starters) can satisfy FLEX
    surplus_qb = max(0, drafted_qb - total_needed_qb) if "QB" in flex_eligible_positions else 0
    surplus_rb = max(0, drafted_rb - total_needed_rb) if "RB" in flex_eligible_positions else 0
    surplus_wr = max(0, drafted_wr - total_needed_wr) if "WR" in flex_eligible_positions else 0
    # (TE not included in FLEX by your request; add if you ever want it)
    need_flex = max(0, total_needed_flex - (surplus_qb + surplus_rb + surplus_wr))

    out: Dict[int, float] = {}

    def score_pool(pool: List[Player], store: Dict[int, float]):
        n = len(pool)
        for i, p in enumerate(pool):
            nxt = pool[i + 1 : i + 1 + k]
            if not nxt:
                continue
            # Guard against None projected_points
            if p.projected_points is None:
                continue
            next_points = [x.projected_points for x in nxt if x.projected_points is not None]
            if not next_points:
                continue
            store[p.id] = float(p.projected_points - mean(next_points))

    # Position-specific VORP only if starters still needed at that position
    if need_qb > 0:
        score_pool(_sorted_pool(db, Player.position == "QB"), out)
    if need_rb > 0:
        score_pool(_sorted_pool(db, Player.position == "RB"), out)
    if need_wr > 0:
        score_pool(_sorted_pool(db, Player.position == "WR"), out)
    if need_te > 0:
        score_pool(_sorted_pool(db, Player.position == "TE"), out)

    # FLEX pool (RB/WR/QB together) if FLEX starters still needed
    if need_flex > 0 and flex_eligible_positions:
        pool = _sorted_pool(db, or_(*[Player.position == pos for pos in flex_eligible_positions]))
        score_pool(pool, out)  # don't overwrite existing pos scores; score_pool writes/overwrites by id
        # If you prefer to *not* overwrite position scores with FLEX, use:
        # temp: Dict[int, float] = {}
        # score_pool(pool, temp)
        # for pid, val in temp.items():
        #     out.setdefault(pid, val)

    return out
