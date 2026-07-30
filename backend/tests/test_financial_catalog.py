from __future__ import annotations

import traceback
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from backend.app.db.models import ProductStatus
from backend.app.financial_catalog.bizinfo import BizinfoClient, merge_bizinfo_items
from backend.app.financial_catalog.loader import load_curated_catalog
from backend.app.financial_catalog.validation import validate_catalog

CATALOG_ROOT = Path(__file__).resolve().parents[2] / "config/financial_catalog"
CHECKED_AT = datetime(2026, 7, 29, tzinfo=UTC)


def test_curated_catalog_has_expected_initial_scope() -> None:
    bundle = load_curated_catalog(CATALOG_ROOT)
    report = validate_catalog(bundle, now=CHECKED_AT)

    assert len(bundle.organizations) == 9
    assert len(bundle.data_sources) == 7
    assert len(bundle.products) == 37
    assert sum(item.slug.startswith("kb-") for item in bundle.products) == 5
    assert sum(item.slug.startswith("semas-") for item in bundle.products) == 11
    assert sum(item.slug.startswith("seoul-") for item in bundle.products) == 16
    assert sum(item.slug.startswith("koreg-") for item in bundle.products) == 1
    assert sum(item.slug.startswith("kinfa-microfinance-") for item in bundle.products) == 4
    assert report.error_count == 0
    assert report.warning_count == 0


def test_unknown_financial_values_stay_null() -> None:
    bundle = load_curated_catalog(CATALOG_ROOT)
    product = next(item for item in bundle.products if item.slug == "semas-2026-general-management-stability")
    benefit = product.benefits[0]

    assert benefit.amount_max_krw is None
    assert benefit.interest_rate_min_pct is None
    assert benefit.original_text is not None


def test_microfinance_products_keep_official_structured_terms() -> None:
    bundle = load_curated_catalog(CATALOG_ROOT)
    products = {
        item.slug: item for item in bundle.products
        if item.slug.startswith("kinfa-microfinance-")
    }

    assert set(products) == {
        "kinfa-microfinance-startup",
        "kinfa-microfinance-operating",
        "kinfa-microfinance-facility-improvement",
        "kinfa-microfinance-emergency-living",
    }
    startup = products["kinfa-microfinance-startup"].benefits[0]
    emergency = products["kinfa-microfinance-emergency-living"].benefits[0]
    assert startup.amount_max_krw == 70_000_000
    assert startup.interest_rate_max_pct == 4.5
    assert startup.term_max_months == 60
    assert emergency.amount_max_krw == 10_000_000
    assert emergency.term_max_months == 48
    assert all(
        source.data_source_key == "kinfa-microfinance-products"
        for product in products.values()
        for source in product.sources
    )


def test_bizinfo_filters_to_seoul_small_business_and_keeps_unparsed_terms() -> None:
    bundle = load_curated_catalog(CATALOG_ROOT)
    items = [{
        "pblancId": "PBLN_TEST_1",
        "pblancNm": "[서울] 테스트 소상공인 운영지원",
        "pblancUrl": "https://www.bizinfo.go.kr/test/1",
        "jrsdInsttNm": "서울특별시",
        "excInsttNm": "테스트 수행기관",
        "bsnsSumryCn": "<p>개인사업자에게 최대 1억원을 지원합니다.</p>",
        "trgetNm": "소상공인",
        "hashTags": "금융,서울,소상공인",
        "reqstBeginEndDe": "20260720 ~ 20261231",
        "creatPnttm": "2026-07-20 09:00:00",
    }, {
        "pblancId": "PBLN_TEST_2",
        "pblancNm": "[부산] 테스트 소상공인 지원",
        "pblancUrl": "https://www.bizinfo.go.kr/test/2",
        "trgetNm": "소상공인",
        "hashTags": "금융,부산,소상공인",
    }]

    merged = merge_bizinfo_items(bundle, items, checked_at=CHECKED_AT)
    added = next(item for item in merged.products if item.slug == "bizinfo-pbln-test-1")

    assert len(merged.products) == 38
    assert added.status == ProductStatus.ACTIVE
    assert added.application_end_date.isoformat() == "2026-12-31"
    assert added.benefits == []
    assert added.extra_data["curation_level"] == "api_metadata_only"
    assert not any(item.slug == "bizinfo-pbln-test-2" for item in merged.products)


