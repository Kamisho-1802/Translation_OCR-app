/** 翻訳履歴ページ（DESIGN.md 第8.4章）。全件表示＋1件削除＋全削除。 */
import { useCallback, useEffect, useState } from 'react';

import {
  deleteAllHistory,
  deleteHistoryItem,
  fetchHistory,
  type HistoryItem,
} from '../api/client';

function Badges({ item }: { item: HistoryItem }) {
  return (
    <div className="badges">
      <span className="badge">{item.translation_api}</span>
      {item.ocr_engine !== null && <span className="badge">{item.ocr_engine}</span>}
      {item.block_mode !== null && (
        <span className="badge">{item.block_mode === 'split' ? '分割' : '一括'}</span>
      )}
      <span className="badge gray">
        {item.source_lang} → {item.target_lang}
      </span>
      <span className="badge gray">{item.origin}</span>
    </div>
  );
}

export function History() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setItems(await fetchHistory());
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '履歴の取得に失敗しました');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleDelete(id: number) {
    try {
      await deleteHistoryItem(id);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '削除に失敗しました');
    }
  }

  async function handleDeleteAll() {
    // 誤操作防止のため確認ダイアログを必須にする（DESIGN.md 第8.4章）
    if (!window.confirm('履歴をすべて削除します。よろしいですか？')) {
      return;
    }
    try {
      await deleteAllHistory();
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '全削除に失敗しました');
    }
  }

  return (
    <>
      <div className="card-head">
        <h1>翻訳履歴</h1>
        <button
          type="button"
          className="danger"
          onClick={() => void handleDeleteAll()}
          disabled={items.length === 0}
        >
          全削除
        </button>
      </div>

      {error !== null && <div className="error">{error}</div>}
      {loading && <div className="notice">読み込み中…</div>}
      {!loading && items.length === 0 && <div className="notice">履歴はまだありません。</div>}

      {items.map((item) => (
        <div className="card" key={item.id}>
          <div className="card-head">
            <Badges item={item} />
            <div>
              <span className="timestamp">{item.created_at}</span>{' '}
              <button
                type="button"
                className="danger"
                onClick={() => void handleDelete(item.id)}
              >
                削除
              </button>
            </div>
          </div>
          {item.source_blocks.map((source, index) => (
            <div className="block" key={index}>
              {item.source_blocks.length > 1 && (
                <div className="block-index">ブロック {index + 1}</div>
              )}
              <div className="pair">
                <div className="pair-cell">{source}</div>
                <div className="pair-cell">{item.translated_blocks[index] ?? ''}</div>
              </div>
            </div>
          ))}
        </div>
      ))}
    </>
  );
}
