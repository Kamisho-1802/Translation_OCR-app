"""Tesseract（pytesseract）実装。

split は Tesseract の素の出力単位＝ブロック/段落単位（image_to_data の block_num）
をそのまま1ブロックとする（DESIGN.md 第7.2章）。
"""

from __future__ import annotations

import os
from typing import Any

from .base import OCREngine, OcrError, clean_blocks, load_image

# 内部表現 'ja'/'en' → Tesseract の言語コード
_LANG = {"ja": "jpn", "en": "eng"}

# 試すレイアウト解析モード。3=自動（文書向き）／11=疎なテキスト（看板・写真向き）
_PSM_CANDIDATES = (3, 11)

# この確信度未満の語はスコア計算に数えない
_MIN_CONFIDENCE = 60.0

# 語の間に空白を入れる横方向の間隔（行の高さに対する比率）。
# 日本語は語を空白で区切らないので、文中の字間で空白が入らないよう大きめにする。
# 「営業中    10:00-18:00」のように明らかに離れている場合だけ空白にする。
_WORD_GAP_RATIO = 0.6


def _configure_tesseract() -> Any:
    """pytesseract の実行ファイル・tessdata の場所を設定して返す。"""
    try:
        import pytesseract
    except ImportError as exc:  # pragma: no cover - 環境依存
        raise OcrError("pytesseract がインストールされていません") from exc

    from config import settings

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    if settings.tessdata_prefix:
        os.environ["TESSDATA_PREFIX"] = settings.tessdata_prefix
    elif not os.environ.get("TESSDATA_PREFIX"):
        # conda-forge 版は tesseract.exe が <env>/Library/bin、tessdata が
        # <env>/share/tessdata に分かれるため、バイナリ位置から相対探索する。
        cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
        if os.path.isfile(cmd):
            bindir = os.path.dirname(cmd)
            library = os.path.dirname(bindir)
            env_root = os.path.dirname(library)
            for candidate in (
                os.path.join(bindir, "tessdata"),
                os.path.join(library, "tessdata"),
                os.path.join(library, "share", "tessdata"),
                os.path.join(env_root, "share", "tessdata"),
            ):
                if os.path.isfile(os.path.join(candidate, "eng.traineddata")):
                    os.environ["TESSDATA_PREFIX"] = candidate
                    break
    return pytesseract


class TesseractEngine(OCREngine):
    """Tesseract 5.x。"""

    name = "tesseract"

    def extract(
        self, image_bytes: bytes, lang_mode: str, block_mode: str
    ) -> list[str]:
        lang = _LANG.get(lang_mode)
        if lang is None:
            raise OcrError(f"未対応の言語モードです: {lang_mode}")

        pytesseract = _configure_tesseract()
        image = load_image(image_bytes)
        joiner = "" if lang == "jpn" else " "

        # 入力の見た目（文書スキャンか写真か）で当たり外れが大きいので、
        # 「画像の作り方 × PSM」を数通り試し、最も確信度の高い結果を採る。
        #
        # - 原寸のカラー画像: スクリーンショットや書類ではこれが一番素直
        # - グレースケール+コントラスト強調: 看板や標識を撮った写真で効く。
        #   Tesseract は内部で白黒に二値化してから認識するため、背景に草木や影が
        #   写り込んだカラー写真だと二値化に失敗し、どのPSMでも0文字になりやすい。
        # - PSM 3 は文書向けの自動レイアウト解析、11 は散在する文字（看板向き）。
        candidates: list[tuple[str, Any]] = [("original", image)]
        high_contrast = _to_high_contrast(image)
        if high_contrast is not None:
            candidates.append(("high_contrast", high_contrast))

        best_blocks: list[str] = []
        best_score = -1.0
        for _label, candidate in candidates:
            for psm in _PSM_CANDIDATES:
                try:
                    data = pytesseract.image_to_data(
                        candidate,
                        lang=lang,
                        config=f"--oem 3 --psm {psm}",
                        output_type=pytesseract.Output.DICT,
                    )
                except Exception as exc:  # pytesseract は多様な例外を投げる
                    raise OcrError(f"Tesseract の実行に失敗しました: {exc}") from exc

                score = _confidence_score(data)
                if score > best_score:
                    best_score = score
                    best_blocks = clean_blocks(_group_blocks(data, joiner=joiner))

        if block_mode == "single":
            return clean_blocks(["\n".join(best_blocks)])
        return best_blocks


def _to_high_contrast(image: Any) -> Any | None:
    """グレースケール化してコントラストを最大まで伸ばした画像を返す。

    写真の Tesseract 対策。失敗した場合は None を返し、原寸だけで続行する。
    """
    try:
        from PIL import ImageOps

        return ImageOps.autocontrast(image.convert("L")).convert("RGB")
    except (OSError, ValueError):
        return None


def _confidence_score(data: dict[str, list[Any]]) -> float:
    """「確信度の高い語が何文字取れたか」をスコアにする。

    単純な文字数だと、背景のノイズを文字と誤認した結果が勝ってしまうため、
    確信度でふるいにかけた文字数で比べる。
    """
    score = 0.0
    for i in range(len(data.get("text", []))):
        token = (data["text"][i] or "").strip()
        if not token:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf >= _MIN_CONFIDENCE:
            score += len(token) * (conf / 100.0)
    return score


def _group_blocks(data: dict[str, list[Any]], joiner: str) -> list[str]:
    """image_to_data の結果をブロック（段落）単位のテキストへまとめる。

    改行は行が変わるところにだけ入れる。同じ行に並んでいる語は横につなぎ、
    離れている語の間にだけ空白を入れる（日本語は隣接していれば直結する）。
    """
    # block_num -> line_key -> [(左端, 右端, 高さ, 文字列)]
    blocks: dict[int, dict[tuple[int, int], list[tuple[int, int, int, str]]]] = {}
    count = len(data.get("text", []))
    for i in range(count):
        token = (data["text"][i] or "").strip()
        if not token:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < 0:  # -1 は非テキスト領域
            continue
        left = int(data["left"][i])
        word = (left, left + int(data["width"][i]), int(data["height"][i]), token)
        block_num = int(data["block_num"][i])
        line_key = (int(data["par_num"][i]), int(data["line_num"][i]))
        blocks.setdefault(block_num, {}).setdefault(line_key, []).append(word)

    result: list[str] = []
    for lines in blocks.values():
        result.append("\n".join(_join_words(words, joiner) for words in lines.values()))
    return result


def _join_words(words: list[tuple[int, int, int, str]], joiner: str) -> str:
    """同じ行の語を横につなぐ。離れているところにだけ空白を入れる。"""
    ordered = sorted(words, key=lambda w: w[0])
    line_height = max((w[2] for w in ordered), default=0)
    parts: list[str] = []
    previous_right: int | None = None
    for left, right, _height, token in ordered:
        if previous_right is not None:
            gap = left - previous_right
            parts.append(" " if gap > line_height * _WORD_GAP_RATIO else joiner)
        parts.append(token)
        previous_right = max(previous_right or 0, right)
    return "".join(parts)
