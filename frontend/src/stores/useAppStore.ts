import { create } from 'zustand'

interface AppState {
  /** 侧边栏是否折叠 */
  sidebarCollapsed: boolean
  /** 侧边栏宽度（px） */
  sidebarWidth: number
  /** 当前活跃导航项 ID */
  activeNavId: string
  /** 当前选中的账号 */
  currentAccount: string

  toggleSidebar: () => void
  setSidebarCollapsed: (collapsed: boolean) => void
  setActiveNavId: (id: string) => void
  setCurrentAccount: (account: string) => void
}

const SIDEBAR_EXPANDED = 240
const SIDEBAR_COLLAPSED = 64

export const useAppStore = create<AppState>((set) => ({
  sidebarCollapsed: false,
  sidebarWidth: SIDEBAR_EXPANDED,
  activeNavId: 'dashboard',
  currentAccount: 'main',

  toggleSidebar: () =>
    set((state) => {
      const collapsed = !state.sidebarCollapsed
      return {
        sidebarCollapsed: collapsed,
        sidebarWidth: collapsed ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED,
      }
    }),

  setSidebarCollapsed: (collapsed: boolean) =>
    set({
      sidebarCollapsed: collapsed,
      sidebarWidth: collapsed ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED,
    }),

  setActiveNavId: (id: string) => set({ activeNavId: id }),

  setCurrentAccount: (account: string) => set({ currentAccount: account }),
}))
