from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_versioned_health_endpoint() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "nexora"
    assert payload["environment"] in {"development", "production", "test"}
    assert payload["version"] == "0.1.0"


def test_root_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "nexora"
    assert payload["version"] == "0.1.0"


def test_openapi_documentation_endpoints() -> None:
    docs_response = client.get("/docs")
    assert docs_response.status_code == 200

    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200
    schema = openapi_response.json()
    assert schema["info"]["title"] == "NEXORA"
    assert "/api/v1/health" in schema["paths"]

