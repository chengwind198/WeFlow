import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  PenLine,
  ClipboardCheck,
  Send,
  Palette,
  Settings,
  Sparkles,
  User,
  Image,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Eye,
} from 'lucide-react'
import { useAppStore } from '@/stores/useAppStore'
import { useConfigStore } from '@/stores/useConfigStore'
import { cn } from '@/lib/utils'
import { NAV_ITEMS } from '@/lib/constants'
import type { NavItem } from '@/lib/constants'
import { useEffect } from 'react'

/** 图标映射表 */
const ICON_MAP: Record<string, typeof LayoutDashboard> = {
  LayoutDashboard,
  PenLine,
  ClipboardCheck,
  Send,
  Palette,
  Settings,
  Image,
  RefreshCw,
  Eye,
}

/** 递归判断 path 是否在当前路由下处于激活状态 */
function isPathActive(currentPath: string, item: NavItem): boolean {
  if (item.children && item.children.length > 0) {
    return item.children.some((child) => isPathActive(currentPath, child))
  }
  if (!item.path) return false
  if (item.path === '/') return currentPath === '/'
  if (item.path === '/articles/new') return currentPath === '/articles/new'
  if (item.path === '/newspic/new') return currentPath.startsWith('/newspic')
  return currentPath.startsWith(item.path)
}

/** 侧边栏导航项组件（递归渲染） */
function NavItemRow({
  item,
  depth,
  sidebarCollapsed,
  locationPath,
  defaultExpanded,
}: {
  item: NavItem
  depth: number
  sidebarCollapsed: boolean
  locationPath: string
  defaultExpanded: boolean
}) {
  const hasChildren = item.children && item.children.length > 0
  const [expanded, setExpanded] = useState(defaultExpanded)
  const Icon = ICON_MAP[item.icon] || LayoutDashboard
  const active = isPathActive(locationPath, item)

  // 无子菜单：叶子节点，渲染为 NavLink
  if (!hasChildren) {
    if (!item.path) return null // 无 path 也无 children，不渲染
    return (
      <NavLink
        key={item.id}
        to={item.path}
        className={cn(
          'flex items-center rounded-md transition-colors duration-150',
          'h-10',
          sidebarCollapsed ? 'justify-center px-0' : 'gap-3 px-3',
          active
            ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
            : 'text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground',
        )}
        style={{ paddingLeft: sidebarCollapsed ? undefined : `${12 + depth * 16}px` }}
        title={sidebarCollapsed ? item.label : undefined}
      >
        <Icon size={18} className="shrink-0" />
        {!sidebarCollapsed && (
          <span className="text-sm truncate">{item.label}</span>
        )}
      </NavLink>
    )
  }

  // 有子菜单：渲染为可折叠按钮 + 子列表
  return (
    <div key={item.id}>
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'flex items-center rounded-md transition-colors duration-150 w-full',
          'h-10',
          sidebarCollapsed ? 'justify-center px-0' : 'gap-3 px-3',
          active
            ? 'text-sidebar-accent-foreground font-medium'
            : 'text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground',
        )}
        style={{ paddingLeft: sidebarCollapsed ? undefined : `${12 + depth * 16}px` }}
        title={sidebarCollapsed ? item.label : undefined}
      >
        <Icon size={18} className="shrink-0" />
        {!sidebarCollapsed && (
          <>
            <span className="text-sm truncate flex-1 text-left">{item.label}</span>
            {expanded ? (
              <ChevronDown size={14} className="shrink-0 opacity-60" />
            ) : (
              <ChevronRight size={14} className="shrink-0 opacity-60" />
            )}
          </>
        )}
      </button>
      {/* 子菜单：折叠状态时隐藏，sidebar 折叠时也隐藏 */}
      {expanded && !sidebarCollapsed && (
        <div className="mt-0.5">
          {item.children!.map((child) => (
            <NavItemRow
              key={child.id}
              item={child}
              depth={depth + 1}
              sidebarCollapsed={sidebarCollapsed}
              locationPath={locationPath}
              defaultExpanded={false}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function Sidebar() {
  const { sidebarCollapsed, sidebarWidth, setActiveNavId } = useAppStore()
  const config = useConfigStore((s) => s.config)
  const location = useLocation()

  // 从配置中解析默认账号信息
  const defaultKey = config?.default || 'main'
  const defaultAccount = config?.accounts?.[defaultKey]
  const accountName = defaultAccount?.name || defaultKey
  const author = defaultAccount?.author || ''

  // 同步当前路由到 activeNavId
  useEffect(() => {
    const currentItem = NAV_ITEMS.find((item) => {
      if (item.path === '/') return location.pathname === '/'
      // articles 导航仅匹配 /articles/new
      if (item.id === 'articles') return location.pathname === '/articles/new'
      // newspic 导航匹配 /newspic/new 和 /newspic/:id
      if (item.id === 'newspic') return location.pathname.startsWith('/newspic')
      return location.pathname.startsWith(item.path)
    })
    if (currentItem) {
      setActiveNavId(currentItem.id)
    }
  }, [location.pathname, setActiveNavId])

  return (
    <aside
      className={cn(
        'flex flex-col border-r bg-sidebar',
        'transition-[width] duration-200 ease-in-out',
        'overflow-hidden',
      )}
      style={{ width: sidebarWidth }}
    >
      {/* Logo 区 */}
      <div
        className={cn(
          'flex h-14 items-center border-b border-sidebar-border px-4',
          sidebarCollapsed ? 'justify-center' : 'gap-3',
        )}
      >
        <div
          className={cn(
            'flex items-center justify-center rounded-lg',
            'bg-sidebar-primary text-sidebar-primary-foreground',
            'size-8 shrink-0',
          )}
        >
          <Sparkles size={18} />
        </div>
        {!sidebarCollapsed && (
          <span className="text-sm font-semibold text-foreground truncate">
            WeFlow
          </span>
        )}
      </div>

      {/* 导航区 */}
      <nav className="flex-1 space-y-0.5 p-3 overflow-y-auto">
        {NAV_ITEMS.map((item) => (
          <NavItemRow
            key={item.id}
            item={item}
            depth={0}
            sidebarCollapsed={sidebarCollapsed}
            locationPath={location.pathname}
            defaultExpanded={false}
          />
        ))}
      </nav>

      {/* 底部：用户信息 —— 动态读取 config.yaml */}
      <div
        className={cn(
          'flex items-center border-t border-sidebar-border p-3',
          sidebarCollapsed ? 'justify-center' : 'gap-3',
        )}
      >
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-sidebar-accent text-sidebar-accent-foreground text-xs font-medium">
          {accountName ? accountName.charAt(0) : <User size={14} />}
        </div>
        {!sidebarCollapsed && (
          <div className="flex flex-col min-w-0">
            <span className="text-sm font-medium text-foreground truncate">
              {accountName}
            </span>
            <span className="text-xs text-sidebar-foreground truncate">
              {author ? `${defaultKey} (${author})` : defaultKey}
            </span>
          </div>
        )}
      </div>
    </aside>
  )
}
