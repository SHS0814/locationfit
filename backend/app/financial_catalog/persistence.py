from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models import (
    DataSource,
    EligibilityRule,
    EligibilityRuleGroup,
    FundingProduct,
    Organization,
    ProductBenefit,
    ProductOrganization,
    ProductSource,
)
from backend.app.financial_catalog.contracts import (
    BenefitRecord,
    CatalogBundle,
    DataSourceRecord,
    EligibilityGroupRecord,
    EligibilityRuleRecord,
    OrganizationRecord,
    ProductOrganizationRecord,
    ProductRecord,
    ProductSourceRecord,
)
from backend.app.financial_catalog.loader import catalog_digest

CATALOG_ADVISORY_LOCK = 4_601_728_031


def lock_catalog(session: Session) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": CATALOG_ADVISORY_LOCK})


def bundle_from_database(session: Session) -> CatalogBundle:
    organizations = list(session.scalars(select(Organization).order_by(Organization.code)))
    data_sources = list(session.scalars(
        select(DataSource)
        .options(selectinload(DataSource.organization))
        .order_by(DataSource.key)
    ))
    products = list(session.scalars(
        select(FundingProduct)
        .options(
            selectinload(FundingProduct.organization_roles).selectinload(
                ProductOrganization.organization
            ),
            selectinload(FundingProduct.benefits),
            selectinload(FundingProduct.eligibility_groups).selectinload(
                EligibilityRuleGroup.rules
            ),
            selectinload(FundingProduct.sources).selectinload(ProductSource.data_source),
        )
        .order_by(FundingProduct.slug)
    ))
    return CatalogBundle(
        organizations=[OrganizationRecord(
            code=item.code,
            name=item.name,
            organization_type=item.organization_type,
            homepage_url=item.homepage_url,
            is_active=item.is_active,
        ) for item in organizations],
        data_sources=[DataSourceRecord(
            key=item.key,
            name=item.name,
            acquisition_mode=item.acquisition_mode,
            organization_code=item.organization.code if item.organization else None,
            base_url=item.base_url,
            is_active=item.is_active,
        ) for item in data_sources],
        products=[_product_record(item) for item in products],
    )


def database_digest(session: Session) -> str:
    return catalog_digest(bundle_from_database(session))


def apply_bundle(
    session: Session,
    bundle: CatalogBundle,
    *,
    close_expired_bizinfo: bool = False,
    as_of: date | None = None,
) -> dict[str, int]:
    lock_catalog(session)

    organization_by_code = {
        item.code: item for item in session.scalars(select(Organization))
    }
    for record in bundle.organizations:
        item = organization_by_code.get(record.code)
        if item is None:
            item = Organization(code=record.code, name=record.name, organization_type=record.organization_type)
            session.add(item)
            organization_by_code[record.code] = item
        item.name = record.name
        item.organization_type = record.organization_type
        item.homepage_url = record.homepage_url
        item.is_active = record.is_active
    session.flush()

    source_by_key = {item.key: item for item in session.scalars(select(DataSource))}
    for record in bundle.data_sources:
        item = source_by_key.get(record.key)
        if item is None:
            item = DataSource(key=record.key, name=record.name, acquisition_mode=record.acquisition_mode, base_url=record.base_url)
            session.add(item)
            source_by_key[record.key] = item
        item.name = record.name
        item.acquisition_mode = record.acquisition_mode
        item.organization = (
            organization_by_code[record.organization_code] if record.organization_code else None
        )
        item.base_url = record.base_url
        item.is_active = record.is_active
    session.flush()

    product_by_slug = {item.slug: item for item in session.scalars(select(FundingProduct))}
    added = 0
    updated = 0
    for record in bundle.products:
        product = product_by_slug.get(record.slug)
        if product is None:
            product = FundingProduct(slug=record.slug, name=record.name, product_type=record.product_type)
            session.add(product)
            product_by_slug[record.slug] = product
            added += 1
        else:
            updated += 1
        _assign_product_fields(product, record)

        product.organization_roles.clear()
        product.benefits.clear()
        product.eligibility_groups.clear()
        desired_source_keys = {source.data_source_key for source in record.sources}
        product.sources[:] = [
            source for source in product.sources if source.data_source.key not in desired_source_keys
        ]
        session.flush()

        product.organization_roles.extend(ProductOrganization(
            organization=organization_by_code[role.organization_code],
            role=role.role,
        ) for role in record.organization_roles)
        product.benefits.extend(ProductBenefit(**benefit.model_dump()) for benefit in record.benefits)
        for position, group_record in enumerate(record.eligibility_groups):
            group = EligibilityRuleGroup(
                position=position,
                name=group_record.name,
                description=group_record.description,
            )
            group.rules.extend(EligibilityRule(
                position=rule_position,
                **rule.model_dump(),
            ) for rule_position, rule in enumerate(group_record.rules))
            product.eligibility_groups.append(group)
        product.sources.extend(ProductSource(
            data_source=source_by_key[source.data_source_key],
            external_id=source.external_id,
            title=source.title,
            official_url=source.official_url,
            published_at=source.published_at,
            checked_at=source.checked_at,
            content_hash=source.content_hash,
            raw_data=source.raw_data,
        ) for source in record.sources)
        session.flush()

    desired_product_slugs = {record.slug for record in bundle.products}
    closed = 0
    if close_expired_bizinfo:
        reference_date = as_of or date.today()
        candidates = session.scalars(
            select(FundingProduct)
            .join(FundingProduct.sources)
            .join(ProductSource.data_source)
            .where(DataSource.key == "bizinfo-api")
            .distinct()
        )
        for product in candidates:
            is_missing_api_product = (
                product.slug not in desired_product_slugs
                and product.extra_data.get("curation_level") == "api_metadata_only"
            )
            is_expired = (
                product.application_end_date is not None
                and product.application_end_date < reference_date
            )
            if (is_missing_api_product or is_expired) and product.status.value != "closed":
                product.status = type(product.status).CLOSED
                closed += 1
    session.flush()
    return {"added": added, "updated": updated, "closed": closed}


