from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.models.orm_models import Base

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # checks the connection before each use, avoids
                          # "MySQL server has gone away" after idle periods
    pool_recycle=280,     # recycle connections before MySQL's default 8h timeout
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    """Create all tables in the database."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency: yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
