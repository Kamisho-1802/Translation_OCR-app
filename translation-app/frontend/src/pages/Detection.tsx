/**
 * 文字検出ページ。画像 → OCR（Tesseract・easyOCR 同時実行）→ 結果を選んで編集 → 翻訳。
 *
 * DESIGN.md 第8.3章からの変更:
 * - OCRエンジンは選ばせず両方実行し、抽出結果をユーザーが選ぶ方式にした。
 * - ブロックモード（一括/分割）は手直しとスクロールの手間が大きいため一時的に撤去し、
 *   常に一括（single）で実行する。戻すときは BLOCK_MODE をトグルに戻せばよい
 *   （バックエンド・履歴表示は分割のままでも動く）。
 */
import { useState } from 'react';

import {
  runOcr,
  runTranslate,
  type BlockMode,
  type Lang,
  type OcrEngineName,
  type OcrEngineResult,
  type TranslateResult,
  type TranslationApi,
} from '../api/client';
import { FixedValue, ToggleGroup } from '../components/EngineToggles';
import { useConfigState } from '../config-context';

const LANG_MODES: { value: Lang; label: string }[] = [
  { value: 'ja', label: '日本語' },
  { value: 'en', label: '英語' },
];

const APIS: { value: TranslationApi; label: string }[] = [
  { value: 'deepl', label: 'DeepL' },
  { value: 'azure', label: 'Azure' },
];

// 分割モードは一時撤去中。常に一括で実行する。
const BLOCK_MODE: BlockMode = 'single';

const ENGINE_LABELS: Record<string, string> = {
  tesseract: 'Tesseract',
  easyocr: 'easyOCR',
  mangaocr: 'manga-ocr（日本語特化・縦書き対応）',
};

// フロント側の事前バリデーション（最終防衛線はバックエンド。DESIGN.md 第2章）
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const ALLOWED_TYPES = ['image/png', 'image/jpeg'];
const IMAGE_RULE_MESSAGE = '10MBまでのPNG/JPEG画像にしてください';

function isOcrEngine(value: string): value is OcrEngineName {
  return value === 'tesseract' || value === 'easyocr' || value === 'mangaocr';
}

function isTranslationApi(value: string): value is TranslationApi {
  return value === 'deepl' || value === 'azure';
}

/** 一括モードなので、1エンジンの抽出結果は要素0個か1個。 */
function resultText(result: OcrEngineResult): string {
  return result.blocks[0] ?? '';
}

