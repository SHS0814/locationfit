"""Small, retrying clients for the official REB R-ONE refresh job.

These clients are deliberately not imported by the web application. External calls happen
only during a manual refresh; runtime reads the generated Parquet artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
import ssl
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class RebApiError(RuntimeError):
    pass


OpenJson = Callable[[Request, float], dict[str, Any]]


def _default_open_json(request: Request, timeout: float) -> dict[str, Any]:
    verify_paths = ssl.get_default_verify_paths()
    context = ssl.create_default_context()
    if verify_paths.cafile is None:
        for candidate in (Path("/etc/ssl/cert.pem"), Path("/etc/ssl/certs/ca-certificates.crt")):
            if candidate.exists():
                context = ssl.create_default_context(cafile=str(candidate))
                break
    with urlopen(  # noqa: S310 - fixed official URLs/config
        request,
        timeout=timeout,
        context=context,
    ) as response:
        return json.loads(response.read().decode("utf-8"))


class RebOpenApiClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float = 20.0,
        retries: int = 3,
        open_json: OpenJson = _default_open_json,
    ) -> None:
        if not api_key.strip():
            raise ValueError("REB_API_KEY가 필요합니다.")
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.retries = retries
        self.open_json = open_json

    def _request(self, params: dict[str, object]) -> dict[str, Any]:
        safe_params = {**params, "KEY": self.api_key, "Type": "json"}
        request = Request(f"{self.base_url}?{urlencode(safe_params)}")
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                return self.open_json(request, self.timeout)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(0.5 * (2**attempt))
        raise RebApiError(f"REB API 요청에 실패했습니다: {type(last_error).__name__}") from last_error

    @staticmethod
    def _parse_page(payload: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
        root_error = payload.get("RESULT")
        if isinstance(root_error, dict) and root_error.get("CODE") != "INFO-000":
            raise RebApiError(str(root_error.get("MESSAGE", "REB API 오류")))
        blocks = payload.get("SttsApiTblData")
        if not isinstance(blocks, list) or not blocks:
            raise RebApiError("REB API 응답 형식이 올바르지 않습니다.")
        head = blocks[0].get("head", []) if isinstance(blocks[0], dict) else []
        total = 0
        for item in head:
            if "list_total_count" in item:
                total = int(item["list_total_count"])
            result = item.get("RESULT")
            if result and result.get("CODE") != "INFO-000":
                raise RebApiError(str(result.get("MESSAGE", "REB API 오류")))
        rows = blocks[1].get("row", []) if len(blocks) > 1 else []
        if not isinstance(rows, list):
            raise RebApiError("REB API row 형식이 올바르지 않습니다.")
        return total, rows

    def fetch_table(
        self,
        table_id: str,
        *,
        cycle: str = "QY",
        period: str | None = None,
        page_size: int = 1000,
    ) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        expected_total: int | None = None
        while expected_total is None or len(rows) < expected_total:
            params: dict[str, object] = {
                "pIndex": page,
                "pSize": page_size,
                "STATBL_ID": table_id,
                "DTACYCLE_CD": cycle,
            }
            if period:
                params["WRTTIME_IDTFR_ID"] = period
            total, page_rows = self._parse_page(self._request(params))
            expected_total = total
            if not page_rows:
                break
            rows.extend(page_rows)
            page += 1
        if expected_total is None or len(rows) != expected_total:
            raise RebApiError(
                f"REB API 전체 행을 받지 못했습니다: table={table_id}, "
                f"expected={expected_total}, received={len(rows)}"
            )
        return rows


class RebGisClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 20.0,
        open_json: OpenJson = _default_open_json,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.open_json = open_json

    def fetch_seoul_centers(
        self,
        *,
        period: str,
        previous_period: str,
        building_code: str,
    ) -> list[dict[str, Any]]:
        body = urlencode({
            "data_type": "RENT",
            "date": period,
            "PREV_DATE": previous_period,
            "buld_gbn": building_code,
            "sido_cd": "01",
            "MIN_X": "126.7",
            "MIN_Y": "37.3",
            "MAX_X": "127.3",
            "MAX_Y": "37.8",
        }).encode("utf-8")
        request = Request(
            self.base_url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        payload = self.open_json(request, self.timeout)
        rows = payload.get("res", [])
        if not isinstance(rows, list):
            raise RebApiError("REB GIS 응답 형식이 올바르지 않습니다.")
        return rows

    def fetch_seoul_boundaries(self) -> dict[str, Any]:
        body = urlencode({"CQL_FILTER": "sidocode='11'"}).encode("utf-8")
        request = Request(
            self.base_url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        payload = self.open_json(request, self.timeout)
        if (
            payload.get("type") != "FeatureCollection"
            or not isinstance(payload.get("features"), list)
            or not payload["features"]
        ):
            raise RebApiError("REB 상권 경계 응답 형식이 올바르지 않습니다.")
        return payload
