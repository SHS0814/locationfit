"""Retrying client for Seoul Commercial District Analysis rental prices."""

from __future__ import annotations

import time
from typing import Any, Callable

import requests


class SeoulRentApiError(RuntimeError):
    """Raised when the official Seoul service returns an unusable response."""


class SeoulRentClient:
    """Small client for the public endpoints used by golmok.seoul.go.kr."""

    def __init__(
        self,
        *,
        base_url: str = "https://golmok.seoul.go.kr",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_wait: float = 1.0,
        session: requests.Session | None = None,
        logger: Callable[[str], None] | None = print,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_wait = retry_wait
        self.session = session or requests.Session()
        self.logger = logger

    def available_periods(self) -> list[tuple[int, int]]:
        rows = self._post_json("/region/selectYearData.json", {})
        periods: list[tuple[int, int]] = []
        for row in rows:
            try:
                year, quarter = int(row["YEARS"]), int(row["QU"])
            except (KeyError, TypeError, ValueError) as exc:
                raise SeoulRentApiError("서울시 임대시세 기준기간 응답이 올바르지 않습니다.") from exc
            if quarter not in (1, 2, 3, 4):
                raise SeoulRentApiError(f"서울시 임대시세 분기 코드가 올바르지 않습니다: {quarter}")
            periods.append((year, quarter))
        if not periods:
            raise SeoulRentApiError("서울시 임대시세 기준기간 응답이 비어 있습니다.")
        return sorted(set(periods), reverse=True)

    def rental_rows(self, *, year: int, quarter: int, area_type_code: str) -> list[dict[str, Any]]:
        if quarter not in (1, 2, 3, 4):
            raise ValueError("quarter는 1~4여야 합니다.")
        if area_type_code not in {"A", "D", "R", "U"}:
            raise ValueError(f"알 수 없는 서울 상권유형 코드입니다: {area_type_code}")
        return self._post_json(
            "/business/selectRentalPriceTerm.json",
            {
                "stdrYyCd": str(year),
                "stdrQuCd": str(quarter),
                "stdrSlctQu": "sameQu",
                "svcIndutyCdL": "CS000000",
                "svcIndutyCdM": "all",
                "trdarSeCd": area_type_code,
                "stdrMnCd": "",
                "selectTerm": "quarter",
                "stdrSigngu": "11",
                "selectInduty": "1",
            },
        )

    def _post_json(self, path: str, data: dict[str, str]) -> list[dict[str, Any]]:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    url,
                    data=data,
                    timeout=self.timeout,
                    headers={
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "Referer": f"{self.base_url}/stateDistrict.do",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
                    raise SeoulRentApiError("서울시 임대시세 응답 형식이 올바르지 않습니다.")
                return payload
            except (requests.RequestException, ValueError, SeoulRentApiError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    if self.logger:
                        self.logger(f"서울시 임대시세 요청 재시도 {attempt}/{self.max_retries}")
                    time.sleep(self.retry_wait * attempt)
        raise SeoulRentApiError(
            f"서울시 임대시세 요청에 실패했습니다: {type(last_error).__name__}"
        ) from last_error
