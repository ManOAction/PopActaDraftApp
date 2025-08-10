# app/models.py
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from .database import Base


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("name", "position", "team", name="uq_players_identity"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    position = Column(String)
    team = Column(String)
    projected_points = Column(Float)
    bye_week = Column(Integer)
    drafted_status = Column(Boolean, default=False)
    target_status = Column(String, default="default")  # default, target, avoid
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DraftPick(Base):
    __tablename__ = "draft_picks"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer)
    team_name = Column(String)
    pick_number = Column(Integer)
    round_number = Column(Integer)
    drafted_at = Column(DateTime(timezone=True), server_default=func.now())


class DraftStatus(Base):
    __tablename__ = "draft_status"

    id = Column(Integer, primary_key=True, index=True)
    picks_remaining = Column(Integer, default=0)
    qb_remaining = Column(Integer, default=0)
    rb_remaining = Column(Integer, default=0)
    current_pick = Column(Integer, default=1)


class DraftSettings(Base):
    __tablename__ = "draft_settings"

    id = Column(Integer, primary_key=True, index=True)
    total_teams = Column(Integer, default=12)
    rounds = Column(Integer, default=16)
    current_pick = Column(Integer, default=1)
    is_active = Column(Boolean, default=False)


class WelcomeMessage(Base):
    __tablename__ = "welcome_messages"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
