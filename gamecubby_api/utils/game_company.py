from gamecubby_api.models.company import Company
from gamecubby_api.models.game_company import GameCompany
from sqlalchemy.orm import Session


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
