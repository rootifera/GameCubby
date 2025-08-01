from .db_tools import with_db
from ..models.company import Company
from ..models.game_company import GameCompany
from sqlalchemy.orm import Session
import asyncio
import os
import httpx
from .external import get_igdb_token
from ..db import SessionLocal


def upsert_companies(db: Session, company_data: list[dict]) -> list[Company]:
    companies = []
    for data in company_data:
        company_id = data["company_id"]
        name = data["name"]
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            company = Company(id=company_id, name=name)
            db.add(company)
            db.commit()
            db.refresh(company)
        companies.append(company)
    return companies


async def sync_company_names(db: Session):
    CLIENT_ID = os.getenv("CLIENT_ID")
    token = await get_igdb_token()
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    companies = db.query(Company).all()
    updated = 0

    for company in companies:
        query = f"fields name; where id = {company.id};"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post("https://api.igdb.com/v4/companies", data=query, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if data:
                    name = data[0]["name"]
                    if company.name != name:
                        company.name = name
                        updated += 1
        except Exception as e:
            print(f"Failed to sync company ID {company.id}: {e}")

        await asyncio.sleep(0.5)

    db.commit()
    print(f"Updated {updated} company names.")


async def sync_companies():
    with with_db() as db:
        await sync_company_names(db)