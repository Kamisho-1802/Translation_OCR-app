# game-ocr-bench

ゲーム画面のスクリーンショットに対し、無料で使える 3 つの OCR エンジン
（**Tesseract 5.x / EasyOCR / PaddleOCR**）を同一の正解データ・同一の指標で比較する。
仕様は [`game-ocr-bench-spec.md`](../game-ocr-bench-spec.md) を参照。

📊 **調査結果（5枚・予備調査）: [RESULTS.md](RESULTS.md)** — ROI認識は EasyOCR(raw) と Tesseract(psm6) が互角。EasyOCR は設定不要で楽・全画面は優位。

## 実装フェーズの進捗

| Phase | 内容 | 状態 |
|---|---|---|
| M1 | 型定義・SQLite・レジストリ・CLI 骨組み・前処理・Tesseract アダプタ | ✅ 完了・検証済 |
| M2 | Evaluator（正規化・CER/WER・編集内訳・完全一致）+ 単体テスト | ✅ 完了・検証済 |
| M3 | EasyOCR アダプタ（GPU 稼働）、バッチ実行、ウォームアップ、レイテンシ/FPS | ✅ 完了（PaddleOCR は保留）|
| M4 | ROI モード、検出評価（IoU/Recall/Precision）、誤検出テキスト量 | ✅ 完了・検証済 |
| M5 | GT ブートストラップ + レビュー CLI + 監査 | ✅ 完了（実データで人手確定が残る）|
| M6 | 色キーイング、前処理スイープ、条件別集計 | ✅ 完了 |
| M7 | Streamlit UI（5 タブ）・HTML レポート | ✅ 完了（起動・描画確認済）|

**全 54 テスト緑**。2 エンジン（Tesseract/EasyOCR-GPU）で ingest→run→eval→report→GT→sweep→UI が通し稼働。

> **エンジン状況**: Tesseract（CPU）と EasyOCR（GPU）が稼働。**PaddleOCR は保留**
> （現行 env に入れると OpenCV ダウングレード等で EasyOCR/torch を壊すリスクがあるため）。
> 後から `adapters/` の登録だけで組み込める設計。
>
> **実行環境**: 専用 conda env `ocrbench`（Python 3.11 + conda-forge Tesseract）。
> Windows 標準の Python/Tesseract インストーラは非対話環境でハングするため conda を使用。
> 実行時は `PYTHONUTF8=1` と `OCR_BENCH_TESSERACT_CMD` を設定（cp932 クラッシュ回避）。

## セットアップ

### 1. Python（本体が未導入の場合）

```powershell
winget install -e --id Python.Python.3.11
```

インストール後、新しいターミナルで `python --version` が `3.11.x` を返すこと。

### 2. Tesseract 本体（M1 で必要）

```powershell
winget install -e --id UB-Mannheim.TesseractOCR
```

`tesseract --version` が通ること。通らない場合は
`C:\Program Files\Tesseract-OCR` を PATH に追加する。

### 3. Python 依存

```powershell
cd game-ocr-bench
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev,eval]
```

EasyOCR / PaddleOCR（GPU）は M3 で追加する。

## 使い方（M1 時点）

```powershell
# 登録エンジン・前処理一覧
ocr-bench info

# 合成テスト画像を 1 枚生成（実ゲーム画像が揃う前の動作確認用）
python scripts/gen_synthetic.py data/game/images/0001.png

# 1 枚を raw / tuned 両条件で認識して DB 保存
ocr-bench run --engines tesseract --mode fullscreen --preprocess raw,tuned --image data/game/images/0001.png
```

### データセット一括（M3〜M7）

実行前提: 環境変数を設定（cp932 クラッシュ回避と Tesseract 検出）。
`PYTHONUTF8=1` と `OCR_BENCH_TESSERACT_CMD=<env>\Library\bin\tesseract.exe`、
かつ `<env>\Library\bin` を PATH に追加。

```powershell
ocr-bench annotate                                                 # 箱描画ツールをブラウザで開く（regions JSON 生成）
ocr-bench ingest                                                   # images/ を登録・regions/GT 取込
ocr-bench run --engines tesseract,easyocr --mode fullscreen,roi --preprocess raw,tuned
ocr-bench eval --norm strict,loose                                 # 指標を計算（推論しない）
ocr-bench gt bootstrap --engines all                               # 多数決で GT 下書き
ocr-bench gt review --accept-agreed                                # 一致は自動確定・不一致のみ人手
ocr-bench gt audit --sample-rate 0.2                               # fantasy/pixel 優先で抜取監査
ocr-bench sweep --engine easyocr --param mag_ratio --values 1.0,2.0 --filter font_style=hud
ocr-bench report --group-by font_style,text_type --out out/report.html
streamlit run ocr_bench/ui/app.py                                  # 5 タブ UI（差分ビュー付き）
```

## テスト

```powershell
pytest -q
```

- 前処理・ハッシュ・DB・キャッシュのテストは外部エンジン不要。
- Tesseract バイナリが無い場合、認識の統合テストは自動 skip。

## ディレクトリ

```
ocr_bench/
  core/       types.py registry.py cache.py images.py db.py hashing.py config.py schema.sql
  preprocess/ pipeline.py ops.py colorkey.py
  adapters/   tesseract.py            (easyocr.py / paddleocr.py は M3)
  runner/     runner.py               (sweep.py は M6)
  eval/ gt/ report/ ui/               (後続フェーズ)
config/       engines.yaml preprocess.yaml norm_profiles.yaml colorkeys.yaml
data/game/    images/ regions/ gt/ manifest.yaml
db/           bench.sqlite
tests/
```
