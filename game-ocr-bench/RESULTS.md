# ゲーム画面 OCR 精度比較 — 調査結果（v0.2）

無料ローカル OCR エンジンを、同一の正解データ・同一指標で比較した結果。

> ⚠️ **サンプル 5 枚・各 1 領域**の予備調査。数値は「方向性の目安」で統計的結論ではない
> （設計書 §12「少数サンプルでの過度な一般化」に注意）。傾向を固めるには枚数・領域を増やす。

**v0.1 → v0.2 の主な訂正**: v0.1 で「Tesseract はこのフォントの認識が弱い」と結論したが、
これは誤りだった。原因は **ROI の既定 psm=7（単一行）** で、複数行のセリフ枠を 1 行として
扱いほぼ空を返していただけ。**psm=6（ブロック）にすると Tesseract は EasyOCR と互角**に読める。
この発見を受けて既定を `roi → psm 6` に修正済み（`adapters/tesseract.py`）。

---

## 1. 調査条件

| 項目 | 内容 |
|---|---|
| 対象 | ゲーム画面 5 枚・各 1 領域。Deltarune 戦闘セリフ ×4（ピクセルフォント）＋ Street Fighter6 エラーダイアログ ×1（システムsansフォント・ファイルパス含む） |
| 言語 | 英語 |
| エンジン | **Tesseract 5.5.3（CPU, 辞書オフ）** / **EasyOCR 1.7.2（GPU: RTX 4060）**。PaddleOCR は保留 |
| モード | `fullscreen`（全画面）/ `roi`（正解領域を切り出して認識） |
| 前処理 | `raw` / `tuned`(auto_invert+Lanczos2x+Otsu) / `pixel`(auto_invert+最近傍3x+Otsu) |
| 指標 | micro CER（主）・完全一致率・誤検出テキスト量・FPS。正規化 strict |

---

## 2. 結果（全 5 枚プール）

### 2.1 ROI（セリフ枠を切り出して読む＝純粋な認識力）

| エンジン / 条件 | micro CER | 完全一致率 |
|---|---:|---:|
| **tesseract / raw（psm6）** | **0.095** | 0.20 |
| **easyocr / raw** | **0.116** | 0.20 |
| easyocr / tuned | 0.190 | 0.00 |
| easyocr / pixel | 0.193 | 0.00 |
| tesseract / pixel（psm6） | 0.758 | 0.00 |
| tesseract / raw（**psm7=旧既定**） | 0.902 | 0.00 |
| tesseract / tuned（psm7） | 0.908 | 0.00 |

*Tesseract は psm=6 で 0.095、psm=7 では 0.902。設定 1 つで結果が激変する。*

### 2.2 fullscreen（全画面＝実運用。誤検出量に注目）

| エンジン / 条件 | micro CER | 誤検出文字数 |
|---|---:|---:|
| **easyocr / raw** | **0.422** | 80 |
| easyocr / tuned | 0.443 | 80 |
| easyocr / pixel | 0.465 | 79 |
| tesseract / pixel | 0.612 | 96 |
| tesseract / tuned | 0.657 | 127 |
| tesseract / raw | 1.315 | 237 |

*micro CER が 1.0 超は、背景テクスチャを文字と誤認した挿入誤りが GT 文字数を上回るため。*

### 2.3 Tesseract ROI を psm6 で読み直した個別結果

```
s1 CER=0.043  "x But it didn't interest me, so you can take it."
s2 CER=0.082  "* ... don't think I'm serious? Check the price tagf"
s3 CER=0.000  "But ain't every story better with a little twist?"     ← 完全一致
s4 CER=0.218  "a * Damn... I dunno what S this axe is, but it ... looks awesomet"
s5 CER=0.102  "C¥Program Files (x86)¥Steam¥steamapps¥common¥Street Fighter 6¥…Failed. Please restart…"
```

---

## 3. 考察（使い分け）

1. **正しく設定すれば ROI 認識は互角**。tesseract(psm6) 0.095 ≒ easyocr(raw) 0.116。
   Deltarune のピクセルフォントも SF6 のシステムフォントも、両者とも十分読める。
2. **EasyOCR は"素で"強い（設定不要）**。psm も前処理も選ばず raw で 0.116。
   一方 **Tesseract は psm の当たり外れが大きい**（psm7 だと 0.90）。運用の手間が段違い。
3. **既定 psm=7 は複数行領域で罠**。ゲームのセリフ枠は複数行が多く、単一行 psm では
   ほぼ空を返す。→ **本ツールの roi 既定を psm=6 に修正**した。
4. **EasyOCR に前処理は不要〜逆効果**（ROI: raw 0.116 → tuned/pixel 0.19）。二値化は悪化。
5. **全画面は EasyOCR 優位**（0.422 vs Tesseract 最良 0.612）。無加工 Tesseract の全画面は
   破綻（CER 1.315・誤検出 237 文字）。前処理で誤検出は減るが EasyOCR に届かない。

### 暫定・使い分け表

| 条件 | 推奨 | 補足 |
|---|---|---|
| セリフ枠を切り出して読む（ROI 運用） | **EasyOCR(raw)** または **Tesseract(psm6)** | 精度は互角。設定不要な EasyOCR が楽 |
| 全画面から拾う | **EasyOCR(raw)** | 背景の誤検出が最少。前処理不要 |
| Tesseract を使う場合 | ROI + **psm=6** 必須 | 複数行は psm7 で失敗。前処理は fullscreen 時のみ有効 |

---

## 4. 限界と次の一手

- **サンプル 5 枚・各 1 領域**。特に非Deltarune は SF6 1 枚のみ。フォント種を散らして増やす。
- `text_type` は既定 hud のまま、条件タグ（`font_style` 等）未設定のため条件別ヒートマップは薄い。
  **箱ごとに type を選び、画像に font_style=pixel 等を付与**すると使い分け表が埋まる。
- 完全一致率が低い(0.20)のは軽微な差（先頭の `#`/`*`、`Damn.` vs `Damn...`、パスの `¥` vs `#`、
  GT 側の先頭タブ等）。後処理・GT表記の統一で改善余地。
- PaddleOCR を 3 エンジン目に加えると多数決 GT と比較の厚みが増す。

### 再現手順

```bat
conda activate ocrbench
cd C:\Users\USER\Desktop\translation-app\game-ocr-bench
set PYTHONUTF8=1
set OCR_BENCH_TESSERACT_CMD=C:\Users\USER\anaconda3\envs\ocrbench\Library\bin\tesseract.exe

ocr-bench ingest
ocr-bench run --engines tesseract,easyocr --mode fullscreen,roi --preprocess raw,tuned,pixel
ocr-bench eval --norm strict,loose
ocr-bench report --group-by font_style,text_type --out out/report.html
```

*Tesseract の ROI 既定は psm=6（複数行対応）。単一行と分かっている領域だけ psm=7 を使うと僅かに速い。*
