"""アダプタ登録。import した時点で registry に登録される。

各アダプタは重い依存（pytesseract/torch 等）をクラス生成時に遅延 import するため、
ここで import してもライブラリ未インストールでは落ちない（登録だけ行われる）。
M3 で easyocr / paddleocr を追加する。
"""

from . import tesseract  # noqa: F401  登録副作用のため
from . import easyocr  # noqa: F401
from . import paddleocr  # noqa: F401