def test_bizinfo_alias_attaches_one_announcement_to_all_semas_products() -> None:
    bundle = load_curated_catalog(CATALOG_ROOT)
    item = {
        "pblancId": "PBLN_000000000124238",
        "pblancNm": "2026년 소상공인 정책자금 융자사업 3차 변경 공고",
        "pblancUrl": "https://www.bizinfo.go.kr/policy/124238",
        "jrsdInsttNm": "중소벤처기업부",
        "excInsttNm": "소상공인시장진흥공단",
        "trgetNm": "소상공인",
        "hashTags": "금융,서울,소상공인",
        "reqstBeginEndDe": "예산 소진시까지",
    }

    merged = merge_bizinfo_items(bundle, [item], checked_at=CHECKED_AT)
    semas = [product for product in merged.products if product.slug.startswith("semas-")]

    assert len(merged.products) == 37
    assert len(semas) == 11
    assert all(any(
        source.data_source_key == "bizinfo-api"
        and source.external_id == "PBLN_000000000124238"
        for source in product.sources
    ) for product in semas)


def test_bizinfo_founder_filter_does_not_claim_small_business_status() -> None:
    bundle = load_curated_catalog(CATALOG_ROOT)
    item = {
        "pblancId": "PBLN_FOUNDER_ONLY",
        "pblancNm": "[서울] 예비창업자 금융 지원",
        "pblancUrl": "https://www.bizinfo.go.kr/founder-only",
        "trgetNm": "예비창업자",
        "hashTags": "금융,서울,예비창업",
    }

    merged = merge_bizinfo_items(bundle, [item], checked_at=CHECKED_AT)
    product = next(item for item in merged.products if item.slug == "bizinfo-pbln-founder-only")
    fields = [
        rule.field_key
        for group in product.eligibility_groups
        for rule in group.rules
    ]

    assert fields == ["region_code"]


def test_exact_bizinfo_duplicate_requires_explicit_alias() -> None:
    bundle = load_curated_catalog(CATALOG_ROOT)
    item = {
        "pblancId": "PBLN_UNMAPPED",
        "pblancNm": "KB소상공인 신용대출",
        "pblancUrl": "https://www.bizinfo.go.kr/unmapped",
        "trgetNm": "소상공인",
        "hashTags": "금융,서울,소상공인",
    }

    with pytest.raises(ValueError, match="source_aliases"):
        merge_bizinfo_items(bundle, [item], checked_at=CHECKED_AT)


def test_bizinfo_client_paginates_without_exposing_api_key() -> None:
    requested_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params["pageIndex"]
        requested_pages.append(page)
        items = (
            [{"pblancId": "1", "totCnt": "3"}, {"pblancId": "2", "totCnt": "3"}]
            if page == "1"
            else [{"pblancId": "3", "totCnt": "3"}]
        )
        return httpx.Response(200, json={"jsonArray": {"item": items, "totCnt": "3"}})

    client = BizinfoClient(
        "secret-test-key",
        page_size=2,
        transport=httpx.MockTransport(handler),
    )
    items = client.fetch_financial_announcements()

    assert [item["pblancId"] for item in items] == ["1", "2", "3"]
    assert requested_pages == ["1", "2"]


def test_bizinfo_client_failure_does_not_expose_api_key() -> None:
    api_key = "secret-test-key"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request, text="failed")

    client = BizinfoClient(api_key, transport=httpx.MockTransport(handler))

    try:
        client.fetch_financial_announcements()
    except RuntimeError as exc:
        rendered = "".join(traceback.format_exception(exc))
        assert api_key not in rendered
        assert "crtfcKey" not in rendered
        assert "HTTP 500" in str(exc)
        assert exc.__cause__ is None
        assert exc.__suppress_context__ is True
    else:
        pytest.fail("기업마당 API 오류가 RuntimeError로 변환되지 않았습니다.")
