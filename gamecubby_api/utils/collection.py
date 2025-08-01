from sqlalchemy.orm import Session
from ..models.collection import Collection


def create_collection(session: Session, collection_data: dict):
    collection = Collection(**collection_data)
    session.add(collection)
    session.commit()
    session.refresh(collection)
    return collection


def get_collection(session: Session, collection_id: int):
    return session.query(Collection).filter_by(id=collection_id).first()


def get_collection_by_igdb_id(session: Session, igdb_id: int):
    return session.query(Collection).filter_by(igdb_id=igdb_id).first()


def list_collections(session: Session):
    return session.query(Collection).order_by(Collection.name).all()
