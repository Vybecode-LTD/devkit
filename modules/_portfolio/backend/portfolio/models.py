"""SQLAlchemy models for portfolio (SPEC.md section 10). Generated scaffold: check types and indexes before the first migration.

Tables are portfolio_<name>, UUID keys, timestamptz in UTC; foreign keys only to this module's tables and auth_user.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from kernel import Base


class PortfolioPiece(Base):
    __tablename__ = "portfolio_piece"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("auth_user.id", ondelete="SET NULL"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    discipline: Mapped[str] = mapped_column(String(40))
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    shop_product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, doc="Links to shop by id, no foreign key"
    )
    status: Mapped[str] = mapped_column(String(12), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)


class PortfolioImage(Base):
    __tablename__ = "portfolio_image"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    piece_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("portfolio_piece.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(Text)
    alt: Mapped[str] = mapped_column(String(300), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
