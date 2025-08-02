from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.company import Company
from ..utils.game_company import sync_companies

router = APIRouter(prefix="/company", tags=["Company"])


@router.post("/sync")
async def sync_companies_endpoint():
    await sync_companies()
    return JSONResponse(content={"message": "Company sync completed"})


@router.get("/", response_model=list[dict])
def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).order_by(Company.name).all()
    return [{"id": c.id, "name": c.name} for c in companies]


@router.get("/{company_id}", response_model=dict)
def get_company_by_id(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"id": company.id, "name": company.name}
