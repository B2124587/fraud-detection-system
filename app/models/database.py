from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.models.orm_models import Base


def _resolve_database_url() -> str:
    """Use SQLite locally when MySQL is not configured or reachable."""
    raw_url = (settings.DATABASE_URL or "").strip()
    if not raw_url:
        return "sqlite:///./zambia_fraud.db"
    if raw_url.startswith("sqlite"):
        return raw_url
    if raw_url.startswith("mysql") and (
        "YOUR_MYSQL_PASSWORD" in raw_url or "root:password@" in raw_url
    ):
        return "sqlite:///./zambia_fraud.db"
    return raw_url


def _create_engine_with_fallback():
    database_url = _resolve_database_url()
    engine = create_engine(
        database_url,
        pool_pre_ping=True,   # checks the connection before each use, avoids
                              # "MySQL server has gone away" after idle periods
        pool_recycle=280,     # recycle connections before MySQL's default 8h timeout
        echo=False,
    )

    if database_url.startswith("mysql"):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return engine
        except OperationalError:
            print("MySQL connection failed; falling back to SQLite for local demo usage.")
            fallback_engine = create_engine(
                "sqlite:///./zambia_fraud.db",
                pool_pre_ping=True,
                pool_recycle=280,
                echo=False,
            )
            return fallback_engine

    return engine


engine = _create_engine_with_fallback()
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
