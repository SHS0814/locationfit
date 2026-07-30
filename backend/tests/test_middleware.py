from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.app.core.middleware import RequestContextMiddleware


MAX_REQUEST_BYTES = 16


def test_request_size_limit_accepts_body_at_exact_limit() -> None:
    with TestClient(_test_app()) as client:
        response = client.post("/body-size", content=b"x" * MAX_REQUEST_BYTES)

    assert response.status_code == 200
    assert response.json() == {"size": MAX_REQUEST_BYTES}
    assert response.headers["x-request-id"]
    assert response.headers["x-process-time-ms"]


def test_request_size_limit_rejects_declared_oversized_body() -> None:
    with TestClient(_test_app()) as client:
        response = client.post("/body-size", content=b"x" * (MAX_REQUEST_BYTES + 1))

    _assert_too_large(response)


def test_request_size_limit_replays_chunked_body_within_limit() -> None:
    chunks = iter((b"x" * 8, b"y" * 8))
    with TestClient(_test_app()) as client:
        request = client.build_request("POST", "/body-size", content=chunks)
        assert "content-length" not in request.headers
        response = client.send(request)

    assert response.status_code == 200
    assert response.json() == {"size": MAX_REQUEST_BYTES}


def test_request_size_limit_rejects_chunked_oversized_body() -> None:
    chunks = iter((b"x" * 10, b"y" * 10))
    with TestClient(_test_app()) as client:
        request = client.build_request("POST", "/body-size", content=chunks)
        assert "content-length" not in request.headers
        response = client.send(request)

    _assert_too_large(response)


def test_request_size_limit_rejects_body_larger_than_declared() -> None:
    chunks = iter((b"x" * 10, b"y" * 10))
    with TestClient(_test_app()) as client:
        response = client.post(
            "/body-size",
            content=chunks,
            headers={"content-length": "1"},
        )

    _assert_too_large(response)


def _test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware, max_request_bytes=MAX_REQUEST_BYTES)

    @app.post("/body-size")
    async def body_size(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    return app


def _assert_too_large(response) -> None:
    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "REQUEST_TOO_LARGE",
        "message": "요청 본문이 너무 큽니다.",
        "request_id": response.headers["x-request-id"],
    }
    assert response.headers["x-process-time-ms"]
