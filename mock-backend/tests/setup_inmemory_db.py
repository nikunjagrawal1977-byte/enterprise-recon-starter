import os
import importlib
from sqlmodel import create_engine, SQLModel, Session

# Helper to configure an in-memory test DB and initialize the app modules.
# Run this script with `python -m mock-backend.tests.test_reconcile_api` from repo root.

if __name__ == '__main__':
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    # create engine
    engine = create_engine('sqlite:///:memory:', connect_args={"check_same_thread": False})
    # patch app.db.engine if needed
    import app.db as db
    db.engine = engine
    # create tables
    from app import models
    SQLModel.metadata.create_all(engine)
    # seed
    import app.seed as seed
    seed.create_initial_data()
    print('In-memory DB created and seeded')
