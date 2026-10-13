"""Contract tests for the optional authentication dependency.

The dependency is exercised through a minimal FastAPI app so the behaviour is
verified end-to-end (dependency resolution, header parsing and the synthetic
401/403 sentinels) without coupling these assertions to a specific business
route.
"""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.auth import FORBIDDEN_TOKEN, INVALID_TOKEN, verify_optional_auth
from app.main import app as main_app

auth_app = FastAPI()


@auth_app.get("/whoami")
async def whoami(auth: dict = Depends(verify_optional_auth)) -> dict:
    return auth


client = TestClient(auth_app)
main_client = TestClient(main_app)


def test_optional_auth_allows_anonymous_requests() -> None:
    response = client.get("/whoami")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "token_prefix": None}


def test_optional_auth_accepts_api_key_header() -> None:
    response = client.get("/whoami", headers={"X-API-Key": "abcdef123456"})

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "token_prefix": "abcd..."}


def test_optional_auth_accepts_bearer_token() -> None:
    response = client.get("/whoami", headers={"Authorization": "Bearer tok12345"})

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "token_prefix": "tok1..."}


def test_optional_auth_prefers_bearer_token_over_api_key() -> None:
    response = client.get(
        "/whoami",
        headers={"X-API-Key": "valid-api-key", "Authorization": f"Bearer {INVALID_TOKEN}"},
    )

    # The Bearer credential wins, so the denied-access sentinel still triggers.
    assert response.status_code == 401


def test_optional_auth_simulates_unauthorized_access() -> None:
    response = client.get("/whoami", headers={"X-API-Key": INVALID_TOKEN})

    assert response.status_code == 401
    assert "Invalid authentication credentials" in response.text


def test_optional_auth_simulates_forbidden_access() -> None:
    response = client.get("/whoami", headers={"Authorization": f"Bearer {FORBIDDEN_TOKEN}"})

    assert response.status_code == 403
    assert "Access denied" in response.text


def test_crm_route_allows_anonymous_requests() -> None:
    # Attaching the dependency must not force credentials on synthetic traffic.
    assert main_client.get("/api/v1/leads").status_code == 200


def test_crm_route_simulates_unauthorized_access() -> None:
    response = main_client.get("/api/v1/leads", headers={"X-API-Key": INVALID_TOKEN})

    assert response.status_code == 401
    assert "Invalid authentication credentials" in response.text


def test_execution_route_simulates_forbidden_access() -> None:
    response = main_client.post(
        "/api/v1/synthetic/agent/execute/rest",
        headers={"Authorization": f"Bearer {FORBIDDEN_TOKEN}"},
        json={"tool_name": "list_crm_leads", "parameters": {}},
    )

    assert response.status_code == 403
    assert "Access denied" in response.text
