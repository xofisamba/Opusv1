"""Database connectivity and initialization for OpusCore v2."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from persistence.models import Base

DEFAULT_DB_URL = "sqlite:///opuscore.db"


def get_engine(db_url: str = DEFAULT_DB_URL):
    """Create SQLAlchemy engine (echo=False by default)."""
    return create_engine(db_url, echo=False)


def get_session_maker(engine):
    """Create session factory bound to engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(engine) -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session (use with `with` pattern or dependency injection)."""
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db(engine) -> None:
    """Create all tables defined on Base metadata."""
    Base.metadata.create_all(engine)


def reset_db(engine) -> None:
    """Drop all tables and recreate (for testing)."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)