"""Download the two local BAAI models.

Usage:
    python scripts/download_models.py
    python scripts/download_models.py --source hf
    python scripts/download_models.py --only embedding
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

MODELS = {
    "embedding": ("BAAI/bge-base-zh-v1.5", settings.embedding_model),
    "reranker": ("BAAI/bge-reranker-base", settings.reranker_model),
}


def human_size(path: Path) -> str:
    total = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    value = float(total)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def download_modelscope(repo_id: str, target: Path) -> None:
    from modelscope import snapshot_download

    target.mkdir(parents=True, exist_ok=True)
    print(f"  ModelScope: {repo_id} -> {target}")
    snapshot_download(repo_id, local_dir=str(target))


def download_hf(repo_id: str, target: Path) -> None:
    from huggingface_hub import snapshot_download

    target.mkdir(parents=True, exist_ok=True)
    print(f"  HuggingFace: {repo_id} -> {target} (endpoint: {settings.hf_endpoint})")
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target),
        endpoint=settings.hf_endpoint,
        ignore_patterns=["*.onnx", "onnx/*", "openvino/*", "*.msgpack", "*.h5"],
    )


def is_ready(target: Path) -> bool:
    if not target.exists():
        return False
    has_config = (target / "config.json").exists()
    has_weights = any(target.glob("*.safetensors")) or any(target.glob("pytorch_model*.bin"))
    return has_config and has_weights


def prune_duplicate_weights(target: Path) -> None:
    """Remove redundant PyTorch/ONNX copies when safetensors already exists."""
    safetensors = list(target.glob("*.safetensors"))
    if safetensors:
        for old in target.glob("pytorch_model*.bin"):
            old.unlink(missing_ok=True)
    for folder in ("onnx", "openvino"):
        path = target / folder
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def download_one(name: str, repo_id: str, configured_path: str, source: str) -> bool:
    target = Path(configured_path)
    if not target.is_absolute():
        target = ROOT / target
    print(f"\n[{name}] {repo_id}")
    if is_ready(target):
        prune_duplicate_weights(target)
        print(f"  已存在，跳过：{target} ({human_size(target)})")
        return True

    target.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    order = ["modelscope", "hf"] if source == "auto" else [source]
    for current in order:
        try:
            if current == "modelscope":
                download_modelscope(repo_id, target)
            else:
                download_hf(repo_id, target)
            if is_ready(target):
                prune_duplicate_weights(target)
                print(f"  完成：{target} ({human_size(target)})")
                return True
            errors.append(f"{current}: 下载后未找到模型权重")
        except Exception as exc:  # noqa: BLE001 - report and try the next source
            errors.append(f"{current}: {exc}")
            print(f"  {current} 失败：{exc}")

    print("  下载失败：")
    for error in errors:
        print("   -", error)
    if target.exists() and not any(target.iterdir()):
        shutil.rmtree(target, ignore_errors=True)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 BGE 向量模型和重排序模型")
    parser.add_argument("--source", choices=["auto", "modelscope", "hf"], default="auto")
    parser.add_argument("--only", choices=["embedding", "reranker", "all"], default="all")
    args = parser.parse_args()

    print("=" * 64)
    print(" 下载本地模型（首次约需 1.5–3 GB 磁盘空间）")
    print("=" * 64)

    selected = ["embedding", "reranker"] if args.only == "all" else [args.only]
    ok = True
    for name in selected:
        repo_id, configured_path = MODELS[name]
        if not download_one(name, repo_id, configured_path, args.source):
            ok = False

    print("\n" + "=" * 64)
    if ok:
        print(" 全部模型已就绪。下一步：python run.py")
    else:
        print(" 有模型未下载成功，请检查网络后重试。")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())