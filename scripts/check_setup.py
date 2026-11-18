"""Environment self-check.

    python scripts/check_setup.py
    python scripts/check_setup.py --load-models
"""

from __future__ import annotations

import argparse
import importlib.metadata
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "未安装"


def check_import(module: str, label: str) -> bool:
    try:
        __import__(module)
        print(f"  [OK]   {label}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] {label}: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--load-models", action="store_true", help="实际加载模型并跑一次向量/重排")
    args = parser.parse_args()

    print("=" * 64)
    print(" 知库 RAG 环境检查")
    print("=" * 64)

    print("\n[依赖版本]")
    for name in (
        "llama-index-core",
        "llama-index-llms-openai-like",
        "llama-index-embeddings-huggingface",
        "llama-index-vector-stores-chroma",
        "chromadb",
        "sentence-transformers",
        "transformers",
        "torch",
        "unstructured",
        "unstructured-inference",
        "spacy",
        "fastapi",
        "modelscope",
    ):
        print(f"  {name:45s} {package_version(name)}")

    print("\n[关键模块]")
    checks = [
        ("llama_index.core", "LlamaIndex Core"),
        ("llama_index.llms.openai_like", "OpenAI-like LLM"),
        ("llama_index.embeddings.huggingface", "HuggingFace Embedding"),
        ("llama_index.vector_stores.chroma", "Chroma Vector Store"),
        ("chromadb", "ChromaDB"),
        ("sentence_transformers", "SentenceTransformers / CrossEncoder"),
        ("unstructured.partition.auto", "Unstructured partition"),
        ("unstructured_inference", "Unstructured PDF inference"),
        ("spacy", "spaCy"),
        ("fastapi", "FastAPI"),
    ]
    ok = all(check_import(module, label) for module, label in checks)

    print("\n[配置]")
    print(f"  .env 文件：{'存在' if (ROOT / '.env').exists() else '不存在（使用默认值）'}")
    print(f"  千问 Key：{'已配置' if settings.qwen_api_key else '未配置'}")
    print(f"  DeepSeek Key：{'已配置' if settings.deepseek_api_key else '未配置'}")
    print(f"  默认模型：{settings.default_llm}")

    print("\n[本地模型]")
    for label, configured in (("Embedding", settings.embedding_model), ("Reranker", settings.reranker_model)):
        path = Path(configured)
        if not path.is_absolute():
            path = ROOT / path
        ready = path.exists() and (path / "config.json").exists()
        print(f"  {label:10s} {'就绪' if ready else '缺失'}  {path}")
        if not ready:
            ok = False

    print("\n[数据目录]")
    settings.ensure_directories()
    print(f"  原始文档：{settings.documents_dir}")
    print(f"  Chroma：{settings.chroma_dir}")
    print(f"  文件清单：{settings.registry_path}")

    if args.load_models:
        print("\n[模型实测]")
        try:
            from llama_index.core.schema import NodeWithScore, TextNode

            from app.services.embeddings import embedding_service
            from app.services.reranker import reranker

            vector = embedding_service.get().get_text_embedding("差旅住宿标准是多少？")
            print(f"  Embedding OK：{len(vector)} 维")
            nodes = [
                NodeWithScore(node=TextNode(text="一线城市普通员工住宿标准为 500 元/晚。"), score=0.5),
                NodeWithScore(node=TextNode(text="公司年会通常在每年一月举行。"), score=0.4),
            ]
            ranked = reranker.rerank("住宿标准", nodes, top_n=2)
            print("  Reranker OK：" + " | ".join(f"{item.node.get_content()[:18]}… {item.score:.4f}" for item in ranked))
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] {exc}")
            ok = False

    print("\n" + "=" * 64)
    if ok:
        print(" 环境检查通过。填写 .env 后运行：python run.py")
    else:
        print(" 仍有未就绪项，请按上面的提示处理。")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())