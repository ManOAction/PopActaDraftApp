# app/models.py
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.ext.hybrid import hybrid_property

from .database import Base


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("name", "position", "team", name="uq_players_identity"),
        Index("ix_players_position_points", "position", "projected_points"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    position = Column(String, nullable=False)  # QB | RB | WR | TE
    team = Column(String, nullable=False)  # NFL team code
    projected_points = Column(Float, nullable=True)
    bye_week = Column(Integer, nullable=True)

    # Draft prediction + actual pick (single current draft)
    predicted_pick_number = Column(Integer, nullable=True, index=True)
    actual_pick_number = Column(Integer, unique=True, index=True, nullable=True)

    # Targeting
    target_status = Column(String, default="default")  # default, target, avoid

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Derived convenience flag (replaces drafted_status)
    @hybrid_property
    def drafted(self) -> bool:
        return self.actual_pick_number is not None

    @drafted.expression
    def drafted(cls):
        return cls.actual_pick_number.isnot(None)


class DraftSettings(Base):
    __tablename__ = "draft_settings"

    id = Column(Integer, primary_key=True, index=True)
    total_teams = Column(Integer, default=12)
    rounds = Column(Integer, default=16)

    # Per-team roster slots
    qb_slots = Column(Integer, default=1)
    rb_slots = Column(Integer, default=2)
    wr_slots = Column(Integer, default=2)
    te_slots = Column(Integer, default=1)
    flex_slots = Column(Integer, default=2)  # QB/RB/WR/TE


class WelcomeMessage(Base):
    __tablename__ = "welcome_messages"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
