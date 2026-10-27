from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="NEXORA")
    app_env: str = Field(default="development")
    api_prefix: str = Field(default="/api/v1")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"])

    # -- Authentication (Naaneshwar / WP-A launch hardening) ---------------
    # Comma-separated list of accepted API keys (NEXORA_API_KEYS).  Empty by
    # default so local development and the test suite stay credential-free;
    # set it to turn authentication on for a deployment.  The NEXORA_-prefixed
    # env var is the documented name (see .env.example); the bare field name
    # (API_KEYS) is accepted as a fallback alias.
    api_keys: str = Field(
        default="",
        validation_alias=AliasChoices("NEXORA_API_KEYS", "API_KEYS"),
    )
    # Authentication enforcement mode (NEXORA_AUTH_MODE / AUTH_MODE):
    #   auto  - "write" when api_keys are configured, otherwise "off"
    #   off   - never enforce (sentinels still simulate 401/403)
    #   write - mutating requests (POST/PUT/PATCH/DELETE) require a valid key
    #   full  - every request under the API prefix requires a valid key
    # Reads stay open in "write" mode so the dashboard, Swagger UI and the SSE
    # trace stream keep working without embedding credentials in URLs.
    auth_mode: str = Field(
        default="auto",
        validation_alias=AliasChoices("NEXORA_AUTH_MODE", "AUTH_MODE"),
    )

    # -- Durable core-store persistence (WP-A) ----------------------------
    # Directory for the JSON snapshot of the core store (agents, runs,
    # environments, leads, traces, reports).  Relative paths resolve against
    # the backend directory.  Set to an empty string to disable persistence.
    state_dir: str = Field(
        default=".state",
        validation_alias=AliasChoices("NEXORA_STATE_DIR", "STATE_DIR"),
    )

    # -- Workflow execution (Rahul / Work Package D) -----------------------
    # Operational knobs for the workflow subsystem.  All are environment
    # overridable (prefix-free names map to WORKFLOW_* env vars via the field
    # name), so launch deployments can tune them without code changes.
    workflow_total_timeout_seconds: float = Field(default=30.0, gt=0.0)
    workflow_agent_timeout_seconds: float = Field(default=10.0, gt=0.0)
    workflow_default_pass_threshold: float = Field(default=70.0, ge=0.0, le=100.0)
    workflow_max_concurrent_runs: int = Field(default=4, ge=1)
    # Durable directory for run-context snapshots so queued runs survive a
    # process restart.  Relative paths resolve against the backend directory.
    workflow_state_dir: str = Field(default=".workflow_state")


settings = Settings()
