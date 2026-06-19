from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations():
    """Lightweight SQLite migrations for MVP (no Alembic)."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "patients" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("patients")}
    if "middle_name" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE patients ADD COLUMN middle_name VARCHAR(100)"))
