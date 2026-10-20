"""How Alembic connects to the database when it runs migrations.

app/migrate.py passes in a connection that is already inside a transaction. From the
command line (uv run alembic ...), the database comes from the app's settings and the
connection from app.migrate.migration_engine, so the same rules apply either way.
"""

from alembic import context
from sqlalchemy import Connection

from app import models  # noqa: F401  (importing it registers every table on Base.metadata)
from app.config import load_settings
from app.db import Base
from app.migrate import migration_engine

config = context.config
target_metadata = Base.metadata  # what `alembic revision --autogenerate` compares the database with


def run(connection: Connection) -> None:
    # render_as_batch: SQLite cannot change most things about an existing column; Alembic's
    # "batch" mode does it by copying the table, when a migration asks for it.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


given = config.attributes.get("connection")
if given is not None:
    run(given)
else:
    engine = migration_engine(load_settings().database_path)
    try:
        with engine.begin() as connection:
            run(connection)
    finally:
        engine.dispose()
