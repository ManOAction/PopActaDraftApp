# app/services/vorp.py
from statistics import mean
from typing import Dict, List

from sqlalchemy.orm import Session

from ..models import DraftSettings, Player


def _sorted_pool(db: Session, where) -> List[Player]:
    return db.query(Player).filter(where).order_by(Player.projected_points.desc()).all()


def _count_drafted(db: Session, pos: str) -> int:
    return db.query(Player).filter(Player.position == pos, Player.drafted_status == True).count()


def compute_vorp_drop(db: Session, k: int = 6) -> Dict[int, float]:
    """Return {player_id: drop} for positions that still have starter slots to fill."""
    s: DraftSettings | None = db.query(DraftSettings).first()
    if not s:
        return {}

    # Remaining starters needed per position
    need_qb = s.total_teams * s.qb_slots - _count_drafted(db, "QB")
    need_rb = s.total_teams * s.rb_slots - _count_drafted(db, "RB")
    need_wr = s.total_teams * s.wr_slots - _count_drafted(db, "WR")

    # Flex: RB/WR surplus can satisfy flex slots
    drafted_rb = _count_drafted(db, "RB")
    drafted_wr = _count_drafted(db, "WR")
    surplus_rb = max(0, drafted_rb - s.total_teams * s.rb_slots)
    surplus_wr = max(0, drafted_wr - s.total_teams * s.wr_slots)
    need_flex = max(0, s.total_teams * s.flex_slots - (surplus_rb + surplus_wr))

    out: Dict[int, float] = {}

    def fill_for_position(pos: str, need_pos: int):
        if need_pos <= 0:
            return
        pool = _sorted_pool(db, Player.position == pos)
        n = len(pool)
        for i, p in enumerate(pool):
            # Lookahead next k players at SAME position
            nxt = pool[i + 1 : i + 1 + k]
            if not nxt:
                continue
            out[p.id] = float(p.projected_points - mean([x.projected_points for x in nxt]))

    # Apply for positions where starters still needed
    fill_for_position("QB", need_qb)
    fill_for_position("RB", need_rb)
    fill_for_position("WR", need_wr)

    # Optional: a FLEX view that treats RB+WR together (useful if you want a flex-specific score)
    if need_flex > 0:
        pool = _sorted_pool(db, Player.position.in_(["RB", "WR"]))
        for i, p in enumerate(pool):
            nxt = pool[i + 1 : i + 1 + k]
            if not nxt:
                continue
            out.setdefault(p.id, float(p.projected_points - mean([x.projected_points for x in nxt])))

    return out
