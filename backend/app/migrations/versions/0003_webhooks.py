"""API webhooks: per-job URL and delivery status, per-user signing secret

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31 12:02:21.068220
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("webhook_url", sa.String(length=2000), nullable=True))
        batch_op.add_column(sa.Column("webhook_status", sa.String(length=16), nullable=True))

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("webhook_secret", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("webhook_secret")

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("webhook_status")
        batch_op.drop_column("webhook_url")