export function Detection() {
  const { config } = useConfigState();

  const [langMode, setLangMode] = useState<Lang>('ja');
  // null = 未選択。設定取得後は既定値を使い、ユーザーが選んだらその値を優先する。
  const [pickedApi, setPickedApi] = useState<TranslationApi | null>(null);

  const [file, setFile] = useState<File | null>(null);
  // 手直しのときに元画像と見比べられるよう、選んだ画像のプレビューURLを持つ。
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const [results, setResults] = useState<OcrEngineResult[] | null>(null);
  // エンジン名 → 編集中テキスト。選び直しても編集内容が消えないようエンジンごとに持つ。
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [selectedEngine, setSelectedEngine] = useState<string | null>(null);

  const [result, setResult] = useState<TranslateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocrBusy, setOcrBusy] = useState(false);
  const [translateBusy, setTranslateBusy] = useState(false);

  const defaultApi: TranslationApi =
    config && isTranslationApi(config.default_translation_api)
      ? config.default_translation_api
      : 'deepl';
  const translationApi: TranslationApi = pickedApi ?? defaultApi;

  const showToggle = config?.enable_engine_toggle ?? false;
  // 画像モードから翻訳方向を自動決定（DESIGN.md 第4章 言語連動ルール）
  const sourceLang: Lang = langMode;
  const targetLang: Lang = langMode === 'ja' ? 'en' : 'ja';

  function clearOcrState() {
    setResults(null);
    setTexts({});
    setSelectedEngine(null);
    setResult(null);
  }

  /** 前のプレビューURLを解放してから、新しい画像のURLを作る。 */
  function replacePreview(selected: File | null) {
    setPreviewUrl((previous) => {
      if (previous !== null) {
        URL.revokeObjectURL(previous);
      }
      return selected === null ? null : URL.createObjectURL(selected);
    });
    setZoomed(false);
  }

  function handleFileChange(selected: File | null) {
    clearOcrState();
    if (selected === null) {
      setFile(null);
      replacePreview(null);
      setError(null);
      return;
    }
    if (!ALLOWED_TYPES.includes(selected.type) || selected.size > MAX_IMAGE_BYTES) {
      setFile(null);
      replacePreview(null);
      setError(IMAGE_RULE_MESSAGE);
      return;
    }
    setFile(selected);
    replacePreview(selected);
    setError(null);
  }

  async function handleOcr() {
    if (file === null) {
      return;
    }
    setOcrBusy(true);
    setError(null);
    clearOcrState();
    try {
      const res = await runOcr({ image: file, langMode, blockMode: BLOCK_MODE });
      setResults(res.results);

      const nextTexts: Record<string, string> = {};
      for (const engineResult of res.results) {
        nextTexts[engineResult.ocr_engine] = resultText(engineResult);
      }
      setTexts(nextTexts);

      // 文字が取れたエンジンを既定で選んでおく（無ければ未選択のまま）
      const usable = res.results.find((item) => resultText(item).trim() !== '');
      setSelectedEngine(usable?.ocr_engine ?? null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'OCRに失敗しました');
    } finally {
      setOcrBusy(false);
    }
  }

  function updateText(engine: string, value: string) {
    setTexts((prev) => ({ ...prev, [engine]: value }));
  }

  const selectedText = selectedEngine === null ? '' : (texts[selectedEngine] ?? '');

  async function handleTranslate() {
    if (selectedEngine === null || selectedText.trim() === '') {
      return;
    }
    setTranslateBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await runTranslate({
        blocks: [selectedText],
        source_lang: sourceLang,
        target_lang: targetLang,
        translation_api: translationApi,
        origin: 'detection',
        // どのエンジンの抽出結果を翻訳したかを履歴に残す
        ocr_engine: isOcrEngine(selectedEngine) ? selectedEngine : null,
        block_mode: BLOCK_MODE,
      });
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '翻訳に失敗しました');
    } finally {
      setTranslateBusy(false);
    }
  }

  const noTextAtAll =
    results !== null && results.every((item) => resultText(item).trim() === '');

  return (
    <>
      <h1>文字検出</h1>

      <div className="panel toggles">
        <ToggleGroup
          label="画像モード"
          options={LANG_MODES}
          value={langMode}
          onChange={setLangMode}
        />
        {showToggle ? (
          <ToggleGroup
            label="翻訳API"
            options={APIS}
            value={translationApi}
            onChange={setPickedApi}
          />
        ) : (
          <FixedValue label="翻訳API" value={config?.default_translation_api ?? '-'} />
        )}
      </div>

      <div className="panel">
        <input
          type="file"
          accept="image/png,image/jpeg"
          onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
        />
        <div className="notice">{IMAGE_RULE_MESSAGE}</div>
        {/* OCR前は、選んだ画像が合っているかをここで確認できるようにする。
            OCR後は左側に大きく出すので、こちらは出さない。 */}
        {previewUrl !== null && results === null && (
          <img
            className="preview-thumb"
            src={previewUrl}
            alt="選択した画像"
            onClick={() => setZoomed(true)}
          />
        )}
        <div className="actions">
          <button
            type="button"
            className="primary"
            onClick={() => void handleOcr()}
            disabled={file === null || ocrBusy}
          >
            {ocrBusy ? 'OCR実行中…' : 'OCR実行'}
          </button>
          <span className="notice">
            翻訳方向: {sourceLang} → {targetLang}
          </span>
        </div>
      </div>

      {error !== null && <div className="error">{error}</div>}

      {results !== null && (
        <>
          <h2>抽出結果（使う方を選んで、必要なら手直ししてください）</h2>
          {noTextAtAll && <div className="notice">文字が検出されませんでした</div>}

          <div className="detection-layout">
            {/* 手直し中もスクロールに追従して元画像が見えるようにする */}
            {previewUrl !== null && (
              <div className="image-pane">
                <img
                  src={previewUrl}
                  alt="OCRにかけた画像"
                  onClick={() => setZoomed(true)}
                />
                <div className="notice">クリックで拡大</div>
              </div>
            )}

            <div className="result-pane">
          {results.map((engineResult) => {
            const engine = engineResult.ocr_engine;
            const text = texts[engine] ?? '';
            const isSelected = selectedEngine === engine;
            const isEmpty = resultText(engineResult).trim() === '';
            return (
              <div className={isSelected ? 'panel selected' : 'panel'} key={engine}>
                <label className="engine-pick">
                  <input
                    type="radio"
                    name="ocr-result"
                    checked={isSelected}
                    disabled={isEmpty && engineResult.error !== null}
                    onChange={() => setSelectedEngine(engine)}
                  />
                  <span className="engine-name">{ENGINE_LABELS[engine] ?? engine}</span>
                  <span className="notice">
                    {engineResult.error !== null
                      ? 'エラー'
                      : isEmpty
                        ? '検出なし'
                        : `${text.length}文字`}
                  </span>
                </label>
                {engineResult.error !== null && (
                  <div className="error">{engineResult.error}</div>
                )}
                {engineResult.error === null && (
                  <textarea
                    value={text}
                    placeholder="文字が検出されませんでした"
                    onChange={(e) => updateText(engine, e.target.value)}
                    onFocus={() => setSelectedEngine(engine)}
                  />
                )}
              </div>
            );
          })}

              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  onClick={() => void handleTranslate()}
                  disabled={
                    selectedEngine === null || selectedText.trim() === '' || translateBusy
                  }
                >
                  {translateBusy ? '翻訳中…' : '翻訳する'}
                </button>
                {selectedEngine !== null && (
                  <span className="notice">
                    {ENGINE_LABELS[selectedEngine] ?? selectedEngine} の結果を翻訳します
                  </span>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {zoomed && previewUrl !== null && (
        <div
          className="lightbox"
          role="presentation"
          onClick={() => setZoomed(false)}
        >
          <img src={previewUrl} alt="拡大した画像" />
        </div>
      )}

      {result !== null && (
        <div className="panel">
          <h2>翻訳結果（{result.translation_api}）</h2>
          <div className="pair">
            <div className="pair-cell">{result.source_blocks[0] ?? ''}</div>
            <div className="pair-cell">{result.translated_blocks[0] ?? ''}</div>
          </div>
        </div>
      )}
    </>
  );
}
