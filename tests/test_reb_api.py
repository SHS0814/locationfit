from __future__ import annotations

from urllib.error import URLError

import pytest

from src.data.reb_api import RebApiError, RebOpenApiClient


def response(total: int, rows: list[dict]) -> dict:
    return {
        "SttsApiTblData": [
            {"head": [{"list_total_count": total}, {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"}}]},
            {"row": rows},
        ]
    }


def test_reb_client_pages_until_exact_total() -> None:
    calls: list[str] = []

    def opener(request, timeout):
        del timeout
        calls.append(request.full_url)
        page = int(request.full_url.split("pIndex=")[1].split("&")[0])
        return response(3, [{"id": 1}, {"id": 2}] if page == 1 else [{"id": 3}])

    client = RebOpenApiClient(
        api_key="secret-key", base_url="https://example.test/api", open_json=opener,
    )
    assert [row["id"] for row in client.fetch_table("TABLE", page_size=2)] == [1, 2, 3]
    assert len(calls) == 2


def test_reb_client_errors_do_not_expose_api_key() -> None:
    def opener(request, timeout):
        del request, timeout
        raise URLError("offline")

    client = RebOpenApiClient(
        api_key="do-not-leak", base_url="https://example.test/api", retries=1, open_json=opener,
    )
    with pytest.raises(RebApiError) as caught:
        client.fetch_table("TABLE")
    assert "do-not-leak" not in str(caught.value)


def test_reb_client_rejects_error_and_incomplete_response() -> None:
    error_client = RebOpenApiClient(
        api_key="key",
        base_url="https://example.test/api",
        open_json=lambda request, timeout: {"RESULT": {"CODE": "ERROR-290", "MESSAGE": "invalid"}},
    )
    with pytest.raises(RebApiError, match="invalid"):
        error_client.fetch_table("TABLE")

    incomplete_client = RebOpenApiClient(
        api_key="key",
        base_url="https://example.test/api",
        open_json=lambda request, timeout: response(2, [{"id": 1}]) if "pIndex=1" in request.full_url else response(2, []),
    )
    with pytest.raises(RebApiError, match="전체 행"):
        incomplete_client.fetch_table("TABLE")
