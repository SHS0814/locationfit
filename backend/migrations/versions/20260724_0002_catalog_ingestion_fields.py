"""Add catalog ingestion fields and allow shared official sources.

Revision ID: 20260724_0002
Revises: 20260724_0001
Create Date: 2026-07-24
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260724_0002"
down_revision: str | None = "20260724_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_benefits",
        sa.Column("guarantee_fee_rate_pct", sa.Numeric(precision=7, scale=4), nullable=True),
    )
    op.create_check_constraint(
        "ck_product_benefits_guarantee_fee_rate_range",
        "product_benefits",
        "guarantee_fee_rate_pct IS NULL "
        "OR (guarantee_fee_rate_pct >= 0 AND guarantee_fee_rate_pct <= 100)",
    )
    op.create_index(
        "ix_funding_products_extra_data_gin",
        "funding_products",
        ["extra_data"],
        unique=False,
        postgresql_using="gin",
    )
    op.drop_constraint(
        "uq_product_sources_source_external_id", "product_sources", type_="unique"
    )
    op.drop_constraint(
        "uq_product_sources_source_url", "product_sources", type_="unique"
    )
    op.create_unique_constraint(
        "uq_product_sources_product_source_external_id",
        "product_sources",
        ["product_id", "data_source_id", "external_id"],
    )
    op.create_unique_constraint(
        "uq_product_sources_product_source_url",
        "product_sources",
        ["product_id", "data_source_id", "official_url"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_product_sources_product_source_url", "product_sources", type_="unique"
    )
    op.drop_constraint(
        "uq_product_sources_product_source_external_id", "product_sources", type_="unique"
    )
    op.create_unique_constraint(
        "uq_product_sources_source_url",
        "product_sources",
        ["data_source_id", "official_url"],
    )
    op.create_unique_constraint(
        "uq_product_sources_source_external_id",
        "product_sources",
        ["data_source_id", "external_id"],
    )
    op.drop_index("ix_funding_products_extra_data_gin", table_name="funding_products")
    op.drop_constraint(
        "ck_product_benefits_guarantee_fee_rate_range", "product_benefits", type_="check"
    )
    op.drop_column("product_benefits", "guarantee_fee_rate_pct")
