from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_metadata_and_recommendation_contract() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        assert client.get("/api/v1/health/ready").status_code == 200
        metadata = client.get("/api/v1/metadata")
        assert metadata.status_code == 200
        assert metadata.json()["artifact_version"] == "2025q4-v3"
        assert metadata.json()["rent_floors"] == [
            {"code": "all", "name": "전체 층 평균"},
            {"code": "f1", "name": "1층"},
            {"code": "non_f1", "name": "1층 외"},
        ]

        response = client.post(
            "/api/v1/recommendations",
            json={
                "industry_code": "CS100010",
                "target_age_groups": ["20"],
                "weekend_importance": 0.8,
                "top_n": 3,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["recommendations"]) == 3
        assert body["request_id"] == response.headers["x-request-id"]


def test_request_accepts_industry_only_as_unrestricted_scope() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/recommendations", json={"industry_code": "CS100001"})
        assert response.status_code == 200
        body = response.json()
        assert len(body["recommendations"]) == 10
        assert body["diagnostics"]["condition_feature_count"] == 0


def test_schema_validation_has_a_stable_error_shape() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/recommendations",
            json={"industry_code": "CS100001", "top_n": 100},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "REQUEST_SCHEMA_VALIDATION_FAILED"
        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_market_geographies_returns_requested_area_and_district_boundaries() -> None:
    with TestClient(app) as client:
        area_keys = ["3001491", "3001492"]

        areas = client.post(
            "/api/v1/market-geographies",
            json={"group_by": "area", "entity_keys": area_keys},
        )
        assert areas.status_code == 200
        assert [feature["entity_key"] for feature in areas.json()["features"]] == area_keys
        assert all(feature["boundary"]["coordinates"] for feature in areas.json()["features"])

        districts = client.post(
            "/api/v1/market-geographies",
            json={"group_by": "district", "entity_keys": ["강남구", "마포구"]},
        )
        assert districts.status_code == 200
        assert [feature["entity_key"] for feature in districts.json()["features"]] == ["강남구", "마포구"]


def test_market_geographies_rejects_duplicates_and_unknown_keys() -> None:
    with TestClient(app) as client:
        duplicate = client.post(
            "/api/v1/market-geographies",
            json={"group_by": "district", "entity_keys": ["강남구", "강남구"]},
        )
        assert duplicate.status_code == 422

        unknown = client.post(
            "/api/v1/market-geographies",
            json={"group_by": "district", "entity_keys": ["없는구"]},
        )
        assert unknown.status_code == 422
