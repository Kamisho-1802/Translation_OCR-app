/** 翻訳ページ（DESIGN.md 第8.5章）。純粋な翻訳のみ。 */
import { useState } from 'react';

import {
  runTranslate,
  type Lang,
  type TranslateResult,
  type TranslationApi,
} from '../api/client';
import { FixedValue, ToggleGroup } from '../components/EngineToggles';
import { useConfigState } from '../config-context';

const DIRECTIONS: { value: Lang; label: string }[] = [
  { value: 'ja', label: '日本語 → 英語' },
  { value: 'en', label: '英語 → 日本語' },
];

const APIS: { value: TranslationApi; label: string }[] = [
  { value: 'deepl', label: 'DeepL' },
  { value: 'azure', label: 'Azure' },
];

function isTranslationApi(value: string): value is TranslationApi {
  return value === 'deepl' || value === 'azure';
}

export function Translate() {
  const { config } = useConfigState();
  const [sourceLang, setSourceLang] = useState<Lang>('ja');
  // null = 未選択。設定取得後は既定値を使い、ユーザーが選んだらその値を優先する。
  const [pickedApi, setPickedApi] = useState<TranslationApi | null>(null);
  const [text, setText] = useState('');
  const [result, setResult] = useState<TranslateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const defaultApi: TranslationApi =
    config && isTranslationApi(config.default_translation_api)
      ? config.default_translation_api
      : 'deepl';
  const translationApi: TranslationApi = pickedApi ?? defaultApi;

  const targetLang: Lang = sourceLang === 'ja' ? 'en' : 'ja';
  const showToggle = config?.enable_engine_toggle ?? false;

  async function handleTranslate() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await runTranslate({
        blocks: [text],
        source_lang: sourceLang,
        target_lang: targetLang,
        translation_api: translationApi,
        origin: 'translate',
        ocr_engine: null,
        block_mode: null,
      });
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '翻訳に失敗しました');
    } finally {
      setBusy(false);
    }
  }

  const translated = result?.translated_blocks[0] ?? '';

  return (
    <>
      <h1>翻訳ページ</h1>

      <div className="panel toggles">
        <ToggleGroup
          label="翻訳方向"
          options={DIRECTIONS}
          value={sourceLang}
          onChange={setSourceLang}
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
        <textarea
          value={text}
          placeholder={sourceLang === 'ja' ? '翻訳したい日本語を入力' : 'Enter English text'}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="actions">
          <button
            type="button"
            className="primary"
            onClick={() => void handleTranslate()}
            disabled={busy || text.trim() === ''}
          >
            {busy ? '翻訳中…' : '翻訳'}
          </button>
        </div>
      </div>

      {error !== null && <div className="error">{error}</div>}

      {result !== null && (
        <div className="panel">
          <h2>翻訳結果（{result.translation_api}）</h2>
          <div className="pair">
            <div className="pair-cell">{result.source_blocks[0] ?? ''}</div>
            <div className="pair-cell">{translated}</div>
          </div>
        </div>
      )}
    </>
  );
}
