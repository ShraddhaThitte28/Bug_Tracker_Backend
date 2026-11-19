from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Create SQLAlchemy Engine
# pool_pre_ping checks connection liveness before execution
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,
)

# SessionLocal factory for creating independent database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Declarative Base class for future SQLAlchemy ORM models
Base = declarative_base()


def get_db() -> Generator:
    """FastAPI dependency to provide a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

