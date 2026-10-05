/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** バックエンドのベースURL（既定: http://localhost:8000） */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