def _assign_product_fields(product: FundingProduct, record: ProductRecord) -> None:
    product.name = record.name
    product.product_type = record.product_type
    product.status = record.status
    product.summary = record.summary
    product.application_start_date = record.application_start_date
    product.application_end_date = record.application_end_date
    product.application_url = record.application_url
    product.last_checked_at = record.last_checked_at
    product.extra_data = record.extra_data


def _product_record(item: FundingProduct) -> ProductRecord:
    return ProductRecord(
        slug=item.slug,
        name=item.name,
        product_type=item.product_type,
        status=item.status,
        summary=item.summary,
        application_start_date=item.application_start_date,
        application_end_date=item.application_end_date,
        application_url=item.application_url,
        last_checked_at=item.last_checked_at,
        extra_data=item.extra_data,
        organization_roles=[ProductOrganizationRecord(
            organization_code=role.organization.code,
            role=role.role,
        ) for role in sorted(
            item.organization_roles,
            key=lambda role: (role.organization.code, role.role.value),
        )],
        benefits=[_benefit_record(benefit) for benefit in sorted(
            item.benefits,
            key=lambda benefit: (
                benefit.benefit_type.value,
                benefit.amount_min_krw or -1,
                benefit.amount_max_krw or -1,
                benefit.original_text or "",
            ),
        )],
        eligibility_groups=[EligibilityGroupRecord(
            name=group.name,
            description=group.description,
            rules=[EligibilityRuleRecord(
                field_key=rule.field_key,
                operator=rule.operator,
                value=rule.value,
                unit=rule.unit,
                description=rule.description,
                extra_data=rule.extra_data,
            ) for rule in sorted(group.rules, key=lambda rule: rule.position)],
        ) for group in sorted(item.eligibility_groups, key=lambda group: group.position)],
        sources=[ProductSourceRecord(
            data_source_key=source.data_source.key,
            external_id=source.external_id,
            title=source.title,
            official_url=source.official_url,
            published_at=source.published_at,
            checked_at=source.checked_at,
            content_hash=source.content_hash,
            raw_data=source.raw_data,
        ) for source in sorted(
            item.sources,
            key=lambda source: (source.data_source.key, source.external_id or "", source.official_url),
        )],
    )


def _benefit_record(item: ProductBenefit) -> BenefitRecord:
    fields: dict[str, Any] = {
        "benefit_type": item.benefit_type,
        "amount_min_krw": item.amount_min_krw,
        "amount_max_krw": item.amount_max_krw,
        "interest_rate_min_pct": item.interest_rate_min_pct,
        "interest_rate_max_pct": item.interest_rate_max_pct,
        "guarantee_rate_pct": item.guarantee_rate_pct,
        "interest_subsidy_rate_pct": item.interest_subsidy_rate_pct,
        "guarantee_fee_rate_pct": item.guarantee_fee_rate_pct,
        "term_min_months": item.term_min_months,
        "term_max_months": item.term_max_months,
        "grace_period_months": item.grace_period_months,
        "original_text": item.original_text,
        "extra_data": item.extra_data,
    }
    return BenefitRecord(**fields)
