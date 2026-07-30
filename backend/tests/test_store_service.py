from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from shapely.geometry import shape

from backend.app.main import app
from backend.app.services.recommender_service import RecommenderService
from backend.app.services.store_classification import COMPETITOR_TERMS, classify_store
from backend.app.services.store_service import (
    CommercialStoreService,
    SbizStoreProvider,
    StoreFetchResult,
    StoreUpstreamError,
)

ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts/current"


class FakeProvider:
    def __init__(self, rows: list[dict], *, fail_after: int | None = None) -> None:
        self.rows = rows
        self.fail_after = fail_after
        self.calls = 0

    async def fetch(self, geometry):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise StoreUpstreamError("temporary failure")
        return StoreFetchResult(self.rows, "202607")


def sample(recommender: RecommenderService):
    area_code = str(recommender.index.iloc[0]["area_code"])
    point = shape(recommender.boundaries[area_code]).representative_point()
    row = {
        "bizesId": "STORE-1",
        "bizesNm": "테스트 한식당",
        "indsLclsCd": "I2",
        "indsLclsNm": "음식",
        "indsMclsCd": "I201",
        "indsMclsNm": "한식",
        "indsSclsCd": "I20101",
        "indsSclsNm": "한식 음식점업",
        "rdnmAdr": "서울특별시 테스트로 1",
        "bldNm": "테스트빌딩",
        "flrNo": "1",
        "lon": str(point.x),
        "lat": str(point.y),
    }
    return area_code, row


def test_crosswalk_covers_all_service_industries_and_is_deterministic() -> None:
    recommender = RecommenderService(ARTIFACT_DIR)
    service_codes = {item["code"] for item in recommender.metadata()["industries"]}
    assert service_codes == set(COMPETITOR_TERMS)
    assert classify_store("CS100001", "음식", "한식", "한식 음식점업") == "competitor"
    assert classify_store("CS100001", "소매", "편의점", "체인화 편의점") == "complementary"
    assert classify_store("CS200025", "생활서비스", "세탁", "세탁소") == "daily_life"


def test_store_analysis_filters_boundary_classifies_and_caches() -> None:
    recommender = RecommenderService(ARTIFACT_DIR)
    area_code, row = sample(recommender)
    outside = {**row, "bizesId": "OUTSIDE", "lon": "129", "lat": "36"}
    provider = FakeProvider([row, row, outside])
    service = CommercialStoreService(recommender, provider)

    first = asyncio.run(service.analyse(area_code, "CS100001"))
    second = asyncio.run(service.analyse(area_code, "CS100001"))

    assert provider.calls == 1
    assert first["cache_status"] == "refreshed"
    assert second["cache_status"] == "fresh"
    assert [item["store_id"] for item in first["stores"]] == ["STORE-1"]
    assert first["stores"][0]["relation"] == "competitor"
    assert first["summary"]["competitor_count"] == 1
    assert first["reference_month"] == "202607"


def test_store_analysis_uses_stale_cache_when_refresh_fails() -> None:
    recommender = RecommenderService(ARTIFACT_DIR)
    area_code, row = sample(recommender)
    now = [0.0]
    provider = FakeProvider([row], fail_after=1)
    service = CommercialStoreService(
        recommender, provider, cache_ttl_seconds=10, stale_ttl_seconds=100,
        clock=lambda: now[0],
    )
    asyncio.run(service.analyse(area_code, "CS100001"))
    now[0] = 20
    stale = asyncio.run(service.analyse(area_code, "CS100001"))
    assert stale["cache_status"] == "stale"
    assert stale["warnings"]


def test_area_store_api_contract_with_injected_service() -> None:
    recommender = RecommenderService(ARTIFACT_DIR)
    area_code, row = sample(recommender)
    service = CommercialStoreService(recommender, FakeProvider([row]))
    with TestClient(app) as client:
        app.state.store_service = service
        response = client.get(
            f"/api/v1/areas/{area_code}/stores", params={"industry_code": "CS100001"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["request_id"] == response.headers["x-request-id"]
        assert body["stores"][0]["name"] == "테스트 한식당"
        assert "임대 가능 여부" in body["disclosure"]


def test_provider_rectangle_fallback_uses_coordinate_parameters_and_nested_json() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {"items": {"item": [{"bizesId": "A"}]}, "totalCount": 1, "stdrYm": "202607"},
        }})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = SbizStoreProvider(
        service_key="test", base_url="https://example.com", timeout_seconds=1,
        client=client, max_wkt_length=1,
    )
    result = asyncio.run(provider.fetch({
        "type": "Polygon",
        "coordinates": [[[126.9, 37.5], [127.0, 37.5], [127.0, 37.6], [126.9, 37.5]]],
    }))
    asyncio.run(client.aclose())
    assert result.reference_month == "202607"
    assert requests[0].url.path.endswith("/storeListInRectangle")
    assert requests[0].url.params["minx"] == "126.9"
    assert "key" not in requests[0].url.params


def test_provider_reports_api_authorization_failure_without_exposing_key() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(403, text="Forbidden", request=request)
    ))
    provider = SbizStoreProvider(
        service_key="secret-test-key", base_url="https://example.com",
        timeout_seconds=1, client=client,
    )
    try:
        asyncio.run(provider.fetch({
            "type": "Polygon",
            "coordinates": [[[126.9, 37.5], [127.0, 37.5], [127.0, 37.6], [126.9, 37.5]]],
        }))
    except StoreUpstreamError as exc:
        assert "활용신청 승인" in str(exc)
        assert "secret-test-key" not in str(exc)
    else:
        raise AssertionError("403 must fail")
    finally:
        asyncio.run(client.aclose())
