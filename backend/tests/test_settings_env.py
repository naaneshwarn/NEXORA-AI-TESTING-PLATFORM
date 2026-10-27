"""Tests for settings: env-var aliases and defaults (WP-A launch hardening).

The documented deployment surface uses NEXORA_-prefixed env vars
(``NEXORA_API_KEYS``, ``NEXORA_AUTH_MODE``, ``NEXORA_STATE_DIR``).  These tests
pin that mapping so a settings refactor cannot silently break deployments.
"""

from __future__ import annotations

from app.core.config import Settings


def test_defaults_are_development_friendly() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.api_keys == ""
    assert settings.auth_mode == "auto"
    assert settings.state_dir == ".state"


def test_nexora_prefixed_env_vars_are_read(monkeypatch) -> None:
    monkeypatch.setenv("NEXORA_API_KEYS", "k1,k2")
    monkeypatch.setenv("NEXORA_AUTH_MODE", "write")
    monkeypatch.setenv("NEXORA_STATE_DIR", "/var/lib/nexora")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.api_keys == "k1,k2"
    assert settings.auth_mode == "write"
    assert settings.state_dir == "/var/lib/nexora"


def test_bare_env_var_names_still_work(monkeypatch) -> None:
    monkeypatch.delenv("NEXORA_API_KEYS", raising=False)
    monkeypatch.setenv("API_KEYS", "bare-key")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.api_keys == "bare-key"


def test_prefixed_var_wins_over_bare(monkeypatch) -> None:
    monkeypatch.setenv("NEXORA_API_KEYS", "prefixed-key")
    monkeypatch.setenv("API_KEYS", "bare-key")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.api_keys == "prefixed-key"


def test_workflow_env_vars_map_from_field_names(monkeypatch) -> None:
    monkeypatch.setenv("WORKFLOW_DEFAULT_PASS_THRESHOLD", "85")
    monkeypatch.setenv("WORKFLOW_MAX_CONCURRENT_RUNS", "2")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.workflow_default_pass_threshold == 85.0
    assert settings.workflow_max_concurrent_runs == 2
