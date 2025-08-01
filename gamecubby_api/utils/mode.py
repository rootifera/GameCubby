import os
import httpx
from typing import Optional
from sqlalchemy.orm import Session

from .external import get_igdb_token
from ..models.mode import Mode
from ..models.game import Game


def upsert_mode(db: Session, mode_id: int, name: str) -> Mode:
    """
    Insert or update a game mode by ID and name.
    """
    mode = db.query(Mode).filter_by(id=mode_id).first()
    if not mode:
        mode = Mode(id=mode_id, name=name)
        db.add(mode)
        db.commit()
        db.refresh(mode)
    elif mode.name != name:
        mode.name = name
        db.commit()
    return mode


def list_modes(db: Session) -> list[Mode]:
    return db.query(Mode).order_by(Mode.name).all()


def assign_mode_to_game(db: Session, game_id: int, mode_id: int) -> bool:
    game = db.query(Game).filter_by(id=game_id).first()
    mode = db.query(Mode).filter_by(id=mode_id).first()
    if not game or not mode:
        return False
    if mode not in game.modes:
        game.modes.append(mode)
        db.commit()
    return True


def remove_mode_from_game(db: Session, game_id: int, mode_id: int) -> bool:
    game = db.query(Game).filter_by(id=game_id).first()
    mode = db.query(Mode).filter_by(id=mode_id).first()
    if not game or not mode:
        return False
    if mode in game.modes:
        game.modes.remove(mode)
        db.commit()
    return True


async def sync_modes_from_igdb(db: Session) -> int:
    """
    Fetch all game modes from IGDB and upsert into local DB.
    Returns the number of modes synced.
    """
    CLIENT_ID = os.getenv("CLIENT_ID")
    token = await get_igdb_token()

    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.igdb.com/v4/game_modes",
            headers=headers,
            data="fields id, name; limit 500;"
        )
    resp.raise_for_status()
    modes = resp.json()

    for mode in modes:
        upsert_mode(db, mode["id"], mode["name"])

    return len(modes)


def get_mode_by_id(db: Session, mode_id: int) -> Optional[Mode]:
    return db.query(Mode).filter(Mode.id == mode_id).first()
