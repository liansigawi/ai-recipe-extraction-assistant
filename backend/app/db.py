"""The database connection: one SQLite file, data/recipes.db (or RECIPES_DATA_DIR/recipes.db).

Two SQLAlchemy ideas are used everywhere in the backend:
- the *engine* is the connection to the database file;
- a *session* is one unit of work: load and change objects, then session.commit()
  writes all the changes in one transaction (all of them are saved, or none).
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Request
from sqlalchemy import DateTime, Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    """Parent class of every table class in app/models.py."""


class UTCDateTime(TypeDecorator[datetime]):
    """Stores times in UTC and gives them back *with* their time zone.

    SQLite has no time-zone-aware date type, so SQLAlchemy returns "naive" datetimes.
    Without this, the API would send "2026-10-19T08:00:00" (no Z) and the browser would
    read it as local time: three hours off in Israel.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("refusing to store a datetime without a time zone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def make_engine(database_path: Path, echo: bool = False) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{database_path}",
        echo=echo,  # True: print every SQL statement (RECIPES_SQL_ECHO=true)
        # Store Hebrew in JSON columns as readable text, not as \uXXXX escapes.
        json_serializer=lambda value: json.dumps(value, ensure_ascii=False),
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record) -> None:
        # SQLite only checks foreign keys when asked to, on every new connection.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: objects stay readable after commit, so we can build the response from them.
    return sessionmaker(engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed when the request ends.

    The session factory is created once at start-up (see app/main.py).
    """
    with request.app.state.session_factory() as session:
        yield session


def utc_now() -> datetime:
    return datetime.now(UTC)
