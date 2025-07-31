from fastapi import APIRouter
from ..utils.game_company import sync_companies
from ..utils.response import success_response

router = APIRouter(prefix="/company", tags=["Company"])


@router.post("/sync")
async def sync_companies_endpoint():
    await sync_companies()
    return success_response(message="Company sync completed")
