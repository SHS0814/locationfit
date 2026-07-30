"""Resilient and secret-safe client for the Seoul Open Data JSON API."""

from __future__ import annotations

import hashlib
import json
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from src.utils.paths import PROJECT_ROOT


class SeoulAPIError(RuntimeError):
    """API error carrying whether repeating the same request can be useful."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class FetchResult:
    """Rows and API count returned by a page or complete paginated fetch."""

    rows: list[dict[str, Any]]
    total_count: int
    page_count: int


@dataclass(frozen=True)
class ResponseDiagnostics:
    """Non-secret HTTP response facts useful for diagnosing non-JSON responses."""

    status: int
    content_type: str
    body_length: int
    body_preview: str
    redirected: bool
    url: str


class SeoulAPIClient:
    """Fetch Seoul Open Data services without exposing authentication keys."""

    SUCCESS_CODES = {"INFO-000"}
    EMPTY_CODES = {"INFO-200"}
    RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
    RETRYABLE_API_CODES = {"ERROR-500", "ERROR-600"}
    PLACEHOLDER_KEYS = {
        "your_seoul_open_data_api_key",
        "your_api_key",
        "changeme",
        "replace_me",
    }

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "http://openapi.seoul.go.kr:8088",
        page_size: int = 1000,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_wait: float = 1.0,
        session: requests.Session | None = None,
        env_path: Path | None = None,
        debug: bool = False,
        logger: Callable[[str], None] | None = print,
    ) -> None:
        self.env_path = (env_path or PROJECT_ROOT / ".env").resolve()
        load_dotenv(self.env_path, override=False)
        raw_api_key = api_key if api_key is not None else os.getenv("SEOUL_API_KEY")
        self.api_key = (raw_api_key or "").strip()
        if not self.api_key:
            raise SeoulAPIError(
                f"프로젝트 루트의 .env에서 SEOUL_API_KEY를 찾지 못했습니다: {self.env_path}"
            )
        if self.api_key.lower() in self.PLACEHOLDER_KEYS or self.api_key.lower().startswith("your_"):
            raise SeoulAPIError(
                f"SEOUL_API_KEY가 예제 placeholder입니다. 실제 발급 키를 {self.env_path}에 입력하세요."
            )
        if page_size < 1 or page_size > 1000:
            raise ValueError("page_size는 1~1000이어야 합니다.")
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_wait = retry_wait
        self.session = session or requests.Session()
        self.debug = debug
        self.logger = logger
        if self.debug:
            self._emit("SEOUL_API_KEY loaded: yes")
            self._emit(f"length: {len(self.api_key)}")

    def build_url(
        self,
        service_name: str,
        start_index: int,
        end_index: int,
        path_filters: Sequence[str | int] = (),
    ) -> str:
        """Build one request URL; callers must never log it without masking."""
        if not service_name:
            raise ValueError("api_service_name이 비어 있습니다.")
        parts = [
            self.base_url,
            quote(self.api_key, safe=""),
            "json",
            quote(service_name, safe=""),
            str(start_index),
            str(end_index),
        ]
        parts.extend(quote(str(value), safe="") for value in path_filters)
        return "/".join(parts)

    def mask_url(self, url: str) -> str:
        """Mask this client's API key in a URL or exception string."""
        masked = str(url).replace(self.api_key, "***MASKED***")
        encoded_key = quote(self.api_key, safe="")
        return masked.replace(encoded_key, "***MASKED***")

    def fetch_page(
        self,
        service_name: str,
        *,
        start_index: int = 1,
        end_index: int = 5,
        path_filters: Sequence[str | int] = (),
        label: str | None = None,
    ) -> FetchResult:
        """Fetch and parse one page, primarily for safe API diagnostics."""
        display = label or service_name
        url = self.build_url(service_name, start_index, end_index, path_filters)
        payload = self._request_json(url, display)
        rows, total = self._parse_payload(payload, service_name, display)
        if self.debug:
            self._emit(f"[{display}] json_top_level_keys={list(payload)}")
            self._emit(f"[{display}] total_count={total:,}")
            self._emit(f"[{display}] first_page_rows={len(rows):,}")
        return FetchResult(rows=rows, total_count=total, page_count=1)

    def fetch_all(
        self,
        service_name: str,
        *,
        path_filters: Sequence[str | int] = (),
        label: str | None = None,
        progress: Callable[[str], None] | None = print,
    ) -> FetchResult:
        """Fetch all pages, validating counts, errors and duplicate pages."""
        rows: list[dict[str, Any]] = []
        total_count: int | None = None
        page_number = 0
        fingerprints: set[str] = set()
        start = 1
        display = label or service_name

        while total_count is None or start <= total_count:
            end = start + self.page_size - 1
            payload = self._request_json(
                self.build_url(service_name, start, end, path_filters),
                display,
            )
            page_rows, page_total = self._parse_payload(payload, service_name, display)
            if total_count is None:
                total_count = page_total
                if progress:
                    progress(f"[{display}] API total={total_count:,}")
            elif page_total != total_count:
                raise SeoulAPIError(
                    f"[{display}] 페이지 간 list_total_count 불일치: {total_count} != {page_total}"
                )

            if not page_rows:
                if total_count == 0 or start > total_count:
                    break
                raise SeoulAPIError(f"[{display}] {start}-{end} 구간이 빈 응답입니다.")

            fingerprint = self._fingerprint(page_rows)
            if fingerprint in fingerprints:
                raise SeoulAPIError(f"[{display}] 중복 페이지 감지: {start}-{end}")
            fingerprints.add(fingerprint)
            rows.extend(page_rows)
            page_number += 1
            if progress and (
                page_number == 1
                or page_number % 10 == 0
                or len(rows) >= total_count
            ):
                progress(f"[{display}] {min(len(rows), total_count):,}/{total_count:,}")
            start += self.page_size

        expected = total_count or 0
        if len(rows) != expected:
            raise SeoulAPIError(f"[{display}] 수집 행 수 불일치: rows={len(rows)}, total={expected}")
        return FetchResult(rows=rows, total_count=expected, page_count=page_number)

    def _request_json(self, url: str, label: str) -> dict[str, Any]:
        last_error: SeoulAPIError | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                return self._decode_response(response, url, label)
            except (requests.Timeout, requests.ConnectionError) as exc:
                detail = self._sanitize(str(exc))
                last_error = SeoulAPIError(
                    f"[{label}] 네트워크 오류: {detail}\nurl={self.mask_url(url)}",
                    retryable=True,
                )
            except requests.RequestException as exc:
                detail = self._sanitize(str(exc))
                raise SeoulAPIError(
                    f"[{label}] HTTP 요청 오류: {detail}\nurl={self.mask_url(url)}"
                ) from exc
            except SeoulAPIError as exc:
                last_error = exc

            assert last_error is not None
            if not last_error.retryable or attempt >= self.max_retries:
                raise last_error
            self._emit(
                f"[{label}] 재시도 {attempt}/{self.max_retries - 1} "
                f"url={self.mask_url(url)} reason={str(last_error).splitlines()[0]}"
            )
            time.sleep(self.retry_wait * (2 ** (attempt - 1)))
        raise AssertionError("unreachable")

    def _decode_response(
        self, response: requests.Response, request_url: str, label: str
    ) -> dict[str, Any]:
        diagnostics = self._diagnostics(response, request_url)
        if self.debug:
            self._emit_diagnostics(label, diagnostics)

        if diagnostics.status in self.RETRYABLE_HTTP_CODES:
            raise SeoulAPIError(
                f"[{label}] 일시적 HTTP 오류입니다.\n{self._format_diagnostics(diagnostics)}",
                retryable=True,
            )
        if diagnostics.status >= 400:
            raise SeoulAPIError(
                f"[{label}] HTTP 오류 응답을 받았습니다.\n{self._format_diagnostics(diagnostics)}"
            )
        if diagnostics.body_length == 0:
            raise SeoulAPIError(
                f"[{label}] API가 빈 응답을 반환했습니다.\n{self._format_diagnostics(diagnostics)}",
                retryable=True,
            )

        body = response.text
        stripped = body.lstrip()
        content_type = diagnostics.content_type.lower()
        if "text/html" in content_type or stripped.lower().startswith(("<!doctype html", "<html")):
            raise SeoulAPIError(
                f"[{label}] HTML 오류 응답을 받았습니다. "
                f"네트워크·프록시·URL을 확인하세요.\n{self._format_diagnostics(diagnostics)}"
            )
        if "xml" in content_type or stripped.startswith("<"):
            self._raise_xml_error(body, label, diagnostics)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise SeoulAPIError(
                f"[{label}] JSON이 아닌 응답입니다.\n{self._format_diagnostics(diagnostics)}"
            ) from exc
        if not isinstance(payload, dict):
            raise SeoulAPIError(
                f"[{label}] JSON 최상위가 object가 아닙니다.\n{self._format_diagnostics(diagnostics)}"
            )
        return payload

    def _raise_xml_error(
        self, body: str, label: str, diagnostics: ResponseDiagnostics
    ) -> None:
        try:
            root = ET.fromstring(body)
            code = (root.findtext(".//CODE") or "").strip()
            message = (root.findtext(".//MESSAGE") or "").strip()
        except ET.ParseError as exc:
            raise SeoulAPIError(
                f"[{label}] JSON이 아닌 XML 응답이며 XML 파싱도 실패했습니다.\n"
                f"{self._format_diagnostics(diagnostics)}"
            ) from exc
        detail = f"CODE={code or 'UNKNOWN'} MESSAGE={self._sanitize(message)}"
        raise SeoulAPIError(
            f"[{label}] XML 오류 응답을 받았습니다. {detail}\n"
            f"{self._format_diagnostics(diagnostics)}",
            retryable=code in self.RETRYABLE_API_CODES,
        )

    def _parse_payload(
        self, payload: dict[str, Any], service_name: str, label: str
    ) -> tuple[list[dict[str, Any]], int]:
        top_result = payload.get("RESULT")
        if isinstance(top_result, dict):
            code = str(top_result.get("CODE", ""))
            message = self._sanitize(str(top_result.get("MESSAGE", "")))
            if code in self.EMPTY_CODES:
                return [], 0
            raise SeoulAPIError(
                f"[{label}] Seoul API {code or 'UNKNOWN'}: {message}",
                retryable=code in self.RETRYABLE_API_CODES,
            )

        body = payload.get(service_name)
        if not isinstance(body, dict):
            candidates = [
                value for value in payload.values() if isinstance(value, dict) and "RESULT" in value
            ]
            if len(candidates) != 1:
                raise SeoulAPIError(
                    f"[{label}] 응답에 서비스 루트 '{service_name}'가 없습니다. "
                    f"top_level_keys={list(payload)}"
                )
            body = candidates[0]

        result = body.get("RESULT", {})
        code = str(result.get("CODE", "")) if isinstance(result, dict) else ""
        if code not in self.SUCCESS_CODES:
            message = result.get("MESSAGE", "") if isinstance(result, dict) else result
            if code in self.EMPTY_CODES:
                return [], 0
            raise SeoulAPIError(
                f"[{label}] Seoul API {code or 'UNKNOWN'}: {self._sanitize(str(message))}",
                retryable=code in self.RETRYABLE_API_CODES,
            )
        try:
            total = int(body.get("list_total_count", 0))
        except (TypeError, ValueError) as exc:
            raise SeoulAPIError(f"[{label}] list_total_count가 올바르지 않습니다.") from exc
        raw_rows = body.get("row", [])
        if raw_rows is None:
            raw_rows = []
        if not isinstance(raw_rows, list) or any(not isinstance(row, dict) for row in raw_rows):
            raise SeoulAPIError(f"[{label}] row가 올바른 object 배열이 아닙니다.")
        if any("RESULT" in row or "CODE" in row and "MESSAGE" in row for row in raw_rows):
            raise SeoulAPIError(f"[{label}] API 오류 object가 데이터 행에 포함됐습니다.")
        return raw_rows, total

    def _diagnostics(
        self, response: requests.Response, request_url: str
    ) -> ResponseDiagnostics:
        body = response.content or b""
        text = response.text if body else ""
        final_url = getattr(response, "url", None) or request_url
        return ResponseDiagnostics(
            status=int(getattr(response, "status_code", 0)),
            content_type=str(getattr(response, "headers", {}).get("Content-Type", "")),
            body_length=len(body),
            body_preview=self._sanitize(text[:500]),
            redirected=bool(getattr(response, "history", [])),
            url=self.mask_url(str(final_url)),
        )

    def _format_diagnostics(self, diagnostics: ResponseDiagnostics) -> str:
        return (
            f"status={diagnostics.status}\n"
            f"content_type={diagnostics.content_type or '(missing)'}\n"
            f"body_length={diagnostics.body_length}\n"
            f"body_preview={diagnostics.body_preview}\n"
            f"redirected={'yes' if diagnostics.redirected else 'no'}\n"
            f"url={diagnostics.url}"
        )

    def _emit_diagnostics(self, label: str, diagnostics: ResponseDiagnostics) -> None:
        self._emit(f"[{label}] masked_url={diagnostics.url}")
        self._emit(f"[{label}] status={diagnostics.status}")
        self._emit(f"[{label}] content_type={diagnostics.content_type or '(missing)'}")
        self._emit(f"[{label}] body_length={diagnostics.body_length}")
        self._emit(f"[{label}] body_preview={diagnostics.body_preview}")
        self._emit(f"[{label}] redirected={'yes' if diagnostics.redirected else 'no'}")

    def _sanitize(self, text: str) -> str:
        return self.mask_url(text)

    def _emit(self, message: str) -> None:
        if self.logger is not None:
            self.logger(message)

    @staticmethod
    def _fingerprint(rows: list[dict[str, Any]]) -> str:
        sample = {"count": len(rows), "first": rows[0], "last": rows[-1]}
        encoded = json.dumps(sample, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
