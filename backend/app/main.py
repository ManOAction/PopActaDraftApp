# app/main.py
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import get_db
from .init_db import init_database
from .models import DraftSettings, Player, WelcomeMessage
from .services.player_import import CSVValidationError, parse_players_csv, replace_players_transactionally


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


@app.get("/")
async def root():
    return {"message": "PopActaDraftApp API is running"}


@app.get("/api/hello")
def read_hello():
    return {"message": "Hello, world!"}


# app/main.py (add route near your others)
@app.get("/api/welcome")
def get_random_welcome(db: Session = Depends(get_db)):
    msg = db.query(WelcomeMessage).order_by(func.random()).first()
    if not msg:
        # Fallback if table has no rows
        return {"message": "Message Table is empty."}
    return {"id": msg.id, "message": msg.message}


@app.get("/api/players")
async def get_players(db: Session = Depends(get_db)):
    return db.query(Player).all()


@app.get("/api/draft-settings")
async def get_draft_settings(db: Session = Depends(get_db)):
    return db.query(DraftSettings).first()


@app.post("/api/reset-players")
async def reset_players(
    file: UploadFile = File(..., description="CSV columns: name,position,team,projected_points,bye_week"),
    db: Session = Depends(get_db),
):
    # Light content-type guard; browsers sometimes send application/octet-stream
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
    try:
        db.query(Player).update({"drafted_status": False}, synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to reset drafted status: {e}")

    return {"message": "Player draft status reset successfully"}
