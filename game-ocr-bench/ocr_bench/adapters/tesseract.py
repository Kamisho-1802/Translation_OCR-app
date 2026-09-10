"""Tesseract 5.x アダプタ（仕様書 §3.1 / §3.2）。

重要（受け入れ基準）: 辞書を既定でオフにする（load_system_dawg=0 / load_freq_dawg=0）。
デフォルトでは辞書補正が入り、ゲームの造語（キャラ名・地名）が実在語に化ける。

アダプタは独自の前処理を行わない（§7 規約）。前処理は共通パイプラインが済ませた
画像を受け取る前提。例外は捕捉して OcrResult.error に格納する。
"""

from __future__ import annotations

import time

import numpy as np

from ..core.registry import register
from ..core.types import Box, OcrResult, TextBlock

_ENGINE_ID = "tesseract"

# モード別のデフォルト PSM（§3.2 psm_by_mode）。
_DEFAULT_PSM = {
    "fullscreen": 11,  # sparse text（散在するテキスト）
    "roi_line": 7,     # 単一行
    "roi_block": 6,    # 均一ブロック
    # roi の既定はブロック(6)。ゲームのセリフ枠は複数行が多く、単一行(7)だと
    # 複数行領域でほぼ空を返す（実測: psm7 で CER 0.90 → psm6 で 0.10）。
    # 単一行と分かっている場合は options に psm=7 を渡す。
    "roi": 6,
}


class TesseractEngine:
    id = _ENGINE_ID

    def __init__(self) -> None:
        # import を遅延させ、未インストール時に登録だけで落ちないようにする。
        import os

        import pytesseract  # noqa: F401

        self._pt = pytesseract
        # 環境を activate しなくても tesseract.exe を見つけられるようにする。
        # 優先順: 環境変数 OCR_BENCH_TESSERACT_CMD > PATH 上の tesseract。
        cmd = os.environ.get("OCR_BENCH_TESSERACT_CMD")
        if cmd:
            self._pt.pytesseract.tesseract_cmd = cmd
        self._ensure_tessdata_prefix(os)

    @staticmethod
    def _ensure_tessdata_prefix(os) -> None:
        """eng.traineddata の場所を突き止めて TESSDATA_PREFIX を設定する。

        conda-forge 版は tesseract.exe が <env>/Library/bin、tessdata が
        <env>/share/tessdata に分かれて置かれるため、環境変数が無いと言語ファイルを
        見つけられない。明示指定（OCR_BENCH_TESSDATA_PREFIX / TESSDATA_PREFIX）を
        尊重しつつ、無ければバイナリ位置から相対探索する。
        """
        override = os.environ.get("OCR_BENCH_TESSDATA_PREFIX")
        if override:
            os.environ["TESSDATA_PREFIX"] = override
            return
        if os.environ.get("TESSDATA_PREFIX"):
            return

        import pytesseract as _pt

        tess_cmd = getattr(_pt.pytesseract, "tesseract_cmd", "tesseract")
        if not os.path.isfile(tess_cmd):
            return
        bindir = os.path.dirname(tess_cmd)             # <env>/Library/bin
        library = os.path.dirname(bindir)              # <env>/Library
        env_root = os.path.dirname(library)            # <env>
        candidates = [
            os.path.join(bindir, "tessdata"),
            os.path.join(library, "tessdata"),
            os.path.join(library, "share", "tessdata"),
            os.path.join(env_root, "share", "tessdata"),
        ]
        for c in candidates:
            if os.path.isfile(os.path.join(c, "eng.traineddata")):
                os.environ["TESSDATA_PREFIX"] = c
                return

    def _build_config(self, options: dict, mode: str) -> str:
        oem = options.get("oem", 3)
        psm = options.get("psm") or _DEFAULT_PSM.get(mode, 6)
        # 辞書オフを既定にする（明示的に True を渡さない限り造語矯正を防ぐ）。
        load_system_dawg = int(options.get("load_system_dawg", 0))
        load_freq_dawg = int(options.get("load_freq_dawg", 0))

        parts = [
            f"--oem {oem}",
            f"--psm {psm}",
            f"-c load_system_dawg={load_system_dawg}",
            f"-c load_freq_dawg={load_freq_dawg}",
        ]
        whitelist = options.get("char_whitelist")
        if whitelist:
            parts.append(f"-c tessedit_char_whitelist={whitelist}")
        return " ".join(parts)

    def warmup(self) -> None:
        dummy = np.full((32, 96, 3), 255, dtype=np.uint8)
        try:
            self._pt.image_to_string(dummy, lang="eng", config="--oem 3 --psm 7")
        except Exception:
            # ウォームアップの失敗は握りつぶす（本計測で error として顕在化する）。
            pass

    def recognize(self, image: np.ndarray, options: dict) -> OcrResult:
        mode = options.get("mode", "fullscreen")
        lang = options.get("lang", "eng")
        config = self._build_config(options, mode)

        try:
            t0 = time.perf_counter()
            data = self._pt.image_to_data(
                image,
                lang=lang,
                config=config,
                output_type=self._pt.Output.DICT,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)

            blocks: list[TextBlock] = []
            words: list[str] = []
            n = len(data["text"])
            for i in range(n):
                token = (data["text"][i] or "").strip()
                if not token:
                    continue
                conf_raw = data["conf"][i]
                try:
                    conf = float(conf_raw)
                except (TypeError, ValueError):
                    conf = -1.0
                if conf < 0:  # -1 は非テキスト領域
                    continue
                words.append(token)
                blocks.append(
                    TextBlock(
                        text=token,
                        box=Box(
                            int(data["left"][i]),
                            int(data["top"][i]),
                            int(data["width"][i]),
                            int(data["height"][i]),
                        ),
                        confidence=conf / 100.0,
                    )
                )

            text = " ".join(words)
            return OcrResult(
                engine_id=self.id,
                mode=mode,
                text=text,
                blocks=blocks,
                latency_ms=latency_ms,
                preprocess_ms=0,  # 前処理時間は runner が pipeline から埋める
                raw={"config": config, "lang": lang, "data": data},
            )
        except Exception as exc:  # noqa: BLE001 — 1 エンジンの失敗で全体を止めない
            return OcrResult(
                engine_id=self.id,
                mode=mode,
                text="",
                blocks=[],
                latency_ms=0,
                preprocess_ms=0,
                raw={"config": config},
                error=f"{type(exc).__name__}: {exc}",
            )


def _factory() -> TesseractEngine:
    return TesseractEngine()


register(_ENGINE_ID, _factory)
