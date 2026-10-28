import { useAppStore } from '@/stores/useAppStore'
import { cn } from '@/lib/utils'

export function StatusBar() {
  const { currentAccount, sidebarCollapsed } = useAppStore()
  const sidebarWidth = sidebarCollapsed ? 64 : 240

  return (
    <footer
      className={cn(
        'flex h-7 items-center justify-between border-t px-4',
        'bg-muted/30 text-xs text-muted-foreground',
      )}
      style={{ paddingLeft: `calc(${sidebarWidth}px + 1rem)` }}
    >
      <div className="flex items-center gap-4">
        <span>账号：{currentAccount}</span>
        <span>就绪</span>
      </div>
      <div className="flex items-center gap-4">
        <span>weflow v0.1.0</span>
      </div>
    </footer>
  )
}
