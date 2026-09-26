from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

from ..models import Base


wishlist_platforms = Table(
    "wishlist_platforms",
    Base.metadata,
    Column("wishlist_id", Integer, ForeignKey("wishlist_items.id", ondelete="CASCADE"), primary_key=True),
    Column("platform_id", Integer, ForeignKey("platforms.id", ondelete="CASCADE"), primary_key=True),
)


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    igdb_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    release_year = Column(Integer, nullable=True)
    cover_url = Column(String, nullable=True)
    status = Column(String(20), nullable=False, default="active", server_default="active", index=True)
    library_game_id = Column(Integer, ForeignKey("games.id"), nullable=True)

    platforms = relationship("Platform", secondary=wishlist_platforms)
    links = relationship("WishlistLink", back_populates="wishlist_item", cascade="all, delete-orphan")
    library_game = relationship("Game", foreign_keys=[library_game_id])


class WishlistLink(Base):
    __tablename__ = "wishlist_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    wishlist_item_id = Column(Integer, ForeignKey("wishlist_items.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    url = Column(String(2048), nullable=False)

    wishlist_item = relationship("WishlistItem", back_populates="links")
