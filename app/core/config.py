"""Configuration loader for Aurora Swarm Lab."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    postgres_dsn: str
    artifact_root: Path
    obsidian_vault_path: Path | None
    snowflake_account: str | None
    snowflake_user: str | None
    snowflake_password: str | None
    snowflake_warehouse: str | None
    snowflake_database: str
    snowflake_schema: str
    ollama_base_url: str
    ollama_model_fast: str
    ollama_model_strong: str
    chatgpt_api_enabled: bool
    chatgpt_model: str | None
    chatgpt_api_key: str | None


def _getenv_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    artifact_root = Path(os.getenv("ARTIFACT_ROOT", "./data/artifacts")).resolve()
    obsidian_path = os.getenv("OBSIDIAN_VAULT_PATH")

    return Settings(
        postgres_dsn=os.getenv("POSTGRES_DSN", "sqlite:///./data/aurora_queue.db"),
        artifact_root=artifact_root,
        obsidian_vault_path=Path(obsidian_path).resolve() if obsidian_path else None,
        snowflake_account=os.getenv("SNOWFLAKE_ACCOUNT"),
        snowflake_user=os.getenv("SNOWFLAKE_USER"),
        snowflake_password=os.getenv("SNOWFLAKE_PASSWORD"),
        snowflake_warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        snowflake_database=os.getenv("SNOWFLAKE_DATABASE", "AURORA_LAB_DB"),
        snowflake_schema=os.getenv("SNOWFLAKE_SCHEMA", "AURORA_LAB_SCHEMA"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model_fast=os.getenv("OLLAMA_MODEL_FAST", "gpt-oss-20b"),
        ollama_model_strong=os.getenv("OLLAMA_MODEL_STRONG", "nemotron-3-nano-30b"),
        chatgpt_api_enabled=_getenv_bool("CHATGPT_API_ENABLED", False),
        chatgpt_model=os.getenv("CHATGPT_MODEL"),
        chatgpt_api_key=os.getenv("CHATGPT_API_KEY"),
    )
