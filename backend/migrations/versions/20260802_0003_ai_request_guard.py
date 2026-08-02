"""Add the shared AI request admission ledger.

Revision ID: 20260802_0003
Revises: 20260724_0002
Create Date: 2026-08-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260802_0003"
down_revision: str | None = "20260724_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_request_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id_hash", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.String(length=32), nullable=False),
        sa.Column("reserved_cost_microusd", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "lease_expires_at > started_at",
            name="ck_ai_request_events_lease_after_start",
        ),
        sa.CheckConstraint(
            "reserved_cost_microusd >= 0",
            name="ck_ai_request_events_reserved_cost_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_request_events"),
    )
    op.create_index(
        "ix_ai_request_events_active_lease",
        "ai_request_events",
        ["finished_at", "lease_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_request_events_started_at",
        "ai_request_events",
        ["started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_request_events_started_at", table_name="ai_request_events")
    op.drop_index("ix_ai_request_events_active_lease", table_name="ai_request_events")
    op.drop_table("ai_request_events")
