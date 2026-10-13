from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

# Synthetic sentinels let callers exercise denied-access handling without a real
# identity provider: ``invalid-token-test`` yields 401, ``forbidden-token-test``
# yields 403.
INVALID_TOKEN = "invalid-token-test"
FORBIDDEN_TOKEN = "forbidden-token-test"


async def verify_optional_auth(
    api_key: str | None = Security(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """Validate optional API keys or Bearer tokens.

    Authentication is optional: a missing credential is not rejected, it simply
    reports ``authenticated=False``. The ``X-API-Key`` header and
    ``Authorization: Bearer <token>`` scheme are both accepted, with the Bearer
    token taking precedence when both are supplied.

    Supports simulated auth denial for testing denied requests via the
    :data:`INVALID_TOKEN` (401) and :data:`FORBIDDEN_TOKEN` (403) sentinels.
    """
    token = bearer.credentials if bearer else api_key

    # Example: Allow simulation of unauthorized access for testing denied requests
    if token == INVALID_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid authentication credentials provided."},
        )

    if token == FORBIDDEN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": "Access denied for this synthetic resource."},
        )

    return {
        "authenticated": bool(token),
        "token_prefix": token[:4] + "..." if token else None,
    }
