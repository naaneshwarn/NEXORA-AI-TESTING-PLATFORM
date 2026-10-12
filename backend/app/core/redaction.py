from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

# Key names (normalized to lowercase alphanumerics) whose values must never be
# persisted into telemetry in plain text.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "auth_token",
        "api_key",
        "apikey",
        "api_secret",
        "secret",
        "secret_key",
        "client_secret",
        "authorization",
        "auth",
        "credit_card",
        "card_number",
        "cvv",
        "cvc",
        "ssn",
        "private_key",
        "session_id",
        "cookie",
        "set_cookie",
    }
)


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


_NORMALIZED_SENSITIVE_KEYS = frozenset(_normalize_key(key) for key in SENSITIVE_KEYS)

# Inline secret patterns for free-text / header strings.
_BEARER_RE = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9\-._~+/]+=*)")
_BASIC_RE = re.compile(r"(?i)\b(basic)\s+([A-Za-z0-9+/=]{4,})")
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|token|access[_-]?token|refresh[_-]?token|api[_-]?key|apikey|"
    r"secret|client[_-]?secret|authorization|credit[_-]?card|card[_-]?number|cvv|cvc|ssn)"
    r"\b(\s*[=:]\s*)(?!\[REDACTED\])(?!bearer\b)(?!basic\b)([^\s,;&\"']+)"
)
_OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")
_AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    return _normalize_key(key) in _NORMALIZED_SENSITIVE_KEYS


def _scrub_string(value: str) -> str:
    scrubbed = _BEARER_RE.sub(r"\1 [REDACTED]", value)
    scrubbed = _BASIC_RE.sub(r"\1 [REDACTED]", scrubbed)
    scrubbed = _ASSIGNMENT_RE.sub(r"\1\2[REDACTED]", scrubbed)
    scrubbed = _OPENAI_KEY_RE.sub(REDACTED, scrubbed)
    scrubbed = _AWS_KEY_RE.sub(REDACTED, scrubbed)
    scrubbed = _JWT_RE.sub(REDACTED, scrubbed)
    return scrubbed


def redact_sensitive_data(value: Any) -> Any:
    """Recursively redact sensitive keys and inline secrets from a value.

    Handles dictionaries, lists/tuples and strings; all other types are returned
    unchanged. Dict keys matching :data:`SENSITIVE_KEYS` have their entire value
    replaced with ``"[REDACTED]"``, while strings are scanned for common inline
    secret formats (bearer/basic tokens, ``key=value`` assignments, provider API
    keys, and JWTs).
    """
    if isinstance(value, dict):
        return {
            key: (REDACTED if _is_sensitive_key(key) else redact_sensitive_data(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, str):
        return _scrub_string(value)
    return value
