import { PanelLeftClose, PanelLeft } from 'lucide-react'
import { useAppStore } from '@/stores/useAppStore'
import { useTheme } from 'next-themes'
import { Moon, Sun } from 'lucide-react'
import { cn } from '@/lib/utils'

export function Header() {
  const { sidebarCollapsed, toggleSidebar } = useAppStore()
  const { theme, setTheme } = useTheme()

  return (
    <header
      className={cn(
        'flex h-14 items-center justify-between border-b px-4',
        'bg-background/80 backdrop-blur-sm',
      )}
    >
      {/* 左侧：折叠按钮 + 标题 */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleSidebar}
          className={cn(
            'flex items-center justify-center rounded-md p-2',
            'text-muted-foreground hover:bg-secondary hover:text-foreground',
            'transition-colors duration-150',
          )}
          aria-label={sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'}
        >
          {sidebarCollapsed ? (
            <PanelLeft size={18} />
          ) : (
            <PanelLeftClose size={18} />
          )}
        </button>
        <h1 className="text-page-title text-foreground">WeFlow公众号AI写作助手</h1>
      </div>

      {/* 右侧：全局操作 */}
      <div className="flex items-center gap-1">
        {/* 主题切换 */}
        <button
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className={cn(
            'rounded-md p-2 text-muted-foreground',
            'hover:bg-secondary hover:text-foreground',
            'transition-colors duration-150',
          )}
          aria-label="切换主题"
        >
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>

      </div>
    </header>
  )
}
