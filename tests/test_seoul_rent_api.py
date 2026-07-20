from __future__ import annotations

import requests
import pytest

from src.data.seoul_rent_api import SeoulRentApiError, SeoulRentClient


class Response:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise requests.HTTPError(str(self.status))

    def json(self) -> object:
        return self.payload


class Session:
    def __init__(self, responses: list[Response | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def post(self, url: str, *, data: dict[str, str], timeout: float, headers: dict[str, str]):
        del timeout, headers
        self.calls.append((url, data))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_client_reads_periods_and_rental_rows() -> None:
    session = Session([
        Response([{"YEARS": "2026", "QU": "1"}, {"YEARS": "2025", "QU": "4"}]),
        Response([{"NM": "테스트 (테스트동)", "GUBUN": "dong"}]),
    ])
    client = SeoulRentClient(session=session, retry_wait=0, logger=None)
    assert client.available_periods() == [(2026, 1), (2025, 4)]
    rows = client.rental_rows(year=2026, quarter=1, area_type_code="A")
    assert rows[0]["NM"] == "테스트 (테스트동)"
    assert session.calls[-1][1]["trdarSeCd"] == "A"


def test_client_retries_and_rejects_invalid_payload() -> None:
    session = Session([requests.ConnectionError("offline"), Response([{"YEARS": "2026", "QU": "1"}])])
    client = SeoulRentClient(session=session, max_retries=2, retry_wait=0, logger=None)
    assert client.available_periods() == [(2026, 1)]

    invalid = SeoulRentClient(session=Session([Response({"not": "a list"})]), max_retries=1, logger=None)
    with pytest.raises(SeoulRentApiError, match="요청에 실패"):
        invalid.available_periods()
