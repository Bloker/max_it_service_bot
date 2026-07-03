"""Declarative base для SQLAlchemy models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Единая metadata для отражения существующей схемы."""
