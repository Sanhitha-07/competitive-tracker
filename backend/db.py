from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

# Always the tracker.db next to this file, whichever folder the app is started from.
DB_PATH = Path(__file__).with_name("tracker.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

# Columns added after the first version. Existing databases get them automatically.
NEW_COLUMNS = {"competitor": {"thumbnail": "VARCHAR"}}


def create_tables():
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        insp = inspect(conn)
        for table, columns in NEW_COLUMNS.items():
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def get_session():
    with Session(engine) as session:
        yield session
