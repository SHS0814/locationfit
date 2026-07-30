from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.app.core.middleware import RecommendationRateLimitMiddleware, RequestContextMiddleware

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


def test_store_lookup_get_is_rate_limited_before_reaching_route() -> None:
    calls = 0
    app = FastAPI()
    app.add_middleware(
        RecommendationRateLimitMiddleware,
        limit=30,
        agent_limit=10,
        store_limit=2,
        window_seconds=60,
    )

    @app.get("/api/v1/areas/{area_code}/stores")
    async def stores(area_code: str) -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"area_code": area_code}

    with TestClient(app, client=("store-client", 50_000)) as client:
        first = client.get("/api/v1/areas/A1/stores")
        second = client.get("/api/v1/areas/A2/stores")
        limited = client.get("/api/v1/areas/A3/stores")

    assert first.status_code == 200
    assert second.status_code == 200
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "STORE_RATE_LIMIT_EXCEEDED"
    assert 1 <= int(limited.headers["retry-after"]) <= 60
    assert calls == 2


def test_store_rate_limit_does_not_apply_to_other_get_routes() -> None:
    app = FastAPI()
    app.add_middleware(
        RecommendationRateLimitMiddleware,
        limit=30,
        agent_limit=10,
        store_limit=1,
    )

    @app.get("/api/v1/health/live")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app, client=("health-client", 50_001)) as client:
        responses = [client.get("/api/v1/health/live") for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 200]


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
