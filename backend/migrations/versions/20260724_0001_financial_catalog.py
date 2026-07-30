"""Create the financial-support catalog schema.

Revision ID: 20260724_0001
Revises:
Create Date: 2026-07-24
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260724_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


organization_type = postgresql.ENUM(
    "bank", "public_agency", "local_government", "guarantee_foundation", "aggregator",
    name="organization_type", create_type=False,
)
acquisition_mode = postgresql.ENUM(
    "official_api", "curated_official_source", name="acquisition_mode", create_type=False
)
product_type = postgresql.ENUM(
    "bank_loan", "policy_fund", "support_program", "guarantee",
    name="product_type", create_type=False,
)
product_status = postgresql.ENUM(
    "active", "upcoming", "closed", "suspended", "unknown",
    name="product_status", create_type=False,
)
organization_role = postgresql.ENUM(
    "lender", "guarantor", "operator", "authority", "publisher",
    name="organization_role", create_type=False,
)
benefit_type = postgresql.ENUM(
    "loan", "guarantee", "interest_subsidy", "grant", "other",
    name="benefit_type", create_type=False,
)
rule_operator = postgresql.ENUM(
    "equals", "not_equals", "in", "not_in", "greater_than", "greater_than_or_equal",
    "less_than", "less_than_or_equal", "between", "contains",
    name="rule_operator", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        organization_type, acquisition_mode, product_type, product_status,
        organization_role, benefit_type, rule_operator,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("organization_type", organization_type, nullable=False),
        sa.Column("homepage_url", sa.String(length=2000), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("code", name="uq_organizations_code"),
    )
    op.create_table(
        "data_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("acquisition_mode", acquisition_mode, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("base_url", sa.String(length=2000), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_data_sources_organization_id_organizations", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_sources"),
        sa.UniqueConstraint("key", name="uq_data_sources_key"),
    )
    op.create_table(
        "funding_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("product_type", product_type, nullable=False),
        sa.Column("status", product_status, server_default="unknown", nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("application_start_date", sa.Date(), nullable=True),
        sa.Column("application_end_date", sa.Date(), nullable=True),
        sa.Column("application_url", sa.String(length=2000), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "application_start_date IS NULL OR application_end_date IS NULL "
            "OR application_start_date <= application_end_date",
            name="ck_funding_products_application_date_order",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_funding_products"),
        sa.UniqueConstraint("slug", name="uq_funding_products_slug"),
    )
    op.create_index(
        "ix_funding_products_application_dates", "funding_products",
        ["application_start_date", "application_end_date"], unique=False,
    )
    op.create_index(
        "ix_funding_products_type_status", "funding_products",
        ["product_type", "status"], unique=False,
    )
    op.create_table(
        "product_organizations",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", organization_role, nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_product_organizations_organization_id_organizations", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["funding_products.id"],
            name="fk_product_organizations_product_id_funding_products", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id", "organization_id", "role", name="pk_product_organizations"),
    )
    op.create_index(
        "ix_product_organizations_organization_role", "product_organizations",
        ["organization_id", "role"], unique=False,
    )
    op.create_table(
        "product_benefits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benefit_type", benefit_type, nullable=False),
        sa.Column("amount_min_krw", sa.BigInteger(), nullable=True),
        sa.Column("amount_max_krw", sa.BigInteger(), nullable=True),
        sa.Column("interest_rate_min_pct", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("interest_rate_max_pct", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("guarantee_rate_pct", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("interest_subsidy_rate_pct", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("term_min_months", sa.Integer(), nullable=True),
        sa.Column("term_max_months", sa.Integer(), nullable=True),
        sa.Column("grace_period_months", sa.Integer(), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount_min_krw IS NULL OR amount_min_krw >= 0", name="ck_product_benefits_amount_min_nonnegative"),
        sa.CheckConstraint("amount_max_krw IS NULL OR amount_max_krw >= 0", name="ck_product_benefits_amount_max_nonnegative"),
        sa.CheckConstraint("amount_min_krw IS NULL OR amount_max_krw IS NULL OR amount_min_krw <= amount_max_krw", name="ck_product_benefits_amount_order"),
        sa.CheckConstraint("interest_rate_min_pct IS NULL OR (interest_rate_min_pct >= 0 AND interest_rate_min_pct <= 100)", name="ck_product_benefits_interest_rate_min_range"),
        sa.CheckConstraint("interest_rate_max_pct IS NULL OR (interest_rate_max_pct >= 0 AND interest_rate_max_pct <= 100)", name="ck_product_benefits_interest_rate_max_range"),
        sa.CheckConstraint("interest_rate_min_pct IS NULL OR interest_rate_max_pct IS NULL OR interest_rate_min_pct <= interest_rate_max_pct", name="ck_product_benefits_interest_rate_order"),
        sa.CheckConstraint("guarantee_rate_pct IS NULL OR (guarantee_rate_pct >= 0 AND guarantee_rate_pct <= 100)", name="ck_product_benefits_guarantee_rate_range"),
        sa.CheckConstraint("interest_subsidy_rate_pct IS NULL OR (interest_subsidy_rate_pct >= 0 AND interest_subsidy_rate_pct <= 100)", name="ck_product_benefits_interest_subsidy_rate_range"),
        sa.CheckConstraint("term_min_months IS NULL OR term_min_months >= 0", name="ck_product_benefits_term_min_nonnegative"),
        sa.CheckConstraint("term_max_months IS NULL OR term_max_months >= 0", name="ck_product_benefits_term_max_nonnegative"),
        sa.CheckConstraint("term_min_months IS NULL OR term_max_months IS NULL OR term_min_months <= term_max_months", name="ck_product_benefits_term_order"),
        sa.CheckConstraint("grace_period_months IS NULL OR grace_period_months >= 0", name="ck_product_benefits_grace_nonnegative"),
        sa.ForeignKeyConstraint(
            ["product_id"], ["funding_products.id"],
            name="fk_product_benefits_product_id_funding_products", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_benefits"),
    )
    op.create_index(
        "ix_product_benefits_product_type", "product_benefits",
        ["product_id", "benefit_type"], unique=False,
    )
    op.create_table(
        "eligibility_rule_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_eligibility_rule_groups_position_nonnegative"),
        sa.ForeignKeyConstraint(
            ["product_id"], ["funding_products.id"],
            name="fk_eligibility_rule_groups_product_id_funding_products", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_eligibility_rule_groups"),
        sa.UniqueConstraint("product_id", "position", name="uq_eligibility_rule_groups_product_position"),
    )
    op.create_table(
        "eligibility_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("field_key", sa.String(length=100), nullable=False),
        sa.Column("operator", rule_operator, nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("extra_data", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_eligibility_rules_position_nonnegative"),
        sa.ForeignKeyConstraint(
            ["group_id"], ["eligibility_rule_groups.id"],
            name="fk_eligibility_rules_group_id_eligibility_rule_groups", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_eligibility_rules"),
        sa.UniqueConstraint("group_id", "position", name="uq_eligibility_rules_group_position"),
    )
    op.create_index(
        "ix_eligibility_rules_field_operator", "eligibility_rules",
        ["field_key", "operator"], unique=False,
    )
    op.create_index(
        "ix_eligibility_rules_value_gin", "eligibility_rules", ["value"],
        unique=False, postgresql_using="gin",
    )
    op.create_table(
        "product_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("official_url", sa.String(length=2000), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_id"], ["data_sources.id"],
            name="fk_product_sources_data_source_id_data_sources", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["funding_products.id"],
            name="fk_product_sources_product_id_funding_products", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_sources"),
        sa.UniqueConstraint("data_source_id", "external_id", name="uq_product_sources_source_external_id"),
        sa.UniqueConstraint("data_source_id", "official_url", name="uq_product_sources_source_url"),
    )
    op.create_index(
        "ix_product_sources_product_checked", "product_sources",
        ["product_id", "checked_at"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_product_sources_product_checked", table_name="product_sources")
    op.drop_table("product_sources")
    op.drop_index("ix_eligibility_rules_value_gin", table_name="eligibility_rules")
    op.drop_index("ix_eligibility_rules_field_operator", table_name="eligibility_rules")
    op.drop_table("eligibility_rules")
    op.drop_table("eligibility_rule_groups")
    op.drop_index("ix_product_benefits_product_type", table_name="product_benefits")
    op.drop_table("product_benefits")
    op.drop_index("ix_product_organizations_organization_role", table_name="product_organizations")
    op.drop_table("product_organizations")
    op.drop_index("ix_funding_products_type_status", table_name="funding_products")
    op.drop_index("ix_funding_products_application_dates", table_name="funding_products")
    op.drop_table("funding_products")
    op.drop_table("data_sources")
    op.drop_table("organizations")

    bind = op.get_bind()
    for enum_type in (
        rule_operator, benefit_type, organization_role, product_status,
        product_type, acquisition_mode, organization_type,
    ):
        enum_type.drop(bind, checkfirst=True)
