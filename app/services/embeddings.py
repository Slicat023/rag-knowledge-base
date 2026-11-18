"""Local BAAI/bge-base-zh-v1.5 embedding model."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Lazily loaded, process-wide embedding model.

    Loading is deliberately lazy so the web server can boot (and show the UI)
    while the model is still warming up in the background.
    """

    def __init__(self) -> None:
        self._model = None
        self._lock = threading.RLock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def model_name(self) -> str:
        return settings.embedding_model

    @property
    def device(self) -> str:
        if settings.embedding_device != "auto":
            return settings.embedding_device
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def _resolve(self) -> str:
        resolved = settings.resolve_model_path(settings.embedding_model)
        if isinstance(resolved, Path) and resolved.exists():
            return str(resolved)
        raise RuntimeError(
            "未找到本地向量模型 BAAI/bge-base-zh-v1.5。\n"
            f"请先运行：python scripts/download_models.py\n"
            f"当前配置路径：{settings.embedding_model}"
        )

    def get(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            model_path = self._resolve()
            logger.info("Loading embedding model from %s on %s", model_path, self.device)
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding

            self._model = HuggingFaceEmbedding(
                model_name=model_path,
                device=self.device,
                embed_batch_size=settings.embedding_batch_size,
                max_length=settings.embedding_max_length,
                query_instruction=settings.embedding_query_instruction,
                normalize=True,
                show_progress_bar=False,
                cache_folder=str(settings.cache_dir / "huggingface"),
            )
            logger.info("Embedding model ready")
            return self._model

    def warmup(self) -> None:
        try:
            self.get()
        except Exception:
            logger.exception("Embedding model warmup failed")

    def info(self) -> dict:
        return {
            "model": self.model_name,
            "loaded": self.loaded,
            "device": self.device,
        }


embedding_service = EmbeddingService()