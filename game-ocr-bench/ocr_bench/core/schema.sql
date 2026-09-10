-- データモデル（仕様書 §8）。実行と評価を分離するためのスキーマ。
-- results は推論結果（pred_text/raw）だけを持ち、metrics は eval が後から埋める。

CREATE TABLE IF NOT EXISTS samples (
  id INTEGER PRIMARY KEY,
  file_path TEXT NOT NULL,
  image_sha256 TEXT NOT NULL UNIQUE,
  gt_text TEXT,                 -- 全画面 GT（regions から生成）
  meta TEXT                     -- 条件タグ（JSON）
);

CREATE TABLE IF NOT EXISTS regions (
  id INTEGER PRIMARY KEY,
  sample_id INTEGER,
  region_key TEXT,              -- 'r1'
  box_json TEXT,
  gt_text TEXT,
  text_type TEXT,
  proper_nouns TEXT,            -- JSON 配列
  order_index INTEGER,
  voted_text TEXT,              -- GT ブートストラップの多数決結果（M5）
  gt_status TEXT,               -- NULL / 'agreed' / 'needs_review' / 'confirmed'
  draft_json TEXT,              -- エンジン別下書き {engine_id: text}
  FOREIGN KEY (sample_id) REFERENCES samples(id),
  UNIQUE(sample_id, region_key)
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT, finished_at TEXT,
  engine_id TEXT, mode TEXT,
  options_json TEXT, options_hash TEXT,
  preprocess_json TEXT, preprocess_hash TEXT,
  git_commit TEXT, device TEXT, note TEXT
);

CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY,
  run_id INTEGER, sample_id INTEGER,
  region_id INTEGER,            -- roi モードのみ。fullscreen は NULL
  pred_text TEXT, blocks_json TEXT, raw_json TEXT,
  latency_ms INTEGER, preprocess_ms INTEGER,
  error TEXT,
  FOREIGN KEY (run_id) REFERENCES runs(id),
  FOREIGN KEY (sample_id) REFERENCES samples(id),
  UNIQUE(run_id, sample_id, region_id)
);

CREATE TABLE IF NOT EXISTS metrics (
  id INTEGER PRIMARY KEY,
  result_id INTEGER,
  norm_profile TEXT,
  cer REAL, wer REAL,
  edit_ins INTEGER, edit_del INTEGER, edit_sub INTEGER,
  exact_match INTEGER,
  proper_noun_acc REAL,
  spurious_chars INTEGER,       -- 誤検出テキスト量
  det_recall REAL, det_precision REAL,
  ref_chars INTEGER,            -- 正規化後 GT 文字数（micro CER の分母）
  FOREIGN KEY (result_id) REFERENCES results(id),
  UNIQUE(result_id, norm_profile)
);

-- キャッシュ検索用インデックス（§8 キャッシュキー）。
CREATE INDEX IF NOT EXISTS idx_runs_cachekey
  ON runs(engine_id, mode, options_hash, preprocess_hash);
CREATE INDEX IF NOT EXISTS idx_results_lookup
  ON results(run_id, sample_id, region_id);
