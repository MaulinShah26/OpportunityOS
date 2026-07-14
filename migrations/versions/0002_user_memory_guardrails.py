"""Add user-controlled memory lifecycle and audit history.

Revision ID: 0002_memory_guardrails
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_memory_guardrails"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_items",
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
    )
    op.add_column(
        "memory_items",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "memory_items",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memory_items",
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "memory_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "memory_item_id",
            sa.String(length=36),
            sa.ForeignKey("memory_items.id"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_memory_audit_user_created",
        "memory_audit_events",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_audit_user_created", table_name="memory_audit_events")
    op.drop_table("memory_audit_events")
    op.drop_column("memory_items", "rejected_at")
    op.drop_column("memory_items", "confirmed_at")
    op.drop_column("memory_items", "active")
    op.drop_column("memory_items", "status")
