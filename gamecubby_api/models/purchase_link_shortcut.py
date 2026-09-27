from sqlalchemy import Column, DateTime, Integer, String, func, Index

from ..models import Base


class PurchaseLinkShortcut(Base):
    __tablename__ = "purchase_link_shortcuts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(100), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "uq_purchase_link_shortcuts_label_normalized",
            func.lower(func.trim(label)),
            unique=True,
        ),
    )
