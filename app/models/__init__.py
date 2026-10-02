"""SQLAlchemy models. Import every model module here so Alembic sees all tables."""

from app.db import Base

__all__ = ["Base"]
