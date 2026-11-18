"""Check that the configured Qwen / DeepSeek key actually works.

    python scripts/check_llm.py --provider qwen
    python scripts/check_llm.py --provider deepseek
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.services.llm import PROVIDER_LABELS, llm_factory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["qwen", "deepseek"], default=settings.default_llm)
    parser.add_argument("--prompt", default="请用一句话介绍你自己，并说明你支持的上下文长度。")
    args = parser.parse_args()

    provider = args.provider
    if not llm_factory.available(provider):
        print(f"{PROVIDER_LABELS.get(provider, provider)} 未配置 API Key，请检查 .env。")
        return 1

    print(f"模型：{settings.model_for(provider)}")
    print(f"地址：{settings.base_url_for(provider)}")
    print(f"问题：{args.prompt}")
    try:
        response = llm_factory.get(provider).complete(args.prompt)
        print("\n回答：")
        print(response.text)
    except Exception as exc:  # noqa: BLE001
        print(f"\n调用失败：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())