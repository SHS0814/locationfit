from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


def _enum(enum_class: type[Enum], name: str) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        values_callable=lambda values: [item.value for item in values],
    )


class OrganizationType(str, Enum):
    BANK = "bank"
    PUBLIC_AGENCY = "public_agency"
    LOCAL_GOVERNMENT = "local_government"
    GUARANTEE_FOUNDATION = "guarantee_foundation"
    AGGREGATOR = "aggregator"


class AcquisitionMode(str, Enum):
    OFFICIAL_API = "official_api"
    CURATED_OFFICIAL_SOURCE = "curated_official_source"


class ProductType(str, Enum):
    BANK_LOAN = "bank_loan"
    POLICY_FUND = "policy_fund"
    SUPPORT_PROGRAM = "support_program"
    GUARANTEE = "guarantee"


class ProductStatus(str, Enum):
    ACTIVE = "active"
    UPCOMING = "upcoming"
    CLOSED = "closed"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


class OrganizationRole(str, Enum):
    LENDER = "lender"
    GUARANTOR = "guarantor"
    OPERATOR = "operator"
    AUTHORITY = "authority"
    PUBLISHER = "publisher"


class BenefitType(str, Enum):
    LOAN = "loan"
    GUARANTEE = "guarantee"
    INTEREST_SUBSIDY = "interest_subsidy"
    GRANT = "grant"
    OTHER = "other"


class RuleOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    BETWEEN = "between"
    CONTAINS = "contains"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    organization_type: Mapped[OrganizationType] = mapped_column(
        _enum(OrganizationType, "organization_type"), nullable=False
    )
    homepage_url: Mapped[str | None] = mapped_column(String(2_000))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    data_sources: Mapped[list[DataSource]] = relationship(back_populates="organization")
    product_roles: Mapped[list[ProductOrganization]] = relationship(back_populates="organization")


