"""OCRがうまく取れない画像の切り分け用ツール（アプリ本体からは使わない）。

1枚の画像に対して、
  - Tesseract を複数の PSM（レイアウト解析モード）で
  - easyOCR を既定設定と、小さい文字向けに緩めた設定で
  - さらに前処理（グレースケール+コントラスト強調 / 2倍拡大）を掛けた版でも
実行し、それぞれ何文字取れたかと先頭の抽出結果を並べて表示する。

使い方（PowerShell、backend ディレクトリで）:

    ./.venv/Scripts/python.exe tools/ocr_probe.py "C:/path/to/photo.jpg" ja

第2引数は ja / en（省略時 ja）。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from PIL import Image, ImageOps  # noqa: E402

from services.ocr.base import load_image  # noqa: E402
from services.ocr.tesseract import _configure_tesseract  # noqa: E402

TESSERACT_LANG = {"ja": "jpn", "en": "eng"}
EASYOCR_LANG = {"ja": ["ja", "en"], "en": ["en"]}

# 3=自動(文書向き) 11=疎なテキスト 6=均一ブロック 12=疎なテキスト+向き検出
PSM_LIST = (3, 11, 6, 12)


def variants(image: Image.Image) -> list[tuple[str, Image.Image]]:
    """前処理違いの画像を作る。"""
    gray = ImageOps.autocontrast(image.convert("L")).convert("RGB")
    doubled = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)
    return [
        ("原寸", image),
        ("グレー+コントラスト強調", gray),
        ("2倍拡大", doubled),
    ]


def preview(text: str, limit: int = 70) -> str:
    flat = " / ".join(line for line in text.splitlines() if line.strip())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def run_tesseract(image: Image.Image, lang: str) -> None:
    pytesseract = _configure_tesseract()
    for label, variant in variants(image):
        for psm in PSM_LIST:
            t0 = time.perf_counter()
            try:
                text = pytesseract.image_to_string(
                    variant, lang=lang, config=f"--oem 3 --psm {psm}"
                )
            except Exception as exc:  # noqa: BLE001 - 切り分け用なので握りつぶす
                print(f"  tesseract psm{psm:<2} {label:<22} エラー: {exc}")
                continue
            chars = len(text.strip().replace("\n", ""))
            ms = int((time.perf_counter() - t0) * 1000)
            print(f"  tesseract psm{psm:<2} {label:<22} {chars:>4}文字 {ms:>5}ms  {preview(text)}")


def run_easyocr(image: Image.Image, lang_mode: str) -> None:
    import numpy as np

    import easyocr

    langs = EASYOCR_LANG[lang_mode]
    reader = easyocr.Reader(langs, gpu=True)
    settings: list[tuple[str, dict[str, float]]] = [
        ("既定", {}),
        ("しきい値を緩める", {"text_threshold": 0.5, "low_text": 0.3}),
        ("2倍に拡大して検出", {"mag_ratio": 2.0}),
        ("緩める+拡大", {"text_threshold": 0.5, "low_text": 0.3, "mag_ratio": 2.0}),
    ]
    for label, kwargs in settings:
        t0 = time.perf_counter()
        try:
            detections = reader.readtext(np.array(image), detail=1, **kwargs)
        except Exception as exc:  # noqa: BLE001
            print(f"  easyocr   {label:<28} エラー: {exc}")
            continue
        text = "\n".join(str(d[1]) for d in detections if len(d) > 1)
        ms = int((time.perf_counter() - t0) * 1000)
        print(
            f"  easyocr   {label:<28} {len(detections):>3}箇所 "
            f"{len(text.replace(chr(10), '')):>4}文字 {ms:>5}ms  {preview(text)}"
        )


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    path = Path(sys.argv[1])
    lang_mode = sys.argv[2] if len(sys.argv) > 2 else "ja"
    if lang_mode not in TESSERACT_LANG:
        raise SystemExit("第2引数は ja か en です")

    raw = path.read_bytes()
    image = load_image(raw)
    with Image.open(path) as original:
        exif_applied = original.size != image.size

    print(f"画像       : {path.name}")
    print(f"サイズ     : {image.width} x {image.height} px / {len(raw) / 1024 / 1024:.1f} MB")
    print(f"EXIF回転   : {'適用した（元は横向き）' if exif_applied else 'なし'}")
    print(f"言語       : {lang_mode}")
    print("-" * 100)
    run_tesseract(image, TESSERACT_LANG[lang_mode])
    print("-" * 100)
    run_easyocr(image, lang_mode)


if __name__ == "__main__":
    main()
