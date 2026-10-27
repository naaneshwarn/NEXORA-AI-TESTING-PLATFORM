from __future__ import annotations

import secrets
from typing import Iterable, Mapping

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

# Synthetic sentinels let callers exercise denied-access handling without a real
# identity provider: ``invalid-token-test`` yields 401, ``forbidden-token-test``
# yields 403.
INVALID_TOKEN = "invalid-token-test"
FORBIDDEN_TOKEN = "forbidden-token-test"

# Request methods that mutate state.  In ``write`` mode only these require a
# credential; reads (GET/HEAD/OPTIONS) stay open so the dashboard, Swagger UI
# and the SSE trace stream work without embedding tokens in URLs.
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Paths that never require a credential even in ``full`` mode: liveness and
# schema endpoints are needed by container health checks and API explorers.
OPEN_PATHS = frozenset(
    {
        "/health",
        "/api/v1/health",
        "/v1/health",
        "/v1/models",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)

VALID_AUTH_MODES = frozenset({"auto", "off", "write", "full"})


def configured_api_keys() -> frozenset[str]:
    """Return the set of accepted API keys from ``NEXORA_API_KEYS``.

    The value is a comma-separated list; blank entries are ignored so trailing
    commas and whitespace cannot accidentally create an empty-string key.
    """
    return frozenset(part.strip() for part in settings.api_keys.split(",") if part.strip())


def resolve_auth_mode() -> str:
    """Resolve the effective authentication mode for this process.

    ``auto`` (the default) enables write-protection as soon as at least one
    API key is configured.  An explicit ``write``/``full`` mode without any
    configured keys cannot validate anything, so it degrades to ``off`` with a
    clear, greppable warning rather than locking every caller out with an
    unexplainable 401 (the warning is emitted once at startup).
    """
    mode = (settings.auth_mode or "auto").strip().lower()
    if mode not in VALID_AUTH_MODES:
        mode = "auto"
    if mode == "auto":
        return "write" if configured_api_keys() else "off"
    if mode in {"write", "full"} and not configured_api_keys():
        return "off"
    return mode


def requires_auth(method: str, path: str) -> bool:
    """Whether a request must present a valid credential to be served."""
    mode = resolve_auth_mode()
    if mode == "off":
        return False
    if path in OPEN_PATHS:
        return False
    if mode == "write" and method.upper() not in _MUTATING_METHODS:
        return False
    return True


def _token_is_valid(token: str, valid_keys: Iterable[str]) -> bool:
    """Timing-safe comparison of the presented token against every valid key.

    ``secrets.compare_digest`` is used for each candidate and the result is
    accumulated so the loop always runs to completion — response timing does
    not reveal which configured key (if any) matched.
    """
    token_bytes = token.encode("utf-8")
    matched = False
    for candidate in valid_keys:
        if secrets.compare_digest(token_bytes, candidate.encode("utf-8")):
            matched = True
    return matched


def authenticate_token(token: str | None, *, enforce: bool = True) -> dict:
    """Validate a credential and return the auth context for the request.

    Args:
        token: Bearer token or API key presented by the caller, if any.
        enforce: When ``True`` a valid credential is mandatory (configured
            keys + active mode); when ``False`` a missing credential is only
            reported as ``authenticated=False``.  The synthetic sentinels are
            honoured in both cases.

    Raises:
        HTTPException: 401 for missing/invalid credentials (and the synthetic
            ``invalid-token-test`` sentinel), 403 for the
            ``forbidden-token-test`` sentinel.
    """
    # Synthetic sentinels are honoured in every mode so denied-access handling
    # stays testable without a real identity provider.
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

    valid_keys = configured_api_keys()
    auth_active = bool(valid_keys) and resolve_auth_mode() != "off"

    if not enforce or not auth_active:
        return {
            "authenticated": bool(token),
            "token_prefix": token[:4] + "..." if token else None,
        }

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Missing API key. Provide it via 'X-API-Key' or 'Authorization: Bearer'."
            },
        )

    if not _token_is_valid(token, valid_keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid authentication credentials provided."},
        )

    return {
        "authenticated": True,
        "token_prefix": token[:4] + "..." if token else None,
    }


def extract_token_from_headers(headers: Mapping[str, str | bytes]) -> str | None:
    """Pull the bearer token or API key out of a raw header mapping.

    Accepts both plain ``dict[str, str]`` (Starlette ``Headers``) and the
    ``bytes``-keyed mappings produced by raw ASGI scopes.
    """
    authorization = ""
    api_key = None
    for name, value in headers.items():
        key = name.lower() if isinstance(name, str) else name.decode("latin-1").lower()
        text = value.decode("latin-1") if isinstance(value, (bytes, bytearray)) else str(value)
        if key == "authorization":
            authorization = text
        elif key == "x-api-key":
            api_key = text

    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    if api_key:
        stripped = api_key.strip()
        if stripped:
            return stripped
    return None


def extract_token(request: Request) -> str | None:
    """Pull the bearer token or API key out of an incoming request."""
    return extract_token_from_headers(request.headers)


async def verify_optional_auth(
    request: Request,
    api_key: str | None = Security(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """Validate optional API keys or Bearer tokens.

    Authentication is optional by default: with no API keys configured a
    missing credential is not rejected, it simply reports
    ``authenticated=False``. The ``X-API-Key`` header and
    ``Authorization: Bearer <token>`` scheme are both accepted, with the Bearer
    token taking precedence when both are supplied.

    When ``NEXORA_API_KEYS`` is configured, enforcement follows the active
    auth mode for the *current* request (see :func:`requires_auth`): mutating
    requests always require a valid key, reads only in ``full`` mode.  The
    sentinels are rejected before any of that logic runs.

    ``request`` is injected by FastAPI so the dependency can apply the same
    method/path rules as the auth middleware — a route protected by this
    dependency behaves identically whether or not the middleware is mounted.
    """
    token = bearer.credentials if bearer else api_key
    return authenticate_token(token, enforce=requires_auth(request.method, request.url.path))
