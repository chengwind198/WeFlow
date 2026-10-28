import { create } from 'zustand'
import type { AppConfig } from '@/types/config'

interface ConfigState {
  /** 完整应用配置 */
  config: AppConfig | null
  /** 是否已加载 */
  loaded: boolean
  /** 加载中 */
  loading: boolean

  setConfig: (config: AppConfig) => void
  setLoading: (loading: boolean) => void
}

export const useConfigStore = create<ConfigState>((set) => ({
  config: null,
  loaded: false,
  loading: false,

  setConfig: (config) => set({ config, loaded: true }),
  setLoading: (loading) => set({ loading }),
}))
