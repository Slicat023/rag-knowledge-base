from __future__ import annotations

import os
from pathlib import Path

# Keep unit tests offline and isolated from the real knowledge base.
os.environ.setdefault("WARMUP_MODELS", "false")
os.environ.setdefault("DATA_DIR", str(Path(__file__).resolve().parent / ".data"))
os.environ["QWEN_API_KEY"] = ""
os.environ["DASHSCOPE_API_KEY"] = ""
os.environ["DEEPSEEK_API_KEY"] = ""