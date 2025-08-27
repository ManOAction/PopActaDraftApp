# app/init_db.py
import logging
import os
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from .database import Base, SessionLocal, engine
from .models import DraftSettings, Player, WelcomeMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _sqlite_path() -> str | None:
    if engine.dialect.name != "sqlite":
        return None
    db_path = engine.url.database or ""
    if db_path in ("", ":memory:"):
        return None
    return db_path


def drop_all_tables():
    logger.warning("Dropping all tables…")
    Base.metadata.drop_all(bind=engine)


def create_tables():
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created.")


def seed_default_data():
    # A tiny predictable seed (adjust freely)
    sample_players = [
        # name, position, team, projected, bye, predicted_pick_number
        Player(name="Josh Allen", position="QB", team="BUF", projected_points=285.5, bye_week=12, predicted_pick_number=6),
        Player(name="Christian McCaffrey", position="RB", team="SF", projected_points=345.8, bye_week=9, predicted_pick_number=1),
        Player(name="Cooper Kupp", position="WR", team="LAR", projected_points=265.2, bye_week=10, predicted_pick_number=8),
        Player(name="Travis Kelce", position="TE", team="KC", projected_points=195.4, bye_week=10, predicted_pick_number=15),
        Player(name="Justin Jefferson", position="WR", team="MIN", projected_points=300.1, bye_week=6, predicted_pick_number=2),
        Player(name="Bijan Robinson", position="RB", team="ATL", projected_points=260.3, bye_week=11, predicted_pick_number=5),
        # K/DST kept just to show they still exist but won’t show in FLEX
        Player(name="Justin Tucker", position="K", team="BAL", projected_points=145.2, bye_week=13, predicted_pick_number=None),
        Player(name="San Francisco 49ers DST", position="DST", team="SF", projected_points=125.8, bye_week=9, predicted_pick_number=None),
    ]

    sample_messages = [
        WelcomeMessage(message="Welcome to PopActaDraftApp!"),
        WelcomeMessage(message="Get ready for the draft!"),
        WelcomeMessage(message="May your picks be ever in your favor!"),
        WelcomeMessage(message="It's draft day — time to make some magic happen!"),
        WelcomeMessage(message="The clock is ticking... choose wisely."),
        WelcomeMessage(message="Championships are won in the draft. Let’s go!"),
        WelcomeMessage(message="Fortune favors the bold. Draft boldly."),
        WelcomeMessage(message="Don’t just pick players, build legends."),
        WelcomeMessage(message="Your future fantasy glory starts right now."),
        WelcomeMessage(message="In the end zone of life, always spike the ball."),
    ]

    # Draft settings: per-team slots + list of competing teams (round 1 order)
    default_settings = DraftSettings(
        total_teams=12,
        rounds=16,
        current_pick=1,  # you can derive this later if you prefer
        qb_slots=1,
        rb_slots=2,
        wr_slots=2,
        te_slots=1,
        flex_slots=1,
    )

    with SessionLocal() as db, db.begin():
        db.add(default_settings)
        db.add_all(sample_players)
        db.add_all(sample_messages)

    logger.info("Default data seeded successfully.")


def _should_reset() -> bool:
    """Return True if we should hard-reset the DB."""
    # Explicit: POPACTA_RESET_DB=1 to force a rebuild for pre-release iterations
    env_reset = os.getenv("POPACTA_RESET_DB", "").strip() in ("1", "true", "True", "yes", "YES")
    if env_reset:
        return True

    # Otherwise: reset if DB exists but is empty or has no tables (fresh dev env)
    inspector = inspect(engine)
    names = inspector.get_table_names()
    if not names:
        return True

    # DB already has tables -> don't reset unless env var says so
    return False


def init_database():
    sqlite_path = _sqlite_path()
    if sqlite_path:
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

    if _should_reset():
        # For SQLite file, if exists and POPACTA_RESET_DB=1, we still do drop/create (no need to delete the file)
        drop_all_tables()
        create_tables()
        try:
            seed_default_data()
        except IntegrityError as e:
            logger.warning("Seed encountered duplicates; proceeding. Detail: %s", e)
        logger.info("Database initialization complete (fresh).")
        return

    # Existing DB with tables — just ensure tables exist (no destructive ops)
    create_tables()
    logger.info("Database already initialized — no reset requested.")


if __name__ == "__main__":
    init_database()
