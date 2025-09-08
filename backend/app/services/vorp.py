from math import ceil
from statistics import mean
from typing import Dict, List

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import DraftSettings, Player


def _sorted_available_pool(db: Session, where) -> List[Player]:
    """
    Return UNDRAFTED players matching 'where', sorted by projected_points desc.
    Undrafted = actual_pick_number IS NULL.
    """
    return db.query(Player).filter(where, Player.actual_pick_number.is_(None)).order_by(Player.projected_points.desc()).all()


def _count_drafted(db: Session, pos: str) -> int:
    # Drafted = actual_pick_number is not NULL
    return db.query(Player).filter(Player.position == pos, Player.actual_pick_number.isnot(None)).count()


def compute_vorp_drop(db: Session, k: int = 3) -> Dict[str, Dict[int, float]]:
    """
    Replacement-level VORP with separate outputs:

      - pos:  position-only pools (QB/RB/WR/TE) using a replacement baseline at
              50% of remaining starters (ceil(rem * 0.5) - 1), averaged over up to k players.
      - flex: blended FLEX pool (QB+RB+WR+TE) using the same replacement rule.
      - combined: max(pos, flex) per player.

    Returns:
      {
        "pos": {player_id: drop},
        "flex": {player_id: drop},
        "combined": {player_id: drop}
      }
    """
    s: DraftSettings | None = db.query(DraftSettings).first()
    if not s:
        return {"pos": {}, "flex": {}, "combined": {}}

    k = max(1, int(k))
    HALF = 0.5  # 50% of remaining starters for replacement point

    teams = s.total_teams
    qb_slots = getattr(s, "qb_slots", 0)
    rb_slots = getattr(s, "rb_slots", 0)
    wr_slots = getattr(s, "wr_slots", 0)
    te_slots = getattr(s, "te_slots", 0)
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

    # Real remaining starters by position
    rem_qb = max(0, total_needed_qb - drafted_qb)
    rem_rb = max(0, total_needed_rb - drafted_rb)
    rem_wr = max(0, total_needed_wr - drafted_wr)
    rem_te = max(0, total_needed_te - drafted_te)

    # Effective remaining (50% rule)
    need_qb = ceil(rem_qb * HALF)
    need_rb = ceil(rem_rb * HALF)
    need_wr = ceil(rem_wr * HALF)
    need_te = ceil(rem_te * HALF)

    # FLEX eligibility includes all positions
    flex_eligible_positions = ("RB", "WR", "TE")

    # Surplus can satisfy FLEX
    surplus_qb = max(0, drafted_qb - total_needed_qb)
    surplus_rb = max(0, drafted_rb - total_needed_rb)
    surplus_wr = max(0, drafted_wr - total_needed_wr)
    surplus_te = max(0, drafted_te - total_needed_te)
    rem_flex = max(0, total_needed_flex - (surplus_rb + surplus_wr + surplus_te))
    need_flex = ceil(rem_flex * HALF)

    def replacement_baseline(pool: List[Player], remaining_effective: int) -> float | None:
        n = len(pool)
        if n == 0 or remaining_effective <= 0:
            return None
        rep_idx0 = max(0, min(n - 1, remaining_effective - 1))  # 0-based
        window = [p.projected_points for p in pool[rep_idx0 : rep_idx0 + k] if p.projected_points is not None]
        if not window:
            return None
        return float(mean(window))

    def make_drops(pool: List[Player], remaining_effective: int) -> Dict[int, float]:
        drops: Dict[int, float] = {}
        baseline = replacement_baseline(pool, remaining_effective)
        if baseline is None:
            return drops
        for p in pool:
            if p.projected_points is None:
                continue
            drops[p.id] = float(p.projected_points - baseline)
        return drops

    # ----- position-only drops -----
    pos_drops: Dict[int, float] = {}

    if need_qb > 0:
        qb_pool = _sorted_available_pool(db, Player.position == "QB")
        pos_drops.update(make_drops(qb_pool, need_qb))
    if need_rb > 0:
        rb_pool = _sorted_available_pool(db, Player.position == "RB")
        pos_drops.update(make_drops(rb_pool, need_rb))
    if need_wr > 0:
        wr_pool = _sorted_available_pool(db, Player.position == "WR")
        pos_drops.update(make_drops(wr_pool, need_wr))
    if need_te > 0:
        te_pool = _sorted_available_pool(db, Player.position == "TE")
        pos_drops.update(make_drops(te_pool, need_te))

    # ----- flex drops (blended pool) -----
    flex_drops: Dict[int, float] = {}
    if need_flex > 0:
        flex_pool = _sorted_available_pool(db, or_(*[Player.position == pos for pos in flex_eligible_positions]))
        flex_drops = make_drops(flex_pool, need_flex)

    # ----- combined = max(pos, flex) -----
    combined: Dict[int, float] = {}
    for pid in set(list(pos_drops.keys()) + list(flex_drops.keys())):
        p = pos_drops.get(pid)
        f = flex_drops.get(pid)
        if p is None:
            combined[pid] = f  # type: ignore
        elif f is None:
            combined[pid] = p
        else:
            combined[pid] = max(p, f)

    return {"pos": pos_drops, "flex": flex_drops, "combined": combined}
