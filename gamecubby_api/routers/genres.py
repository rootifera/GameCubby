from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..utils.genre import sync_genres
from ..models.genre import Genre
from ..utils.auth import get_current_admin

router = APIRouter(prefix="/genres", tags=["Genres"])


@router.post("/sync", dependencies=[Depends(get_current_admin)])
async def sync_genres_endpoint(db: Session = Depends(get_db)):
    try:
        genres = await sync_genres(db)
        return {"message": "Genres synced successfully.", "count": len(genres)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=list[dict])
def list_genres(db: Session = Depends(get_db)):
    genres = db.query(Genre).all()
    return [{"id": g.id, "name": g.name} for g in genres]


@router.get("/{genre_id}", response_model=dict)
def get_genre_by_id(genre_id: int, db: Session = Depends(get_db)):
    genre = db.query(Genre).filter_by(id=genre_id).first()
    if not genre:
        raise HTTPException(status_code=404, detail="Genre not found")
    return {"id": genre.id, "name": genre.name}
