# app/services/player_import.py
import csv
import io
from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import Player

REQUIRED_COLUMNS = ["name", "position", "team", "projected_points", "bye_week"]


class CSVValidationError(Exception):
    """Raised when the uploaded CSV is invalid (header or row-level issues)."""

    def __init__(self, message: str, errors: List[Dict] | None = None):
        super().__init__(message)
        self.errors = errors or []


def _decode_file(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise CSVValidationError("File must be UTF-8 encoded") from e


def parse_players_csv(raw: bytes) -> List[Player]:
    """
    Parse and validate a players CSV. Returns a list of Player objects (not yet added to the session).
    Raises CSVValidationError on header/row issues.
    """
    text_data = _decode_file(raw)
    f = io.StringIO(text_data, newline="")
    reader = csv.DictReader(f)

    # Validate header (strict order; swap to set() if you want order-insensitive)
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    if headers != REQUIRED_COLUMNS:
        raise CSVValidationError(
            "Invalid CSV header",
            errors=[{"expected": REQUIRED_COLUMNS, "received": headers}],
        )

    players: List[Player] = []
    errors: List[Dict] = []
    rownum = 1  # header

    for row in reader:
        rownum += 1
        try:
            name = (row["name"] or "").strip()
            position = (row["position"] or "").strip()
            team = (row["team"] or "").strip()
            if not name:
                raise ValueError("name is required")
            if not position:
                raise ValueError("position is required")
            if not team:
                raise ValueError("team is required")

            try:
                projected_points = float(row["projected_points"])
            except Exception:
                raise ValueError("projected_points must be a number")

            try:
                bye_week = int(row["bye_week"])
            except Exception:
                raise ValueError("bye_week must be an integer")

            players.append(
                Player(
                    name=name,
                    position=position,
                    team=team,
                    projected_points=projected_points,
                    bye_week=bye_week,
                )
            )
        except Exception as e:
            errors.append({"row": rownum, "error": str(e)})

    if errors:
        raise CSVValidationError("CSV contains invalid rows", errors=errors)

    return players


def replace_players_transactionally(db: Session, players: List[Player]) -> int:
    """
    Replace the players table contents atomically.
    Returns the inserted row count.
    """
    with db.begin():
        db.query(Player).delete()
        # Reset autoincrement for SQLite (optional)
        if db.bind and db.bind.dialect.name == "sqlite":
            try:
                db.execute(text("DELETE FROM sqlite_sequence WHERE name='players'"))
            except Exception:
                pass  # Sequence table doesn't exist
        # Bulk insert
        db.bulk_save_objects(players)
        # Commit happens on context exit
    return len(players)
