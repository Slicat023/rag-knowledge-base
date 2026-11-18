"""Install the small English spaCy model used by Unstructured.

Unstructured lazily downloads ``en_core_web_sm`` from GitHub on first parse.
GitHub release downloads are unreliable on some networks, so this script
tries the official URL plus two mirrors and installs the wheel by extracting
it into the active virtual environment (no pip resolve needed).

The application also has a blank-spaCy fallback, so this step is optional but
recommended for better element classification.
"""

from __future__ import annotations

import hashlib
import sys
import sysconfig
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "models" / "spacy"
FILENAME = "en_core_web_sm-3.8.0-py3-none-any.whl"
SHA256 = "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85"
ASSET = (
    "https://github.com/explosion/spacy-models/releases/download/"
    f"en_core_web_sm-3.8.0/{FILENAME}"
)
URLS = [
    ASSET,
    "https://gh-proxy.com/" + ASSET,
    "https://ghfast.top/" + ASSET,
]


def is_installed() -> bool:
    try:
        import spacy

        spacy.load("en_core_web_sm")
        return True
    except Exception:
        return False


def download() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / FILENAME
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == SHA256:
        print(f"使用已下载的模型：{target}")
        return target

    for url in URLS:
        print(f"尝试下载：{url}")
        try:
            tmp = target.with_suffix(".part")
            with urllib.request.urlopen(url, timeout=20) as response, tmp.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 512)
                    if not chunk:
                        break
                    handle.write(chunk)
            digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
            if digest != SHA256:
                print(f"  校验失败：{digest[:12]}…")
                tmp.unlink(missing_ok=True)
                continue
            tmp.replace(target)
            print(f"  下载完成：{target} ({target.stat().st_size / 1024 / 1024:.1f} MB)")
            return target
        except Exception as exc:  # noqa: BLE001
            print(f"  失败：{exc}")
    raise SystemExit("无法下载 en_core_web_sm，请检查网络后重试。")


def install(wheel: Path) -> None:
    site_packages = Path(sysconfig.get_paths()["purelib"])
    print(f"安装到：{site_packages}")
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(site_packages)
    print("安装完成。")


def main() -> int:
    if is_installed():
        print("en_core_web_sm 已安装，无需重复操作。")
        return 0
    print("=" * 64)
    print(" 安装 Unstructured 需要的 en_core_web_sm")
    print("=" * 64)
    install(download())
    if not is_installed():
        print("安装后仍无法加载，请检查虚拟环境。")
        return 1
    print("验证通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())