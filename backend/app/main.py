# app/main.py
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, File, HTTPException, Path, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import get_db
from .init_db import init_database
from .models import DraftSettings, Player, WelcomeMessage
from .services.player_import import CSVValidationError, parse_players_csv, replace_players_transactionally
from .services.vorp import compute_vorp_drop

# ---- Pydantic payloads ----


class DraftSettingsUpdate(BaseModel):
    total_teams: int | None = Field(None, ge=1, le=24)
    rounds: int | None = Field(None, ge=1, le=40)
    current_pick: int | None = Field(None, ge=1)  # optional convenience field; you may remove later
    qb_slots: int | None = Field(None, ge=0, le=3)
    rb_slots: int | None = Field(None, ge=0, le=6)
    wr_slots: int | None = Field(None, ge=0, le=6)
    flex_slots: int | None = Field(None, ge=0, le=3)
    # NOTE: no is_active, no competing teams


class PlayerUpdate(BaseModel):
    # Allow editing core fields + targeting + predictions; not the draft assignment directly
    name: str | None = None
    team: str | None = None
    position: str | None = None
    projected_points: float | None = None
    bye_week: int | None = None
    target_status: str | None = None  # "default" | "target" | "avoid"
    predicted_pick_number: int | None = None
    # actual_pick_number is controlled via the toggle endpoint (to keep uniqueness consistent)


# ---- App bootstrap ----


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield


app = FastAPI(title="PopActaDraftApp API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Basic/utility routes ----


@app.get("/")
async def root():
    return {"message": "PopActaDraftApp API is running"}


@app.get("/api/hello")
def read_hello():
    return {"message": "Hello, world!"}


@app.get("/api/welcome")
def get_random_welcome(db: Session = Depends(get_db)):
    msg = db.query(WelcomeMessage).order_by(func.random()).first()
    if not msg:
        return {"message": "Message Table is empty."}
    return {"id": msg.id, "message": msg.message}


# ---- Players ----


@app.get("/api/players")
async def get_players(db: Session = Depends(get_db)):
    return db.query(Player).all()


@app.patch("/api/players/{player_id}")
def update_player(
    player_id: int = Path(...),
    payload: PlayerUpdate = Body(...),
    db: Session = Depends(get_db),
):
    p = db.query(Player).filter(Player.id == player_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Player not found")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p, k, v)

    db.commit()
    db.refresh(p)
    return p


@app.post("/api/players/{player_id}/toggle-drafted")
def toggle_drafted(player_id: int, db: Session = Depends(get_db)):
    """
    If player is undrafted -> assign next overall pick number.
    If player is drafted -> clear (undraft).
    """
    p = db.query(Player).filter(Player.id == player_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Player not found")

    if p.actual_pick_number is None:
        # Assign next overall pick number = max(existing) + 1
        next_pick = (db.query(func.max(Player.actual_pick_number)).scalar() or 0) + 1
        p.actual_pick_number = next_pick
    else:
        # Undraft: clear the assignment; we do NOT renumber historical picks
        p.actual_pick_number = None

    db.commit()
    db.refresh(p)
    return {"player": p}


@app.post("/api/reset-players")
async def reset_players(
    file: UploadFile = File(..., description="CSV columns: name,position,team,projected_points,bye_week[,predicted_pick_number]"),
    db: Session = Depends(get_db),
):
    # Light content-type guard
    if file.content_type not in ("text/csv", "application/vnd.ms-excel", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected a CSV upload; got {file.content_type!r}",
        )

    raw = await file.read()

    try:
        players = parse_players_csv(raw)
    except CSVValidationError as e:
        raise HTTPException(status_code=400, detail={"error": str(e), "rows": e.errors})

    try:
        inserted = replace_players_transactionally(db, players)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset players: {e}")

    return {"message": "Players reset successfully", "inserted": inserted}


@app.post("/api/reset-drafted-status")
async def reset_drafted_status(db: Session = Depends(get_db)):
    """
    Clears actual_pick_number for all players (undrafts everyone).
    Returns count of affected rows.
    """
    try:
        updated = (
            db.query(Player)
            .filter(Player.actual_pick_number.isnot(None))
            .update(
                {"actual_pick_number": None},
                synchronize_session=False,
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to reset drafted status: {e}")

    return {"message": "Player draft status reset successfully", "updated": int(updated)}


# ---- Draft settings ----


@app.get("/api/draft-settings")
async def get_draft_settings(db: Session = Depends(get_db)):
    return db.query(DraftSettings).first()


@app.patch("/api/draft-settings")
def patch_draft_settings(payload: DraftSettingsUpdate, db: Session = Depends(get_db)):
    s = db.query(DraftSettings).first()
    if not s:
        s = DraftSettings()
        db.add(s)
        db.flush()

    for f, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, f, v)

    db.commit()
    db.refresh(s)
    return s


# ---- VORP ----


@app.get("/api/vorp-drop")
def get_vorp_drop(db: Session = Depends(get_db), k: int = 6):
    """
    Returns { player_id: drop } for positions where starters remain.
    """
    drops = compute_vorp_drop(db, k=k)
    return drops
