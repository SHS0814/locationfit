from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.db.models import (
    AcquisitionMode,
    BenefitType,
    OrganizationRole,
    OrganizationType,
    ProductStatus,
    ProductType,
    RuleOperator,
)


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrganizationRecord(CatalogModel):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,99}$")
    name: str = Field(min_length=1, max_length=200)
    organization_type: OrganizationType
    homepage_url: str | None = None
    is_active: bool = True

    @field_validator("homepage_url")
    @classmethod
    def validate_homepage_url(cls, value: str | None) -> str | None:
        return require_http_url(value, "homepage_url")


class DataSourceRecord(CatalogModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,99}$")
    name: str = Field(min_length=1, max_length=200)
    acquisition_mode: AcquisitionMode
    organization_code: str | None = None
    base_url: str
    is_active: bool = True

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return require_http_url(value, "base_url") or value


class ProductOrganizationRecord(CatalogModel):
    organization_code: str
    role: OrganizationRole


class BenefitRecord(CatalogModel):
    benefit_type: BenefitType
    amount_min_krw: int | None = Field(default=None, ge=0)
    amount_max_krw: int | None = Field(default=None, ge=0)
    interest_rate_min_pct: Decimal | None = Field(default=None, ge=0, le=100)
    interest_rate_max_pct: Decimal | None = Field(default=None, ge=0, le=100)
    guarantee_rate_pct: Decimal | None = Field(default=None, ge=0, le=100)
    interest_subsidy_rate_pct: Decimal | None = Field(default=None, ge=0, le=100)
    guarantee_fee_rate_pct: Decimal | None = Field(default=None, ge=0, le=100)
    term_min_months: int | None = Field(default=None, ge=0)
    term_max_months: int | None = Field(default=None, ge=0)
    grace_period_months: int | None = Field(default=None, ge=0)
    original_text: str | None = None
    extra_data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_ranges(self) -> "BenefitRecord":
        for minimum, maximum, label in (
            (self.amount_min_krw, self.amount_max_krw, "지원금액"),
            (self.interest_rate_min_pct, self.interest_rate_max_pct, "금리"),
            (self.term_min_months, self.term_max_months, "기간"),
        ):
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"{label} 최솟값은 최댓값보다 클 수 없습니다.")
        return self


class EligibilityRuleRecord(CatalogModel):
    field_key: str = Field(min_length=1, max_length=100)
    operator: RuleOperator
    value: Any
    unit: str | None = None
    description: str = Field(min_length=1)
    extra_data: dict[str, Any] = Field(default_factory=dict)


class EligibilityGroupRecord(CatalogModel):
    name: str | None = None
    description: str | None = None
    rules: list[EligibilityRuleRecord] = Field(default_factory=list)


class ProductSourceRecord(CatalogModel):
    data_source_key: str
    external_id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    official_url: str
    published_at: datetime | None = None
    checked_at: datetime
    content_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    raw_data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("official_url")
    @classmethod
    def validate_official_url(cls, value: str) -> str:
        return require_http_url(value, "official_url") or value


class ProductRecord(CatalogModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,159}$")
    name: str = Field(min_length=1, max_length=300)
    product_type: ProductType
    status: ProductStatus = ProductStatus.UNKNOWN
    summary: str | None = None
    application_start_date: date | None = None
    application_end_date: date | None = None
    application_url: str | None = None
    last_checked_at: datetime | None = None
    extra_data: dict[str, Any] = Field(default_factory=dict)
    organization_roles: list[ProductOrganizationRecord] = Field(default_factory=list)
    benefits: list[BenefitRecord] = Field(default_factory=list)
    eligibility_groups: list[EligibilityGroupRecord] = Field(default_factory=list)
    sources: list[ProductSourceRecord] = Field(default_factory=list)

    @field_validator("application_url")
    @classmethod
    def validate_application_url(cls, value: str | None) -> str | None:
        return require_http_url(value, "application_url")

    @model_validator(mode="after")
    def validate_dates(self) -> "ProductRecord":
        if (
            self.application_start_date is not None
            and self.application_end_date is not None
            and self.application_start_date > self.application_end_date
        ):
            raise ValueError("신청 시작일은 종료일보다 늦을 수 없습니다.")
        return self


class SourceAliasRecord(CatalogModel):
    data_source_key: str
    external_id: str
    product_slugs: list[str] = Field(min_length=1)


class CatalogDocument(CatalogModel):
    catalog_version: Literal[1]
    organizations: list[OrganizationRecord] = Field(default_factory=list)
    data_sources: list[DataSourceRecord] = Field(default_factory=list)
    products: list[ProductRecord] = Field(default_factory=list)
    source_aliases: list[SourceAliasRecord] = Field(default_factory=list)


class CatalogBundle(CatalogModel):
    catalog_version: Literal[1] = 1
    organizations: list[OrganizationRecord] = Field(default_factory=list)
    data_sources: list[DataSourceRecord] = Field(default_factory=list)
    products: list[ProductRecord] = Field(default_factory=list)
    source_aliases: list[SourceAliasRecord] = Field(default_factory=list)


class ValidationIssue(CatalogModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    location: str | None = None


class ValidationReport(CatalogModel):
    checked_at: datetime
    product_count: int
    active_count: int
    upcoming_count: int
    closed_count: int
    source_counts: dict[str, int]
    products_with_amount: int
    products_with_rate: int
    structured_rule_count: int
    issues: list[ValidationIssue]

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)


def require_http_url(value: str | None, field_name: str) -> str | None:
    if value is not None and not value.startswith(("http://", "https://")):
        raise ValueError(f"{field_name}은 HTTP(S) URL이어야 합니다.")
    return value
