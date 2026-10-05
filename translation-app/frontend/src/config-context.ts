/** アプリ設定（GET /api/config）の共有コンテキスト。 */
import { createContext, useContext } from 'react';

import type { AppConfig } from './api/client';

export interface ConfigState {
  config: AppConfig | null;
  loading: boolean;
  error: string | null;
}

export const ConfigContext = createContext<ConfigState>({
  config: null,
  loading: true,
  error: null,
});

export function useConfigState(): ConfigState {
  return useContext(ConfigContext);
}
