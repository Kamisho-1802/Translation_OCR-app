/** 起動時に GET /api/config を1回だけ呼び、結果を配下へ渡す。 */
import { useEffect, useState, type ReactNode } from 'react';

import { fetchConfig, type AppConfig } from '../api/client';
import { ConfigContext, type ConfigState } from '../config-context';

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConfigState>({
    config: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    fetchConfig()
      .then((config: AppConfig) => {
        if (!cancelled) {
          setState({ config, loading: false, error: null });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : '設定の取得に失敗しました';
          setState({ config: null, loading: false, error: message });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return <ConfigContext.Provider value={state}>{children}</ConfigContext.Provider>;
}
