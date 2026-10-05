/**
 * バックエンドAPIの型付きラッパ（DESIGN.md 第6章）。
 * any は使わない。レスポンスは unknown 経由で受け取り、必要な形へ絞り込む。
 */

export type Lang = 'ja' | 'en';
export type TranslationApi = 'azure' | 'deepl';
export type OcrEngineName = 'tesseract' | 'easyocr' | 'mangaocr';
export type BlockMode = 'single' | 'split';
export type Origin = 'detection' | 'translate';

export interface AppConfig {
  enable_engine_toggle: boolean;
  default_translation_api: string;
  default_ocr_engine: string;
}

/** 1エンジン分のOCR結果。error が入っているのはそのエンジンだけ失敗したとき。 */
export interface OcrEngineResult {
  ocr_engine: string;
  blocks: string[];
  error: string | null;
}

/** エンジンを選ばせるのではなく、実行した全エンジンの結果が並んで返る。 */
export interface OcrResult {
  results: OcrEngineResult[];
  lang_mode: Lang;
  block_mode: BlockMode;
}

export interface TranslateRequest {
  blocks: string[];
  source_lang: Lang;
  target_lang: Lang;
  translation_api: TranslationApi;
  origin: Origin;
  ocr_engine: OcrEngineName | null;
  block_mode: BlockMode | null;
}

export interface TranslateResult {
  id: number;
  source_blocks: string[];
  translated_blocks: string[];
  source_lang: string;
  target_lang: string;
  translation_api: string;
  created_at: string;
}

export interface HistoryItem {
  id: number;
  source_blocks: string[];
  translated_blocks: string[];
  source_lang: string;
  target_lang: string;
  translation_api: string;
  ocr_engine: string | null;
  block_mode: string | null;
  origin: string;
  created_at: string;
}

interface HistoryListResponse {
  items: HistoryItem[];
}

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

/** バックエンドが返したHTTPエラー。status と表示用メッセージを持つ。 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** FastAPI の {"detail": "..."} からメッセージを取り出す。 */
function extractDetail(body: unknown, fallback: string): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail: unknown = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') {
      return detail;
    }
  }
  return fallback;
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // ボディがJSONでない場合はステータスだけで判断する
  }
  return new ApiError(res.status, extractDetail(body, `通信に失敗しました (HTTP ${res.status})`));
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, 'サーバーに接続できませんでした。バックエンドが起動しているか確認してください。');
  }
  if (!res.ok) {
    throw await toApiError(res);
  }
  return (await res.json()) as T;
}

async function requestNoContent(path: string, init?: RequestInit): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, 'サーバーに接続できませんでした。バックエンドが起動しているか確認してください。');
  }
  if (!res.ok) {
    throw await toApiError(res);
  }
}

/** GET /api/config */
export function fetchConfig(): Promise<AppConfig> {
  return request<AppConfig>('/api/config');
}

/** POST /api/ocr（multipart）。サーバー側で実行するエンジンが決まる。 */
export function runOcr(params: {
  image: File;
  langMode: Lang;
  blockMode: BlockMode;
}): Promise<OcrResult> {
  const form = new FormData();
  form.append('image', params.image);
  form.append('lang_mode', params.langMode);
  form.append('block_mode', params.blockMode);
  return request<OcrResult>('/api/ocr', { method: 'POST', body: form });
}

/** POST /api/translate */
export function runTranslate(req: TranslateRequest): Promise<TranslateResult> {
  return request<TranslateResult>('/api/translate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
}

/** GET /api/history（limit 省略で全件） */
export async function fetchHistory(limit?: number): Promise<HistoryItem[]> {
  const query = limit === undefined ? '' : `?limit=${limit}`;
  const data = await request<HistoryListResponse>(`/api/history${query}`);
  return data.items;
}

/** DELETE /api/history/{id} */
export function deleteHistoryItem(id: number): Promise<void> {
  return requestNoContent(`/api/history/${id}`, { method: 'DELETE' });
}

/** DELETE /api/history（全件） */
export function deleteAllHistory(): Promise<void> {
  return requestNoContent('/api/history', { method: 'DELETE' });
}
