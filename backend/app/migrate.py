"""Bring the database file up to date with the code, before the app uses it.

Schema changes are *migrations*: small numbered scripts in backend/migrations/versions/,
run in order by Alembic. The database remembers which one it has reached (the
alembic_version table), so each script runs once per database.

At start-up the backend calls upgrade_database():
- a new database: every migration runs, creating the tables (the caller then adds the
  starter categories and samples);
- an existing database that is behind: a backup copy is made first, then the missing
  migrations run, all in one transaction, so a failure leaves the database as it was;
- a database from milestone 3, made before migrations existed: its tables are exactly
  migration 0001's, so it is marked as being at 0001 ("stamped"), then upgraded.

You can also run it by hand, with the backend stopped:
    uv run python -m app.migrate
"""

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, event, inspect

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
BASELINE = "0001"  # the tables as milestone 3 created them

log = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class UpgradeResult:
    created: bool  # the database was empty or new
    from_revision: str | None
    to_revision: str
    backup: Path | None  # the copy made before changing an existing database


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["connection"] = connection  # migrations/env.py uses it when given
    return config


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None, "no migrations found"
    return head


def migration_engine(database_path: Path) -> Engine:
    """An engine for migrations only. It differs from app/db.py's engine in two ways.

    - Foreign keys are NOT enforced. Changing a table in SQLite can mean copying it and dropping
      the old one; with foreign keys on, dropping it would also delete the rows that point at it
      (ON DELETE CASCADE). SQLite's own advice: turn them off, migrate, then run foreign_key_check.
    - Every statement, CREATE and ALTER included, runs inside one real transaction. Python's
      sqlite3 module would otherwise run table changes outside it, so a failing migration could
      leave half its changes behind. (The recipe from SQLAlchemy's SQLite documentation.)
    """
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{database_path}")

    @event.listens_for(engine, "connect")
    def _no_driver_transactions(dbapi_connection, connection_record) -> None:
        dbapi_connection.isolation_level = None  # we say BEGIN ourselves, below

    @event.listens_for(engine, "begin")
    def _begin(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN")

    return engine


def upgrade_database(database_path: Path) -> UpgradeResult:
    head = head_revision()
    engine = migration_engine(database_path)
    try:
        with engine.connect() as connection:
            revision = MigrationContext.configure(connection).get_current_revision()
            tables = set(inspect(connection).get_table_names())
        created = not tables
        stamp_baseline = revision is None and "recipes" in tables
        if stamp_baseline:
            revision = BASELINE

        backup = None
        if not created and revision != head:
            backup = backup_database(database_path, f"before-{head}")

        with engine.begin() as connection:  # one transaction: COMMIT at the end, ROLLBACK on any error
            config = alembic_config(connection)
            if stamp_baseline:
                command.stamp(config, BASELINE)
            command.upgrade(config, "head")
            problems = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if problems:
                raise RuntimeError(f"The database has rows that point at missing rows: {problems[:5]}")
    finally:
        engine.dispose()

    with closing(sqlite3.connect(database_path)) as check:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"The database file failed SQLite's integrity check: {result}")
    return UpgradeResult(created=created, from_revision=None if created else revision, to_revision=head, backup=backup)


def backup_database(database_path: Path, label: str) -> Path:
    """Copy the database next to itself, e.g. recipes.backup-20261020-091500-before-0002.db.

    SQLite's backup API copies a consistent snapshot, even if another program has the file open.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = database_path.with_name(f"{database_path.stem}.backup-{stamp}-{label}.db")
    with closing(sqlite3.connect(database_path)) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy)
    return target


def describe(result: UpgradeResult, database_path: Path) -> str:
    if result.created:
        return f"Created the database at {database_path} (migration {result.to_revision})"
    if result.backup is None:
        return f"Using the recipes database at {database_path} (migration {result.to_revision}, up to date)"
    return (
        f"Upgraded the database at {database_path} from migration {result.from_revision} to "
        f"{result.to_revision}. A copy from before the upgrade: {result.backup}"
    )


if __name__ == "__main__":
    from app.config import load_settings

    path = load_settings().database_path
    print(describe(upgrade_database(path), path))
