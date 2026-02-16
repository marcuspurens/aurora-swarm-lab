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
    ollama_model_embed: str
    ollama_request_timeout_seconds: int
    ollama_request_retries: int
    ollama_request_backoff_seconds: float
    embeddings_enabled: bool
    memory_enabled: bool
    memory_retrieve_limit: int
    retrieval_feedback_enabled: bool
    retrieval_feedback_history_limit: int
    retrieval_feedback_signal_limit: int
    retrieval_feedback_cited_boost: float
    retrieval_feedback_missed_penalty: float
    retrieval_feedback_min_token_overlap: float
    context_handoff_enabled: bool
    context_handoff_turn_limit: int
    context_handoff_resume_idle_minutes: int
    context_handoff_background_interval_seconds: int
    context_handoff_pre_compaction_turn_count: int
    run_log_max_json_chars: int
    run_log_max_error_chars: int
    chatgpt_api_enabled: bool
    chatgpt_model: str | None
    chatgpt_api_key: str | None
    pyannote_token: str | None
    pyannote_model: str | None
    audio_denoise_enabled: bool
    audio_denoise_backend: str
    deepfilternet_cmd: str
    deepfilternet_args: str
    transcribe_backend: str
    whisper_cli_cmd: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    whisper_language: str | None


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
        ollama_model_embed=os.getenv("OLLAMA_MODEL_EMBED", "nomic-embed-text"),
        ollama_request_timeout_seconds=int(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "60")),
        ollama_request_retries=max(0, int(os.getenv("OLLAMA_REQUEST_RETRIES", "2"))),
        ollama_request_backoff_seconds=max(0.0, float(os.getenv("OLLAMA_REQUEST_BACKOFF_SECONDS", "0.5"))),
        embeddings_enabled=_getenv_bool("EMBEDDINGS_ENABLED", True),
        memory_enabled=_getenv_bool("MEMORY_ENABLED", True),
        memory_retrieve_limit=int(os.getenv("MEMORY_RETRIEVE_LIMIT", "4")),
        retrieval_feedback_enabled=_getenv_bool("RETRIEVAL_FEEDBACK_ENABLED", True),
        retrieval_feedback_history_limit=max(10, int(os.getenv("RETRIEVAL_FEEDBACK_HISTORY_LIMIT", "80"))),
        retrieval_feedback_signal_limit=max(3, int(os.getenv("RETRIEVAL_FEEDBACK_SIGNAL_LIMIT", "8"))),
        retrieval_feedback_cited_boost=max(0.0, float(os.getenv("RETRIEVAL_FEEDBACK_CITED_BOOST", "0.08"))),
        retrieval_feedback_missed_penalty=max(0.0, float(os.getenv("RETRIEVAL_FEEDBACK_MISSED_PENALTY", "0.03"))),
        retrieval_feedback_min_token_overlap=max(0.0, float(os.getenv("RETRIEVAL_FEEDBACK_MIN_TOKEN_OVERLAP", "0.2"))),
        context_handoff_enabled=_getenv_bool("CONTEXT_HANDOFF_ENABLED", True),
        context_handoff_turn_limit=int(os.getenv("CONTEXT_HANDOFF_TURN_LIMIT", "20")),
        context_handoff_resume_idle_minutes=int(os.getenv("CONTEXT_HANDOFF_RESUME_IDLE_MINUTES", "45")),
        context_handoff_background_interval_seconds=int(
            os.getenv("CONTEXT_HANDOFF_BACKGROUND_INTERVAL_SECONDS", "300")
        ),
        context_handoff_pre_compaction_turn_count=max(
            0, int(os.getenv("CONTEXT_HANDOFF_PRE_COMPACTION_TURN_COUNT", "12"))
        ),
        run_log_max_json_chars=max(400, int(os.getenv("RUN_LOG_MAX_JSON_CHARS", "20000"))),
        run_log_max_error_chars=max(200, int(os.getenv("RUN_LOG_MAX_ERROR_CHARS", "4000"))),
        chatgpt_api_enabled=_getenv_bool("CHATGPT_API_ENABLED", False),
        chatgpt_model=os.getenv("CHATGPT_MODEL"),
        chatgpt_api_key=os.getenv("CHATGPT_API_KEY"),
        pyannote_token=os.getenv("PYANNOTE_TOKEN"),
        pyannote_model=os.getenv("PYANNOTE_MODEL"),
        audio_denoise_enabled=_getenv_bool("AUDIO_DENOISE_ENABLED", False),
        audio_denoise_backend=os.getenv("AUDIO_DENOISE_BACKEND", "deepfilternet"),
        deepfilternet_cmd=os.getenv("DEEPFILTERNET_CMD", "deepfilternet"),
        deepfilternet_args=os.getenv("DEEPFILTERNET_ARGS", ""),
        transcribe_backend=os.getenv("TRANSCRIBE_BACKEND", "auto"),
        whisper_cli_cmd=os.getenv("WHISPER_CLI_CMD", "whisper"),
        whisper_model=os.getenv("WHISPER_MODEL", "small"),
        whisper_device=os.getenv("WHISPER_DEVICE", "auto"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "default"),
        whisper_language=os.getenv("WHISPER_LANGUAGE"),
    )
