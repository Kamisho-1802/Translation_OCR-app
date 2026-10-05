"""環境変数の読み込み・設定（DESIGN.md 第5章）。

秘密情報は必ず .env から読む（ハードコード禁止）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# backend/.env を読む。無ければ環境変数のみで動作する。
load_dotenv(BASE_DIR / ".env")


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().split("#")[0].strip().lower() in {"1", "true", "yes", "on"}


def _get_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    # .env に「値 # コメント」形式で書かれていても拾えるようにする
    return raw.split("#")[0].strip()


def _get_int(name: str, default: int) -> int:
    raw = _get_str(name, "")
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """アプリ設定。読み込みは起動時に1回だけ行う。"""

    # --- トグル制御 ---
    enable_engine_toggle: bool = field(
        default_factory=lambda: _get_bool("ENABLE_ENGINE_TOGGLE", True)
    )
    default_translation_api: str = field(
        default_factory=lambda: _get_str("DEFAULT_TRANSLATION_API", "deepl")
    )
    default_ocr_engine: str = field(
        default_factory=lambda: _get_str("DEFAULT_OCR_ENGINE", "easyocr")
    )

    # --- 翻訳API認証 ---
    azure_translator_key: str = field(
        default_factory=lambda: _get_str("AZURE_TRANSLATOR_KEY", "")
    )
    azure_translator_region: str = field(
        default_factory=lambda: _get_str("AZURE_TRANSLATOR_REGION", "")
    )
    azure_translator_endpoint: str = field(
        default_factory=lambda: _get_str(
            "AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com"
        )
    )
    deepl_api_key: str = field(default_factory=lambda: _get_str("DEEPL_API_KEY", ""))
    deepl_api_url: str = field(
        default_factory=lambda: _get_str("DEEPL_API_URL", "https://api-free.deepl.com")
    )

    # --- OCR ---
    tesseract_cmd: str = field(default_factory=lambda: _get_str("TESSERACT_CMD", ""))
    tessdata_prefix: str = field(default_factory=lambda: _get_str("TESSDATA_PREFIX", ""))

    # --- 検証用モック（DESIGN.md には無い。IMPLEMENTATION_STEPS の
    #     「モック→本実装」検証を .env だけで切り替えるための追加フラグ） ---
    use_mock_translator: bool = field(
        default_factory=lambda: _get_bool("USE_MOCK_TRANSLATOR", False)
    )
    use_mock_ocr: bool = field(default_factory=lambda: _get_bool("USE_MOCK_OCR", False))

    # --- 画像入力制約 ---
    max_image_size_mb: int = field(
        default_factory=lambda: _get_int("MAX_IMAGE_SIZE_MB", 10)
    )
    allowed_image_types_raw: str = field(
        default_factory=lambda: _get_str("ALLOWED_IMAGE_TYPES", "image/png,image/jpeg")
    )

    # --- DB ---
    database_path_raw: str = field(
        default_factory=lambda: _get_str("DATABASE_PATH", "./data/history.db")
    )

    @property
    def allowed_image_types(self) -> frozenset[str]:
        return frozenset(
            t.strip().lower() for t in self.allowed_image_types_raw.split(",") if t.strip()
        )

    @property
    def max_image_size_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024

    @property
    def database_path(self) -> Path:
        path = Path(self.database_path_raw)
        # 相対パスは backend/ を基準にする（起動ディレクトリに依存させない）
        return path if path.is_absolute() else (BASE_DIR / path).resolve()


settings = Settings()