class DataSource(TimestampMixin, Base):
    __tablename__ = "data_sources"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    acquisition_mode: Mapped[AcquisitionMode] = mapped_column(
        _enum(AcquisitionMode, "acquisition_mode"), nullable=False
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    base_url: Mapped[str] = mapped_column(String(2_000), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    organization: Mapped[Organization | None] = relationship(back_populates="data_sources")
    product_sources: Mapped[list[ProductSource]] = relationship(back_populates="data_source")


class FundingProduct(TimestampMixin, Base):
    __tablename__ = "funding_products"
    __table_args__ = (
        CheckConstraint(
            "application_start_date IS NULL OR application_end_date IS NULL "
            "OR application_start_date <= application_end_date",
            name="application_date_order",
        ),
        Index("ix_funding_products_type_status", "product_type", "status"),
        Index("ix_funding_products_application_dates", "application_start_date", "application_end_date"),
        Index("ix_funding_products_extra_data_gin", "extra_data", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    product_type: Mapped[ProductType] = mapped_column(
        _enum(ProductType, "product_type"), nullable=False
    )
    status: Mapped[ProductStatus] = mapped_column(
        _enum(ProductStatus, "product_status"),
        nullable=False,
        default=ProductStatus.UNKNOWN,
        server_default=ProductStatus.UNKNOWN.value,
    )
    summary: Mapped[str | None] = mapped_column(Text)
    application_start_date: Mapped[date | None] = mapped_column(Date)
    application_end_date: Mapped[date | None] = mapped_column(Date)
    application_url: Mapped[str | None] = mapped_column(String(2_000))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    organization_roles: Mapped[list[ProductOrganization]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    benefits: Mapped[list[ProductBenefit]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    eligibility_groups: Mapped[list[EligibilityRuleGroup]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    sources: Mapped[list[ProductSource]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductOrganization(Base):
    __tablename__ = "product_organizations"
    __table_args__ = (
        Index("ix_product_organizations_organization_role", "organization_id", "role"),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("funding_products.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[OrganizationRole] = mapped_column(
        _enum(OrganizationRole, "organization_role"), primary_key=True
    )

    product: Mapped[FundingProduct] = relationship(back_populates="organization_roles")
    organization: Mapped[Organization] = relationship(back_populates="product_roles")


class ProductBenefit(TimestampMixin, Base):
    __tablename__ = "product_benefits"
    __table_args__ = (
        CheckConstraint("amount_min_krw IS NULL OR amount_min_krw >= 0", name="amount_min_nonnegative"),
        CheckConstraint("amount_max_krw IS NULL OR amount_max_krw >= 0", name="amount_max_nonnegative"),
        CheckConstraint(
            "amount_min_krw IS NULL OR amount_max_krw IS NULL OR amount_min_krw <= amount_max_krw",
            name="amount_order",
        ),
        CheckConstraint(
            "interest_rate_min_pct IS NULL OR (interest_rate_min_pct >= 0 AND interest_rate_min_pct <= 100)",
            name="interest_rate_min_range",
        ),
        CheckConstraint(
            "interest_rate_max_pct IS NULL OR (interest_rate_max_pct >= 0 AND interest_rate_max_pct <= 100)",
            name="interest_rate_max_range",
        ),
        CheckConstraint(
            "interest_rate_min_pct IS NULL OR interest_rate_max_pct IS NULL "
            "OR interest_rate_min_pct <= interest_rate_max_pct",
            name="interest_rate_order",
        ),
        CheckConstraint(
            "guarantee_rate_pct IS NULL OR (guarantee_rate_pct >= 0 AND guarantee_rate_pct <= 100)",
            name="guarantee_rate_range",
        ),
        CheckConstraint(
            "interest_subsidy_rate_pct IS NULL "
            "OR (interest_subsidy_rate_pct >= 0 AND interest_subsidy_rate_pct <= 100)",
            name="interest_subsidy_rate_range",
        ),
        CheckConstraint(
            "guarantee_fee_rate_pct IS NULL "
            "OR (guarantee_fee_rate_pct >= 0 AND guarantee_fee_rate_pct <= 100)",
            name="guarantee_fee_rate_range",
        ),
        CheckConstraint("term_min_months IS NULL OR term_min_months >= 0", name="term_min_nonnegative"),
        CheckConstraint("term_max_months IS NULL OR term_max_months >= 0", name="term_max_nonnegative"),
        CheckConstraint(
            "term_min_months IS NULL OR term_max_months IS NULL OR term_min_months <= term_max_months",
            name="term_order",
        ),
        CheckConstraint("grace_period_months IS NULL OR grace_period_months >= 0", name="grace_nonnegative"),
        Index("ix_product_benefits_product_type", "product_id", "benefit_type"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("funding_products.id", ondelete="CASCADE"), nullable=False
    )
    benefit_type: Mapped[BenefitType] = mapped_column(
        _enum(BenefitType, "benefit_type"), nullable=False
    )
    amount_min_krw: Mapped[int | None] = mapped_column(BigInteger)
    amount_max_krw: Mapped[int | None] = mapped_column(BigInteger)
    interest_rate_min_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    interest_rate_max_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    guarantee_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    interest_subsidy_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    guarantee_fee_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    term_min_months: Mapped[int | None] = mapped_column(Integer)
    term_max_months: Mapped[int | None] = mapped_column(Integer)
    grace_period_months: Mapped[int | None] = mapped_column(Integer)
    original_text: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    product: Mapped[FundingProduct] = relationship(back_populates="benefits")


class EligibilityRuleGroup(TimestampMixin, Base):
    __tablename__ = "eligibility_rule_groups"
    __table_args__ = (
        UniqueConstraint("product_id", "position", name="uq_eligibility_rule_groups_product_position"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("funding_products.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)

    product: Mapped[FundingProduct] = relationship(back_populates="eligibility_groups")
    rules: Mapped[list[EligibilityRule]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class EligibilityRule(TimestampMixin, Base):
    __tablename__ = "eligibility_rules"
    __table_args__ = (
        UniqueConstraint("group_id", "position", name="uq_eligibility_rules_group_position"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        Index("ix_eligibility_rules_field_operator", "field_key", "operator"),
        Index("ix_eligibility_rules_value_gin", "value", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("eligibility_rule_groups.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    operator: Mapped[RuleOperator] = mapped_column(
        _enum(RuleOperator, "rule_operator"), nullable=False
    )
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    group: Mapped[EligibilityRuleGroup] = relationship(back_populates="rules")


class ProductSource(TimestampMixin, Base):
    __tablename__ = "product_sources"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "data_source_id", "external_id",
            name="uq_product_sources_product_source_external_id",
        ),
        UniqueConstraint(
            "product_id", "data_source_id", "official_url",
            name="uq_product_sources_product_source_url",
        ),
        Index("ix_product_sources_product_checked", "product_id", "checked_at"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("funding_products.id", ondelete="CASCADE"), nullable=False
    )
    data_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    official_url: Mapped[str] = mapped_column(String(2_000), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    raw_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    product: Mapped[FundingProduct] = relationship(back_populates="sources")
    data_source: Mapped[DataSource] = relationship(back_populates="product_sources")
