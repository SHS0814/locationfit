from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import time
from typing import Any, Callable, Protocol
from urllib.parse import unquote

import httpx
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from backend.app.services.recommender_service import RecommenderService
from backend.app.services.store_classification import COMPETITOR_TERMS, classify_store


STORE_SOURCE = "소상공인시장진흥공단 상가(상권)정보 API"
STORE_DISCLOSURE = (
    "현재 영업 업소 정보이며 임대 가능 여부, 보증금, 월세, 권리금 또는 매물 상태를 제공하지 않습니다."
)
RELATION_ORDER = {"competitor": 0, "complementary": 1, "daily_life": 2, "other": 3}


class StoreDataUnavailableError(RuntimeError):
    pass


class StoreUpstreamError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoreFetchResult:
    rows: list[dict[str, Any]]
    reference_month: str | None


class StoreProvider(Protocol):
    async def fetch(self, geometry: dict[str, Any]) -> StoreFetchResult: ...


def _as_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int, str | None, str, str]:
    if isinstance(payload.get("response"), dict):
        payload = payload["response"]
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    body = payload.get("body") if isinstance(payload.get("body"), dict) else payload
    result_code = str(
        header.get("resultCode") or body.get("resultCode") or payload.get("resultCode") or ""
    )
    result_message = str(
        header.get("resultMsg") or body.get("resultMsg") or payload.get("resultMsg") or ""
    )
    raw_items = body.get("items", [])
    if isinstance(raw_items, dict):
        raw_items = raw_items.get("item", raw_items.get("items", []))
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        raw_items = []
    rows = [item for item in raw_items if isinstance(item, dict)]
    total_raw = body.get("totalCount", payload.get("totalCount", len(rows)))
    try:
        total = int(total_raw)
    except (TypeError, ValueError):
        total = len(rows)
    reference_month = str(
        header.get("stdrYm") or body.get("stdrYm") or payload.get("stdrYm") or ""
    ) or None
    return rows, total, reference_month, result_code, result_message


