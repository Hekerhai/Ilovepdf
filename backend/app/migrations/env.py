"""Alembic environment. Migrations run from Database.migrate(), which passes in an open connection."""

from alembic import context

from app.infra.db import Base

config = context.config
connection = config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    render_as_batch=connection.dialect.name == "sqlite",
    compare_type=True,
)
with context.begin_transaction():
    context.run_migrations()
