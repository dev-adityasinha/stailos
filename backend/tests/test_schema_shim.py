"""The additive-column shim in main._add_missing_columns must bring an
older database up to the current model schema on startup — create_all()
alone never adds columns to existing tables, which would crash every
SELECT against a pre-upgrade database."""
import sqlite3
import tempfile

import pytest
from sqlalchemy import create_engine, text

from app.db.base import Base
from app.main import _add_missing_columns


@pytest.fixture
def old_db_engine():
    """A database built from the current schema, then surgically aged by
    dropping columns that recent commits introduced."""
    path = tempfile.mktemp(prefix="shim_", suffix=".db")
    engine = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(bind=engine)
    con = sqlite3.connect(path)
    con.execute("ALTER TABLE event_registrations DROP COLUMN reminder_48h_sent_at")
    con.execute("ALTER TABLE event_registrations DROP COLUMN reminder_24h_sent_at")
    con.execute("ALTER TABLE tenants DROP COLUMN onboarding_completed")
    con.execute(
        "INSERT INTO tenants (id, name, slug, plan_tier, created_at, updated_at) "
        "VALUES ('t-old','Old Co','old-co','standard','2026-01-01','2026-01-01')"
    )
    con.commit()
    con.close()
    yield engine
    engine.dispose()


def test_shim_adds_missing_columns_and_backfills_defaults(old_db_engine):
    with old_db_engine.begin() as conn:
        _add_missing_columns(conn)

    with old_db_engine.connect() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(event_registrations)")}
        assert {"reminder_48h_sent_at", "reminder_24h_sent_at"} <= cols

        # Pre-existing row gets the model's scalar default backfilled, so old
        # tenants read as onboarding_completed=False rather than NULL.
        val = conn.execute(
            text("SELECT onboarding_completed FROM tenants WHERE id='t-old'")
        ).scalar()
        assert val == 0

    # Idempotent: a second run must be a clean no-op.
    with old_db_engine.begin() as conn:
        _add_missing_columns(conn)