class SbizStoreProvider:
    def __init__(
        self,
        *,
        service_key: str,
        base_url: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
        max_wkt_length: int = 6_000,
    ) -> None:
        self.service_key = unquote(service_key.strip())
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client = client
        self.max_wkt_length = max_wkt_length

    async def _page(
        self, endpoint: str, query: dict[str, str], page_no: int,
    ) -> tuple[list[dict[str, Any]], int, str | None]:
        if not self.service_key:
            raise StoreDataUnavailableError("DATA_GO_KR_SERVICE_KEY가 설정되지 않았습니다.")
        params = {
            "ServiceKey": self.service_key,
            "pageNo": str(page_no),
            "numOfRows": "1000",
            "type": "json",
            **query,
        }
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.get(f"{self.base_url}/{endpoint}", params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise StoreUpstreamError(
                    "공공데이터 API 인증이 거부되었습니다. 해당 API 활용신청 승인 상태와 인증키를 확인해주세요."
                ) from exc
            raise StoreUpstreamError(
                f"상가업소 API가 HTTP {exc.response.status_code} 오류를 반환했습니다."
            ) from exc
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise StoreUpstreamError("상가업소 정보를 불러오지 못했습니다.") from exc
        finally:
            if owns_client:
                await client.aclose()
        if not isinstance(payload, dict):
            raise StoreUpstreamError("상가업소 API 응답 형식이 올바르지 않습니다.")
        rows, total, reference_month, result_code, result_message = _as_items(payload)
        if result_code and result_code not in {"00", "0", "03"}:
            raise StoreUpstreamError(
                f"상가업소 API가 오류를 반환했습니다: {result_message or result_code}"
            )
        return rows, total, reference_month

    async def _all_pages(self, endpoint: str, query: dict[str, str]) -> StoreFetchResult:
        rows: list[dict[str, Any]] = []
        reference_months: list[str] = []
        page_no = 1
        while page_no <= 100:
            page_rows, total, reference_month = await self._page(endpoint, query, page_no)
            rows.extend(page_rows)
            if reference_month:
                reference_months.append(reference_month)
            if not page_rows or len(rows) >= total:
                break
            page_no += 1
        if page_no > 100:
            raise StoreUpstreamError("상가업소 API 페이지 수가 안전 한도를 초과했습니다.")
        return StoreFetchResult(rows, max(reference_months, default=None))

    async def fetch(self, geometry: dict[str, Any]) -> StoreFetchResult:
        geom = shape(geometry)
        polygons = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        use_rectangle = any(len(poly.wkt) > self.max_wkt_length for poly in polygons)
        if use_rectangle:
            minx, miny, maxx, maxy = geom.bounds
            return await self._all_pages("storeListInRectangle", {
                "minx": str(minx), "miny": str(miny),
                "maxx": str(maxx), "maxy": str(maxy),
            })
        results = await asyncio.gather(*[
            self._all_pages("storeListInPolygon", {"key": poly.wkt}) for poly in polygons
        ])
        rows = [row for result in results for row in result.rows]
        months = [result.reference_month for result in results if result.reference_month]
        return StoreFetchResult(rows, max(months, default=None))


@dataclass
class _CacheEntry:
    result: StoreFetchResult
    fetched_at: datetime
    stored_at: float


class CommercialStoreService:
    def __init__(
        self,
        recommender: RecommenderService,
        provider: StoreProvider,
        *,
        cache_ttl_seconds: float = 86_400,
        stale_ttl_seconds: float = 604_800,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.recommender = recommender
        self.provider = provider
        self.cache_ttl_seconds = cache_ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds
        self.clock = clock
        self._cache: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._industry_names = {
            item["code"]: item["name"] for item in recommender.metadata()["industries"]
        }
        missing = sorted(set(self._industry_names) - set(COMPETITOR_TERMS))
        if missing:
            raise RuntimeError(f"상가업소 업종 교차표가 없는 추천 업종이 있습니다: {missing}")

    def _area(self, area_code: str) -> dict[str, Any]:
        matches = self.recommender.index[
            self.recommender.index["area_code"].astype(str).eq(str(area_code))
        ]
        if matches.empty or str(area_code) not in self.recommender.boundaries:
            raise ValueError("존재하지 않는 상권 코드입니다.")
        row = matches.iloc[0]
        return {
            "area_code": str(area_code),
            "area_name": str(row["area_name"]),
            "area_size_sqm": float(row["area_size_sqm"]),
            "geometry": self.recommender.boundaries[str(area_code)],
        }

    @staticmethod
    def _cache_key(area: dict[str, Any]) -> str:
        encoded = json.dumps(area["geometry"], sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
        return f'{area["area_code"]}:{digest}'

    async def _fetch_cached(self, area: dict[str, Any]) -> tuple[_CacheEntry, str, list[str]]:
        key = self._cache_key(area)
        now = self.clock()
        entry = self._cache.get(key)
        if entry and now - entry.stored_at <= self.cache_ttl_seconds:
            return entry, "fresh", []
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = self.clock()
            entry = self._cache.get(key)
            if entry and now - entry.stored_at <= self.cache_ttl_seconds:
                return entry, "fresh", []
            try:
                result = await self.provider.fetch(area["geometry"])
            except (StoreDataUnavailableError, StoreUpstreamError):
                if entry and now - entry.stored_at <= self.stale_ttl_seconds:
                    return entry, "stale", [
                        "외부 API를 갱신하지 못해 이전 조회 결과를 표시합니다."
                    ]
                raise
            entry = _CacheEntry(result, datetime.now(UTC), now)
            self._cache[key] = entry
            return entry, "refreshed", []

    @staticmethod
    def _optional(row: dict[str, Any], key: str) -> str | None:
        value = row.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _normalise_rows(
        self,
        rows: list[dict[str, Any]],
        geometry: dict[str, Any],
        industry_code: str,
    ) -> list[dict[str, Any]]:
        boundary: BaseGeometry = shape(geometry)
        deduplicated: dict[str, dict[str, Any]] = {}
        for row in rows:
            store_id = self._optional(row, "bizesId")
            name = self._optional(row, "bizesNm")
            try:
                longitude = float(row.get("lon"))
                latitude = float(row.get("lat"))
            except (TypeError, ValueError):
                continue
            if 37 <= longitude <= 38 and 126 <= latitude <= 128:
                longitude, latitude = latitude, longitude
            if not store_id or not name or not (126 <= longitude <= 128 and 37 <= latitude <= 38):
                continue
            if not boundary.covers(Point(longitude, latitude)):
                continue
            large_name = self._optional(row, "indsLclsNm")
            middle_name = self._optional(row, "indsMclsNm")
            small_name = self._optional(row, "indsSclsNm")
            relation = classify_store(industry_code, large_name or "", middle_name or "", small_name or "")
            deduplicated[store_id] = {
                "store_id": store_id,
                "name": name,
                "branch_name": self._optional(row, "brchNm"),
                "industry_large_code": self._optional(row, "indsLclsCd"),
                "industry_large_name": large_name,
                "industry_middle_code": self._optional(row, "indsMclsCd"),
                "industry_middle_name": middle_name,
                "industry_small_code": self._optional(row, "indsSclsCd"),
                "industry_small_name": small_name,
                "ksic_code": self._optional(row, "ksicCd"),
                "ksic_name": self._optional(row, "ksicNm"),
                "road_address": self._optional(row, "rdnmAdr"),
                "lot_address": self._optional(row, "lnoAdr"),
                "building_name": self._optional(row, "bldNm"),
                "building_management_number": self._optional(row, "bldMngNo"),
                "floor": self._optional(row, "flrNo"),
                "unit": self._optional(row, "hoNo"),
                "longitude": longitude,
                "latitude": latitude,
                "relation": relation,
            }
        return sorted(
            deduplicated.values(),
            key=lambda item: (RELATION_ORDER[item["relation"]], item["name"], item["store_id"]),
        )

    @staticmethod
    def _summary(stores: list[dict[str, Any]], area_size_sqm: float) -> dict[str, Any]:
        area_sqkm = max(area_size_sqm / 1_000_000, 1e-9)
        relation_counter = Counter(item["relation"] for item in stores)
        category_counter = Counter(
            (
                item.get("industry_small_code") or item.get("industry_middle_code"),
                item.get("industry_small_name") or item.get("industry_middle_name") or "미분류",
            )
            for item in stores
        )
        competitor_count = relation_counter["competitor"]
        return {
            "total_count": len(stores),
            "total_density_per_sqkm": round(len(stores) / area_sqkm, 2),
            "competitor_count": competitor_count,
            "competitor_density_per_sqkm": round(competitor_count / area_sqkm, 2),
            "relation_counts": [
                {"relation": relation, "count": relation_counter[relation]}
                for relation in RELATION_ORDER
            ],
            "top_categories": [
                {"code": code, "name": name, "count": count}
                for (code, name), count in category_counter.most_common(5)
            ],
        }

    async def analyse(self, area_code: str, industry_code: str) -> dict[str, Any]:
        area = self._area(area_code)
        if industry_code not in self._industry_names:
            raise ValueError("지원하지 않는 추천 업종 코드입니다.")
        entry, cache_status, warnings = await self._fetch_cached(area)
        stores = self._normalise_rows(entry.result.rows, area["geometry"], industry_code)
        return {
            "area_code": area["area_code"],
            "area_name": area["area_name"],
            "industry_code": industry_code,
            "industry_name": self._industry_names[industry_code],
            "reference_month": entry.result.reference_month,
            "fetched_at": entry.fetched_at.isoformat(),
            "cache_status": cache_status,
            "source": STORE_SOURCE,
            "disclosure": STORE_DISCLOSURE,
            "warnings": warnings,
            "summary": self._summary(stores, area["area_size_sqm"]),
            "stores": stores,
        }

    async def get_store(self, area_code: str, industry_code: str, store_id: str) -> dict[str, Any]:
        analysis = await self.analyse(area_code, industry_code)
        store = next((item for item in analysis["stores"] if item["store_id"] == store_id), None)
        if store is None:
            raise ValueError("선택한 상권에서 해당 업소를 찾을 수 없습니다.")
        return {**analysis, "selected_store": store}
