/** ホーム（DESIGN.md 第8.2章）。最新の翻訳履歴を5件カード表示。 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { fetchHistory, type HistoryItem } from '../api/client';

const LIMIT = 5;

/** 代表表示用に先頭ブロックを取り出す（空配列でも落ちないようにする）。 */
function head(blocks: string[]): string {
  return blocks[0] ?? '';
}

export function Home() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchHistory(LIMIT)
      .then((rows) => {
        if (!cancelled) {
          setItems(rows);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '履歴の取得に失敗しました');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <h1>ホーム</h1>
      <div className="notice">最新の翻訳履歴{LIMIT}件</div>

      {error !== null && <div className="error">{error}</div>}
      {loading && <div className="notice">読み込み中…</div>}
      {!loading && items.length === 0 && (
        <div className="notice">
          履歴はまだありません。<Link to="/detection">文字検出</Link> または{' '}
          <Link to="/translate">翻訳ページ</Link> から試してください。
        </div>
      )}

      {items.map((item) => {
        const rest = item.source_blocks.length - 1;
        return (
          <div className="card" key={item.id}>
            <div className="card-head">
              <div className="badges">
                <span className="badge">{item.translation_api}</span>
                {item.ocr_engine !== null && <span className="badge">{item.ocr_engine}</span>}
                {item.block_mode !== null && (
                  <span className="badge">{item.block_mode === 'split' ? '分割' : '一括'}</span>
                )}
              </div>
              <span className="timestamp">{item.created_at}</span>
            </div>
            <div className="pair">
              <div className="pair-cell">{head(item.source_blocks)}</div>
              <div className="pair-cell">{head(item.translated_blocks)}</div>
            </div>
            {rest > 0 && <div className="block-index">他 {rest} 件のブロック</div>}
          </div>
        );
      })}

      {items.length > 0 && (
        <div className="notice">
          <Link to="/history">すべての履歴を見る</Link>
        </div>
      )}
    </>
  );
}
