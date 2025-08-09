# app/main.py
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import get_db
from .init_db import init_database
from .models import DraftSettings, Player


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


@app.get("/players")
async def get_players(db: Session = Depends(get_db)):
    return db.query(Player).all()


@app.get("/draft-settings")
async def get_draft_settings(db: Session = Depends(get_db)):
    return db.query(DraftSettings).first()
