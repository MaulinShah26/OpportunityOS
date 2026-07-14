"""Create OpportunityOS core schema.

Revision ID: 0001_initial
Revises: None
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        *_common_columns(),
        sa.Column("email", sa.String(length=320), nullable=True, unique=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
    )
    op.create_table(
        "personal_profiles",
        *_common_columns(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("headline", sa.String(length=300), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "memory_items",
        *_common_columns(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("key", sa.String(length=180), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_user_overridden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("user_id", "category", "key", name="uq_memory_user_category_key"),
    )
    op.create_table(
        "companies",
        *_common_columns(),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("website", sa.String(length=2048), nullable=True),
        sa.Column("company_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "opportunities",
        *_common_columns(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("opportunity_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "evidence_claims",
        *_common_columns(),
        sa.Column("opportunity_id", sa.String(length=36), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=40), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("supporting_excerpt", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
    )
    op.create_table(
        "analysis_runs",
        *_common_columns(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("orchestrator", sa.String(length=40), nullable=False),
        sa.Column("model_metadata_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "behaviour_events",
        *_common_columns(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("analysis_run_id", sa.String(length=36), sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("event_json", sa.JSON(), nullable=False),
        sa.Column("explicit", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "outcomes",
        *_common_columns(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("outcome_type", sa.String(length=80), nullable=False),
        sa.Column("outcome_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_opportunities_user_status", "opportunities", ["user_id", "status"])
    op.create_index("ix_memory_user_category", "memory_items", ["user_id", "category"])
    op.create_index("ix_behaviour_user_type", "behaviour_events", ["user_id", "event_type"])


def downgrade() -> None:
    op.drop_index("ix_behaviour_user_type", table_name="behaviour_events")
    op.drop_index("ix_memory_user_category", table_name="memory_items")
    op.drop_index("ix_opportunities_user_status", table_name="opportunities")
    op.drop_table("outcomes")
    op.drop_table("behaviour_events")
    op.drop_table("analysis_runs")
    op.drop_table("evidence_claims")
    op.drop_table("opportunities")
    op.drop_table("companies")
    op.drop_table("memory_items")
    op.drop_table("personal_profiles")
    op.drop_table("users")
