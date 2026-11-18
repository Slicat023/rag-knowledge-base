"""Application configuration.

All runtime settings can be overridden through environment variables or a
``.env`` file placed next to this project (see ``.env.example``).
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # ---------- application ----------
    app_name: str = "知库 RAG"
    app_version: str = "1.0.0"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    data_dir: Path = BASE_DIR / "data"
    documents_dir_name: str = "documents"
    chroma_dir_name: str = "chroma"
    registry_name: str = "registry.json"

    # ---------- vector store ----------
    chroma_collection: str = "rag_knowledge_base"

    # ---------- embeddings ----------
    embedding_model: str = "models/bge-base-zh-v1.5"
    embedding_device: str = "auto"  # auto / cpu / cuda / cuda:0
    embedding_batch_size: int = 16
    embedding_max_length: int = 512
    embedding_query_instruction: str = "为这个句子生成表示以用于检索相关文章："

    # ---------- reranker ----------
    rerank_enabled: bool = True
    reranker_model: str = "models/bge-reranker-base"
    reranker_device: str = "auto"
    reranker_batch_size: int = 8
    reranker_max_length: int = 512
    reranker_top_n: int = 6

    # ---------- retrieval / chunking ----------
    retrieval_top_k: int = 12
    # BGE's max sequence length is 512 tokens. For Chinese, one character is
    # roughly one token, so keep chunks comfortably below 512 (not 700).
    chunk_size: int = 420
    chunk_overlap: int = 60
    max_context_chars: int = 6000
    # Number of recent section levels included in the embedding prefix.
    embed_context_levels: int = 3

    # ---------- LLM ----------
    default_llm: str = "qwen"
    qwen_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("QWEN_API_KEY", "DASHSCOPE_API_KEY"),
    )
    # Explicit field so a DASHSCOPE_API_KEY in .env is still visible even when
    # QWEN_API_KEY exists but is empty (AliasChoices stops at the first match).
    dashscope_api_key: str = ""
    qwen_model: str = "qwen-plus"
    qwen_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        validation_alias=AliasChoices("QWEN_BASE_URL", "DASHSCOPE_BASE_URL"),
    )
    dashscope_base_url: str = ""

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    llm_temperature: float = 0.2
    llm_max_tokens: int = 1600
    llm_timeout: float = 120.0
    max_history_turns: int = 6

    # ---------- uploads ----------
    max_upload_mb: int = 50
    warmup_models: bool = True

    # ---------- mirrors ----------
    hf_endpoint: str = "https://hf-mirror.com"

    @model_validator(mode="after")
    def _apply_environment_fallbacks(self) -> "Settings":
        # Be forgiving about the two common names used for DashScope.
        if not self.qwen_api_key:
            self.qwen_api_key = self.dashscope_api_key or os.getenv("DASHSCOPE_API_KEY", "")
        if not self.qwen_base_url:
            self.qwen_base_url = (
                self.dashscope_base_url
                or os.getenv("DASHSCOPE_BASE_URL", "")
                or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        return self

    # ---------- derived paths ----------
    @property
    def resolved_data_dir(self) -> Path:
        return self.data_dir if self.data_dir.is_absolute() else BASE_DIR / self.data_dir

    @property
    def documents_dir(self) -> Path:
        return self.resolved_data_dir / self.documents_dir_name

    @property
    def chroma_dir(self) -> Path:
        return self.resolved_data_dir / self.chroma_dir_name

    @property
    def registry_path(self) -> Path:
        return self.resolved_data_dir / self.registry_name

    @property
    def cache_dir(self) -> Path:
        return self.resolved_data_dir / "cache"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def resolve_model_path(self, value: str) -> Path | str:
        """Return a local path when it exists, otherwise the original repo id."""
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = BASE_DIR / path
        return path if path.exists() else value

    def ensure_directories(self) -> None:
        for directory in (
            self.resolved_data_dir,
            self.documents_dir,
            self.chroma_dir,
            self.cache_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    # ---------- provider helpers ----------
    def api_key_for(self, provider: str) -> str:
        return {
            "qwen": self.qwen_api_key,
            "deepseek": self.deepseek_api_key,
        }.get(provider, "")

    def model_for(self, provider: str) -> str:
        return {
            "qwen": self.qwen_model,
            "deepseek": self.deepseek_model,
        }.get(provider, "")

    def base_url_for(self, provider: str) -> str:
        return {
            "qwen": self.qwen_base_url,
            "deepseek": self.deepseek_base_url,
        }.get(provider, "")

    @property
    def available_providers(self) -> list[str]:
        return [p for p in ("qwen", "deepseek") if self.api_key_for(p)]


settings = Settings()


def _configure_local_caches() -> None:
    """Keep model / LlamaIndex caches inside the project.

    This makes the app self-contained and avoids permission problems on
    locked-down Windows accounts (the default cache lives in AppData).
    """
    settings.ensure_directories()
    defaults = {
        "HF_HOME": settings.cache_dir / "huggingface",
        "HF_HUB_CACHE": settings.cache_dir / "huggingface" / "hub",
        "LLAMA_INDEX_CACHE_DIR": settings.cache_dir / "llama_index",
        "SENTENCE_TRANSFORMERS_HOME": settings.cache_dir / "sentence_transformers",
        "MODELSCOPE_CACHE": settings.cache_dir / "modelscope",
        "TORCH_HOME": settings.cache_dir / "torch",
    }
    for key, value in defaults.items():
        value.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault(key, str(value))
    os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)

    # Keep third-party telemetry / banners out of the console.
    for key, value in {
        "UNSTRUCTURED_DISABLE_NOTICE": "1",
        "DO_NOT_TRACK": "1",
        "SCARF_NO_ANALYTICS": "1",
        "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        "TRANSFORMERS_VERBOSITY": "error",
    }.items():
        os.environ.setdefault(key, value)


_configure_local_caches()