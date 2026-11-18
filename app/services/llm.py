"""Provider-agnostic LLM factory (Qwen / DeepSeek via OpenAI-compatible APIs)."""

from __future__ import annotations

import logging
import threading

from app.config import settings

logger = logging.getLogger(__name__)

PROVIDER_LABELS = {
    "qwen": "通义千问",
    "deepseek": "DeepSeek",
}


class LLMFactory:
    def __init__(self) -> None:
        self._models: dict[str, object] = {}
        self._lock = threading.RLock()

    def available(self, provider: str) -> bool:
        return bool(settings.api_key_for(provider))

    def get(self, provider: str):
        provider = (provider or settings.default_llm).lower()
        if provider not in ("qwen", "deepseek"):
            raise ValueError(f"不支持的模型提供方：{provider}")
        if not settings.api_key_for(provider):
            label = PROVIDER_LABELS.get(provider, provider)
            key_name = "QWEN_API_KEY（或 DASHSCOPE_API_KEY）" if provider == "qwen" else "DEEPSEEK_API_KEY"
            raise RuntimeError(f"尚未配置 {label} 的 API Key，请在 .env 中填写 {key_name} 后重启服务。")

        if provider in self._models:
            return self._models[provider]

        with self._lock:
            if provider in self._models:
                return self._models[provider]

            from llama_index.llms.openai_like import OpenAILike

            llm = OpenAILike(
                model=settings.model_for(provider),
                api_base=settings.base_url_for(provider),
                api_key=settings.api_key_for(provider),
                is_chat_model=True,
                is_function_calling_model=False,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                timeout=settings.llm_timeout,
                context_window=32768,
            )
            self._models[provider] = llm
            logger.info("Initialized %s LLM: %s", provider, settings.model_for(provider))
            return llm

    def info(self) -> dict:
        return {
            provider: {
                "label": PROVIDER_LABELS[provider],
                "model": settings.model_for(provider),
                "configured": self.available(provider),
            }
            for provider in ("qwen", "deepseek")
        }


llm_factory = LLMFactory()