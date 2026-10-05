"""SQLite接続・初期化・履歴リポジトリ（DESIGN.md 第4章）。

SQL はこのモジュールに閉じ込め、将来 PostgreSQL へ移行しやすくしておく。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from config import settings

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS translation_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_text     TEXT    NOT NULL,
    translated_text TEXT    NOT NULL,
    source_lang     TEXT    NOT NULL,
    target_lang     TEXT    NOT NULL,
    translation_api TEXT    NOT NULL,
    ocr_engine      TEXT,
    block_mode      TEXT,
    origin          TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_history_created_at
    ON translation_history (created_at DESC);
"""

_HISTORY_COLUMNS = """
    id, source_text, translated_text, source_lang, target_lang,
    translation_api, ocr_engine, block_mode, origin, created_at
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """リクエストごとに接続を開き、終了時に閉じる。"""
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """DBファイル・テーブルを起動時に自動生成する。"""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_INDEX_SQL)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """DB行を、JSON配列を復元した dict に変換する。"""
    return {
        "id": row["id"],
        "source_blocks": json.loads(row["source_text"]),
        "translated_blocks": json.loads(row["translated_text"]),
        "source_lang": row["source_lang"],
        "target_lang": row["target_lang"],
        "translation_api": row["translation_api"],
        "ocr_engine": row["ocr_engine"],
        "block_mode": row["block_mode"],
        "origin": row["origin"],
        "created_at": row["created_at"],
    }


def insert_history(
    *,
    source_blocks: Sequence[str],
    translated_blocks: Sequence[str],
    source_lang: str,
    target_lang: str,
    translation_api: str,
    ocr_engine: str | None,
    block_mode: str | None,
    origin: str,
) -> dict[str, Any]:
    """履歴を1件保存し、保存後のレコードを返す。

    source_text / translated_text は常にJSON配列文字列として保存する。
    """
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO translation_history (
                source_text, translated_text, source_lang, target_lang,
                translation_api, ocr_engine, block_mode, origin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                json.dumps(list(source_blocks), ensure_ascii=False),
                json.dumps(list(translated_blocks), ensure_ascii=False),
                source_lang,
                target_lang,
                translation_api,
                ocr_engine,
                block_mode,
                origin,
            ),
        )
        new_id = cur.lastrowid
        row = conn.execute(
            f"SELECT {_HISTORY_COLUMNS} FROM translation_history WHERE id = ?",
            (new_id,),
        ).fetchone()
    return _row_to_dict(row)


def list_history(limit: int | None = None) -> list[dict[str, Any]]:
    """履歴を新しい順に返す。limit 省略時は全件。"""
    sql = f"""
        SELECT {_HISTORY_COLUMNS}
        FROM translation_history
        ORDER BY created_at DESC, id DESC
    """
    params: tuple[int, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def delete_history(history_id: int) -> bool:
    """1件削除。削除できたら True、対象が無ければ False。"""
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM translation_history WHERE id = ?", (history_id,)
        )
        return cur.rowcount > 0


def delete_all_history() -> int:
    """全件削除。削除件数を返す。"""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM translation_history")
        return cur.rowcount
