"""SQLite 接続とスキーマ初期化（仕様書 §8）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# リポジトリ標準の DB 位置（game-ocr-bench/db/bench.sqlite）。
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "db" / "bench.sqlite"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """接続を開き、スキーマを冪等に適用して返す。

    Row ファクトリを設定し、外部キーを有効化する。
    """
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """schema.sql を実行（IF NOT EXISTS なので何度呼んでも安全）。"""
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """既存 DB への冪等カラム追加（新規 DB では schema 済みなので no-op）。"""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(regions)")}
    for col, decl in (("voted_text", "TEXT"), ("gt_status", "TEXT"), ("draft_json", "TEXT")):
        if col not in existing:
            conn.execute(f"ALTER TABLE regions ADD COLUMN {col} {decl}")
    metric_cols = {row["name"] for row in conn.execute("PRAGMA table_info(metrics)")}
    if "ref_chars" not in metric_cols:
        conn.execute("ALTER TABLE metrics ADD COLUMN ref_chars INTEGER")
