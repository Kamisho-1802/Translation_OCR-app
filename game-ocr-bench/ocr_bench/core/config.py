"""config/*.yaml のロードとプリセット解決。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@lru_cache(maxsize=None)
def _load(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"設定ファイルがありません: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def engines() -> dict[str, Any]:
    return _load("engines.yaml")


def preprocess() -> dict[str, Any]:
    return _load("preprocess.yaml")


def norm_profiles() -> dict[str, Any]:
    return _load("norm_profiles.yaml")


def colorkeys() -> dict[str, Any]:
    return _load("colorkeys.yaml")


def resolve_preprocess(name_or_steps: Any) -> list:
    """プリセット名なら展開、既に steps ならそのまま返す。"""
    if isinstance(name_or_steps, str):
        presets = preprocess().get("presets", {})
        if name_or_steps in presets:
            return presets[name_or_steps]
        # プリセット名でなければ単一 op 名とみなす。
        return [name_or_steps]
    return name_or_steps


def engine_base_options(engine_id: str) -> dict[str, Any]:
    """エンジンの base オプションを返す（無ければ空 dict）。"""
    return dict(engines().get(engine_id, {}).get("base", {}))
