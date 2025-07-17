import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from dotenv import load_dotenv
from .routers import igdb
from .routers.tags import router as tags_router
from .routers.locations import router as locations_router
from .routers.platforms import router as platforms_router
from .routers.games import router as games_router
from .routers.collections import router as collections_router
from .utils.storage import ensure_game_folders

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_game_folders(autocreate_all=True)
    yield

app = FastAPI(lifespan=lifespan)

app.include_router(igdb.router, prefix="/igdb")
app.include_router(tags_router)
app.include_router(locations_router)
app.include_router(platforms_router)
app.include_router(games_router)
app.include_router(collections_router)

@app.get("/")
def read_root():
    return {"message": "GameCubby API is alive!"}
