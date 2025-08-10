# app/init_db.py
import logging
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from .database import Base, SessionLocal, engine
from .models import DraftSettings, Player, WelcomeMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _sqlite_db_file_exists() -> bool:
    """Return True if we're using SQLite and the DB file already exists."""
    if engine.dialect.name != "sqlite":
        return False  # Only file-skip for SQLite
    db_path = engine.url.database or ""
    # Ignore special in-memory URIs
    if db_path in (":memory:",):
        return False
    try:
        return Path(db_path).exists()
    except TypeError:
        # If database is not a normal filesystem path
        return False


def create_tables():
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created or already present.")


def seed_default_data():
    sample_players = [
        Player(name="Josh Allen", position="QB", team="BUF", projected_points=285.5, bye_week=12),
        Player(name="Christian McCaffrey", position="RB", team="SF", projected_points=245.8, bye_week=9),
        Player(name="Cooper Kupp", position="WR", team="LAR", projected_points=265.2, bye_week=10),
        Player(name="Travis Kelce", position="TE", team="KC", projected_points=195.4, bye_week=10),
        Player(name="Justin Tucker", position="K", team="BAL", projected_points=145.2, bye_week=13),
        Player(name="San Francisco 49ers", position="DST", team="SF", projected_points=125.8, bye_week=9),
    ]

    sample_messages = [
        WelcomeMessage(message="Welcome to PopActaDraftApp!"),
        WelcomeMessage(message="Get ready for the draft!"),
        WelcomeMessage(message="May your picks be ever in your favor!"),
    ]

    with SessionLocal() as db, db.begin():
        # Seed once on fresh DB
        db.add(DraftSettings(total_teams=12, rounds=16, current_pick=1, is_active=False))
        for p in sample_players:
            db.add(p)
        for m in sample_messages:
            db.add(m)

    logger.info("Default data seeded successfully.")


def init_database():
    if engine.dialect.name == "sqlite":
        db_path = engine.url.database or ""
        if db_path not in (":memory:", "") and Path(db_path).exists():
            from sqlalchemy import inspect

            inspector = inspect(engine)
            if inspector.get_table_names():
                logger.info("SQLite DB already initialized — skipping.")
                return

    logger.info("Initializing new database (creating tables + seeding defaults)...")
    create_tables()
    try:
        seed_default_data()
    except IntegrityError:
        logger.info("Seed encountered duplicates; proceeding.")
    logger.info("Database initialization complete.")


if __name__ == "__main__":
    init_database()
