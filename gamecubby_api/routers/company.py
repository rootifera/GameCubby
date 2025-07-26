from fastapi import APIRouter
from ..utils.game_company import sync_companies

router = APIRouter(prefix="/company", tags=["Company"])

@router.post("/sync")
async def sync_companies_endpoint():
    await sync_companies()
    return {"message": "Company sync completed"}
