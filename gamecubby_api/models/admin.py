from sqlalchemy import Column, Integer, String
from ..models import Base

class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    def __repr__(self):
        return f"<AdminUser(username={self.username})>"
