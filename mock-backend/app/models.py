from sqlmodel import create_engine, Session
import os

DATABASE_URL = os.environ.get("DATABASE_URL") or "postgresql+asyncpg://recon_user:change_me@postgres:5432/recon"
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    sync_db_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
else:
    sync_db_url = DATABASE_URL

engine = create_engine(sync_db_url, echo=False)

from contextlib import contextmanager

@contextmanager
def get_session():
    with Session(engine) as session:
        yield session
