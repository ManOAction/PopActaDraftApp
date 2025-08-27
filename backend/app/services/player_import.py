# app/services/player_import.py
import csv
import io
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import Player

# Required base columns for a valid import (order-insensitive, case-insensitive)
REQUIRED_COLUMNS = {"name", "position", "team", "projected_points"}
# Optional columns supported by the new schema
OPTIONAL_COLUMNS = {"predicted_pick_number", "bye_week"}


class CSVValidationError(Exception):
    """Raised when the uploaded CSV is invalid (header or row-level issues)."""

    def __init__(self, message: str, errors: List[Dict] | None = None):
        super().__init__(message)
        self.errors = errors or []


def _decode_file(raw: bytes) -> str:
    try:
        # utf-8 with BOM tolerant
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise CSVValidationError("File must be UTF-8 encoded") from e


def _parse_int(val: str, *, allow_none: bool = False) -> Optional[int]:
    v = (val or "").strip()
    if v == "":
        if allow_none:
            return None
        raise ValueError("value is required")
    try:
        return int(v)
    except Exception:
        raise ValueError("must be an integer")


def _parse_float(val: str) -> float:
    v = (val or "").strip()
    try:
        return float(v)
    except Exception:
        raise ValueError("must be a number")


def parse_players_csv(raw: bytes) -> List[Player]:
    """
    Parse and validate a players CSV. Returns a list of Player objects (not yet added to the session).
    Raises CSVValidationError on header/row issues.

    Required columns (any order): name, position, team, projected_points
    Optional columns: predicted_pick_number, bye_week
    Extra columns are ignored.
    """
    text_data = _decode_file(raw)
    f = io.StringIO(text_data, newline="")
    reader = csv.DictReader(f)

    # Validate header (order-insensitive, lowercase compare)
    headers_lower = [h.strip().lower() for h in (reader.fieldnames or [])]
    header_set = set(headers_lower)
    missing = REQUIRED_COLUMNS - header_set
    if missing:
        raise CSVValidationError(
            "Invalid CSV header",
            errors=[
                {
                    "error": "missing required columns",
                    "missing": sorted(missing),
                    "received": sorted(header_set),
                    "required": sorted(REQUIRED_COLUMNS),
                    "optional": sorted(OPTIONAL_COLUMNS),
                }
            ],
        )

    # Map lowercased header -> original key for safe access
    # (DictReader gives us original keys; we want case-insensitive lookups)
    key_map = {h.lower(): h for h in (reader.fieldnames or [])}

    players: List[Player] = []
    errors: List[Dict] = []
    rownum = 1  # header row

    for row in reader:
        rownum += 1
        try:
            name = (row[key_map["name"]] or "").strip()
            position = (row[key_map["position"]] or "").strip().upper()
            team = (row[key_map["team"]] or "").strip().upper()

            if not name:
                raise ValueError("name is required")
            if not position:
                raise ValueError("position is required")
            if not team:
                raise ValueError("team is required")

            projected_points = _parse_float(row[key_map["projected_points"]])

            # Make bye_week optional with default 0
            bye_week = 0
            if "bye_week" in header_set:
                try:
                    bye_week = _parse_int(row[key_map["bye_week"]])
                except ValueError:
                    # Silently default to 0 for invalid bye weeks
                    pass

            # Optional predicted pick number
            predicted_pick_number = None
            if "predicted_pick_number" in header_set:
                predicted_pick_number = _parse_int(
                    row[key_map["predicted_pick_number"]],
                    allow_none=True,
                )

            players.append(
                Player(
                    name=name,
                    position=position,
                    team=team,
                    projected_points=projected_points,
                    bye_week=bye_week,
                    predicted_pick_number=predicted_pick_number,
                    # actual_pick_number intentionally omitted in import (that happens during the draft)
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
                # sqlite_sequence may not exist (e.g., fresh schema) — ignore
                pass
        # Bulk insert
        db.bulk_save_objects(players)
        # Commit happens on context exit
    return len(players)
