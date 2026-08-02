import asyncio
import json
import logging

from starlette.requests import Request

from backend.app.core.errors import PUBLIC_RUNTIME_ERROR_MESSAGE, runtime_error_handler


def test_runtime_error_response_hides_internal_details(caplog) -> None:
    private_detail = "database failed at /app/private/catalog.db"
    scope = {
        "type": "http",
        "method": "GET",
        "scheme": "https",
        "path": "/api/v1/recommendations",
        "raw_path": b"/api/v1/recommendations",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }
    request = Request(scope)
    request.state.request_id = "request-test-1"

    with caplog.at_level(logging.ERROR, logger="kb_recommender.errors"):
        response = asyncio.run(runtime_error_handler(request, RuntimeError(private_detail)))

    body = json.loads(response.body)
    assert response.status_code == 503
    assert body["error"] == {
        "code": "RECOMMENDER_UNAVAILABLE",
        "message": PUBLIC_RUNTIME_ERROR_MESSAGE,
        "request_id": "request-test-1",
    }
    assert private_detail not in response.body.decode("utf-8")
    assert any(
        record.exc_info is not None and str(record.exc_info[1]) == private_detail
        for record in caplog.records
    )
