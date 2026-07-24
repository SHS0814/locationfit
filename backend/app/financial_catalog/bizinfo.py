from __future__ import annotations

from datetime import UTC, date, datetime
import hashlib
import html
import json
import re
import time
from typing import Any

import httpx

from backend.app.db.models import (
    AcquisitionMode,
    OrganizationRole,
    OrganizationType,
    ProductStatus,
    ProductType,
    RuleOperator,
)
from backend.app.financial_catalog.contracts import (
    CatalogBundle,
    DataSourceRecord,
    EligibilityGroupRecord,
    EligibilityRuleRecord,
    OrganizationRecord,
    ProductOrganizationRecord,
    ProductRecord,
    ProductSourceRecord,
)


BIZINFO_API_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"
TARGET_KEYWORDS = ("소상공인", "개인사업자", "예비창업", "창업기업")


def _plain_text(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(html.unescape(text).split())


def _first(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _parse_period(value: str) -> tuple[date | None, date | None, str | None]:
    digits = re.findall(r"(?<!\d)(\d{8})(?!\d)", value.replace("-", ""))
    parsed = [datetime.strptime(item, "%Y%m%d").date() for item in digits[:2]]
    if len(parsed) >= 2:
        return parsed[0], parsed[1], None
    if len(parsed) == 1:
        return parsed[0], None, value
    return None, None, value or None


def _status(start: date | None, end: date | None, as_of: date) -> ProductStatus:
    if end is not None and end < as_of:
        return ProductStatus.CLOSED
    if start is not None and start > as_of:
        return ProductStatus.UPCOMING
    return ProductStatus.ACTIVE


def _organization_code(name: str) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
    return f"bizinfo-org-{digest}"


def _content_hash(item: dict[str, Any]) -> str:
    payload = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BizinfoClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 15,
        page_size: int = 100,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("기업마당 수집에는 BIZINFO_API_KEY가 필요합니다.")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.page_size = page_size
        self.transport = transport

    def fetch_financial_announcements(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        page = 1
        total: int | None = None
        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            transport=self.transport,
        ) as client:
            while total is None or len(output) < total:
                payload = self._request_page(client, page)
                channel = payload.get("jsonArray", payload)
                raw_items = channel.get("item", []) if isinstance(channel, dict) else []
                items = raw_items if isinstance(raw_items, list) else [raw_items]
                output.extend(item for item in items if isinstance(item, dict))
                raw_total = channel.get("totCnt") if isinstance(channel, dict) else None
                if raw_total is None and items:
                    raw_total = items[0].get("totCnt")
                total = int(raw_total) if raw_total not in (None, "") else len(output)
                if not items or len(items) < self.page_size:
                    break
                page += 1
        return output

    def _request_page(self, client: httpx.Client, page: int) -> dict[str, Any]:
        params = {
            "crtfcKey": self.api_key,
            "dataType": "json",
            "searchLclasId": "01",
            "pageUnit": str(self.page_size),
            "pageIndex": str(page),
        }
        last_error = "알 수 없는 오류"
        for attempt in range(3):
            try:
                response = client.get(BIZINFO_API_URL, params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("기업마당 API 응답 최상위 형식이 객체가 아닙니다.")
                return payload
            except httpx.HTTPStatusError as exc:
                last_error = f"HTTP {exc.response.status_code}"
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
            except httpx.RequestError as exc:
                last_error = type(exc).__name__
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
            except ValueError:
                last_error = "응답 형식 오류"
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        # httpx 예외에는 인증키가 포함된 요청 URL이 들어갈 수 있으므로 원본 예외를
        # 메시지나 예외 체인에 남기지 않는다.
        raise RuntimeError(f"기업마당 API 호출에 실패했습니다: {last_error}") from None


def merge_bizinfo_items(
    curated: CatalogBundle,
    items: list[dict[str, Any]],
    *,
    checked_at: datetime | None = None,
    include_closed: bool = False,
) -> CatalogBundle:
    bundle = curated.model_copy(deep=True)
    now = checked_at or datetime.now(UTC)
    sources = {item.key: item for item in bundle.data_sources}
    if "bizinfo-api" not in sources:
        bundle.data_sources.append(DataSourceRecord(
            key="bizinfo-api",
            name="기업마당 지원사업정보 API",
            acquisition_mode=AcquisitionMode.OFFICIAL_API,
            organization_code="bizinfo",
            base_url=BIZINFO_API_URL,
        ))
    organization_by_name = {item.name: item for item in bundle.organizations}
    product_by_slug = {item.slug: item for item in bundle.products}
    normalized_product_names = {_plain_text(item.name): item.slug for item in bundle.products}
    aliases = {
        (item.data_source_key, item.external_id): item.product_slugs
        for item in bundle.source_aliases
    }

    for item in items:
        external_id = _first(item, "pblancId", "seq")
        title = _plain_text(_first(item, "pblancNm", "title"))
        summary = _plain_text(_first(item, "bsnsSumryCn", "description"))
        target = _plain_text(_first(item, "trgetNm"))
        hashtags = _plain_text(_first(item, "hashTags"))
        searchable = " ".join((title, summary, target, hashtags))
        if not external_id or not title:
            continue
        if "서울" not in hashtags or not any(keyword in searchable for keyword in TARGET_KEYWORDS):
            continue
        period_text = _first(item, "reqstBeginEndDe", "reqstDt")
        start, end, closing_condition = _parse_period(period_text)
        status = _status(start, end, now.date())
        if status == ProductStatus.CLOSED and not include_closed:
            continue
        official_url = _first(item, "pblancUrl", "link")
        if not official_url:
            official_url = (
                "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?"
                f"pblancId={external_id}"
            )
        if official_url.startswith("http://"):
            official_url = "https://" + official_url.removeprefix("http://")
        source_record = ProductSourceRecord(
            data_source_key="bizinfo-api",
            external_id=external_id,
            title=title,
            official_url=official_url,
            published_at=_parse_published_at(_first(item, "creatPnttm", "pubDate")),
            checked_at=now,
            content_hash=_content_hash(item),
            raw_data=item,
        )
        alias_slugs = aliases.get(("bizinfo-api", external_id), [])
        if alias_slugs:
            for slug in alias_slugs:
                product = product_by_slug.get(slug)
                if product is None:
                    raise ValueError(f"기업마당 별칭 상품이 없습니다: {slug}")
                if not any(
                    source.data_source_key == "bizinfo-api" and source.external_id == external_id
                    for source in product.sources
                ):
                    product.sources.append(source_record.model_copy(deep=True))
            continue

        authority_name = _plain_text(_first(item, "jrsdInsttNm", "author")) or "소관기관 미확인"
        operator_name = _plain_text(_first(item, "excInsttNm")) or authority_name
        roles: list[ProductOrganizationRecord] = []
        for name, role in (
            (authority_name, OrganizationRole.AUTHORITY),
            (operator_name, OrganizationRole.OPERATOR),
        ):
            organization = organization_by_name.get(name)
            if organization is None:
                organization = OrganizationRecord(
                    code=_organization_code(name),
                    name=name,
                    organization_type=(
                        OrganizationType.LOCAL_GOVERNMENT
                        if "서울" in name or "구청" in name
                        else OrganizationType.PUBLIC_AGENCY
                    ),
                )
                bundle.organizations.append(organization)
                organization_by_name[name] = organization
            role_record = ProductOrganizationRecord(
                organization_code=organization.code,
                role=role,
            )
            if role_record not in roles:
                roles.append(role_record)

        slug = f"bizinfo-{external_id.lower().replace('_', '-')}"
        existing_name_slug = normalized_product_names.get(title)
        if existing_name_slug:
            raise ValueError(
                "기업마당 공고가 기존 상품명과 중복됩니다. source_aliases에 명시해주세요: "
                f"{external_id} -> {existing_name_slug}"
            )
        extra_data: dict[str, Any] = {
            "category": "금융",
            "curation_level": "api_metadata_only",
            "target_text": target,
            "application_period_text": period_text,
        }
        if closing_condition:
            extra_data["closing_condition"] = closing_condition
        rules = [EligibilityRuleRecord(
            field_key="region_code",
            operator=RuleOperator.IN,
            value=["11"],
            description="서울에서 신청 가능한 공고입니다.",
        )]
        if any(keyword in searchable for keyword in ("소상공인", "개인사업자")):
            rules.append(EligibilityRuleRecord(
                field_key="is_small_business",
                operator=RuleOperator.EQUALS,
                value=True,
                description="소상공인 또는 개인사업자 대상 표현이 포함된 공고입니다.",
            ))

        product = ProductRecord(
            slug=slug,
            name=title,
            product_type=ProductType.SUPPORT_PROGRAM,
            status=status,
            summary=summary or None,
            application_start_date=start,
            application_end_date=end,
            application_url=official_url,
            last_checked_at=now,
            extra_data=extra_data,
            organization_roles=roles,
            eligibility_groups=[EligibilityGroupRecord(
                name="기업마당 공개 대상정보",
                description="API의 대상·해시태그에서 확인되는 최소 조건만 구조화합니다.",
                rules=rules,
            )],
            sources=[source_record],
        )
        if slug in product_by_slug:
            raise ValueError(f"기업마당 상품 slug 충돌: {slug}")
        bundle.products.append(product)
        product_by_slug[slug] = product
        normalized_product_names[title] = slug
    return bundle


def _parse_published_at(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace(".", "-")
    for format_string in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(normalized, format_string)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
