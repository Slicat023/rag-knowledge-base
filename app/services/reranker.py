"""BAAI/bge-reranker-base cross-encoder reranking."""

from __future__ import annotations

import logging
import threading

from llama_index.core.schema import NodeWithScore

from app.config import settings

logger = logging.getLogger(__name__)


class BgeReranker:
    def __init__(self) -> None:
        self._model = None
        self._lock = threading.RLock()
        self.last_error: str | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def model_name(self) -> str:
        return settings.reranker_model

    @property
    def device(self) -> str:
        if settings.reranker_device != "auto":
            return settings.reranker_device
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def _resolve(self) -> str:
        resolved = settings.resolve_model_path(settings.reranker_model)
        from pathlib import Path

        if isinstance(resolved, Path) and resolved.exists():
            return str(resolved)
        raise RuntimeError(
            "未找到本地重排序模型 BAAI/bge-reranker-base。\n"
            "请先运行：python scripts/download_models.py\n"
            f"当前配置路径：{settings.reranker_model}"
        )

    def get(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            model_path = self._resolve()
            logger.info("Loading reranker from %s on %s", model_path, self.device)
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                model_path,
                device=self.device,
                max_length=settings.reranker_max_length,
            )
            self.last_error = None
            logger.info("Reranker ready")
            return self._model

    def warmup(self) -> None:
        if not settings.rerank_enabled:
            return
        try:
            self.get()
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("Reranker warmup failed")

    def rerank(
        self,
        query: str,
        nodes: list[NodeWithScore],
        top_n: int | None = None,
    ) -> list[NodeWithScore]:
        if not nodes:
            return []
        top_n = max(1, int(top_n or settings.reranker_top_n))
        if not settings.rerank_enabled:
            return nodes[:top_n]

        model = self.get()
        pairs = [(query, n.node.get_content() or "") for n in nodes]
        scores = model.predict(
            pairs,
            batch_size=settings.reranker_batch_size,
            show_progress_bar=False,
        )

        ranked: list[NodeWithScore] = []
        for node, score in zip(nodes, scores):
            ranked.append(
                NodeWithScore(node=node.node, score=float(score))
            )
        ranked.sort(key=lambda item: item.score if item.score is not None else -1e9, reverse=True)
        return ranked[:top_n]

    def info(self) -> dict:
        return {
            "model": self.model_name,
            "enabled": settings.rerank_enabled,
            "loaded": self.loaded,
            "device": self.device,
            "error": self.last_error,
        }


reranker = BgeReranker()