import { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Loader2, Palette, Image, Search, Eye, X, AlertCircle } from 'lucide-react'
import { getThemeStyles } from '@/lib/api'

// ============================================================
// 类型
// ============================================================
interface ThemeInfo {
  code: string
  label: string
  description: string
}

interface ImageStyleInfo {
  code: string
  label: string
  keywords: string
  topics: string
  density: string
}

type TabKey = 'themes' | 'styles'

// ============================================================
// 主题色条映射
// ============================================================
const THEME_PALETTE: Record<string, string[]> = {
  'refined-blue': ['#1e40af', '#3b82f6', '#60a5fa', '#93c5fd', '#dbeafe'],
  'warm-editorial': ['#8b4513', '#a0522d', '#cd853f', '#d2b48c', '#faf0e6'],
  'warm-orange': ['#c2410c', '#ea580c', '#f97316', '#fdba74', '#fff7ed'],
  'business-navy': ['#0f1a2e', '#1e3a5f', '#c9a84c', '#e8d48b', '#f0f4f8'],
  'elegant-ink': ['#1a1a1a', '#8b0000', '#c41e3a', '#d4af37', '#faf8f5'],
  'girly-pink': ['#be185d', '#db2777', '#ec4899', '#f9a8d4', '#fdf2f8'],
  'ink-wash': ['#2d1b00', '#5c3317', '#8b6914', '#d4c5a9', '#faf6f0'],
  'magazine-grid': ['#111111', '#333333', '#666666', '#cccccc', '#ffffff'],
  'minimal-bw': ['#000000', '#333333', '#888888', '#d4d4d4', '#ffffff'],
  'minimal-mono': ['#0a0a0a', '#1a1a1a', '#00ff41', '#333333', '#f0f0f0'],
  'mint-fresh': ['#0f766e', '#0d9488', '#14b8a6', '#5eead4', '#f0fdfa'],
  'news-bold': ['#991b1b', '#dc2626', '#1a1a1a', '#666666', '#fef2f2'],
  'sage-premium': ['#365314', '#4d7c0f', '#65a30d', '#bef264', '#f7fee7'],
}
const FALLBACK_PALETTE = ['#6b7280', '#9ca3af', '#b0b7c3', '#d1d5db', '#f3f4f6']

// ============================================================
// 悬浮预览弹窗（Portal）
// ============================================================
function ThemePreview({ url, type, position, label, onClose, onMouseEnter, onMouseLeave }: {
  url: string
  type: 'theme' | 'image-style'
  position: { top: number; left: number }
  label: string
  onClose: () => void
  onMouseEnter?: (e: React.MouseEvent) => void
  onMouseLeave?: (e: React.MouseEvent) => void
}) {
  const [imgError, setImgError] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  return createPortal(
    <div
      ref={ref}
      className="fixed z-[60] animate-in fade-in slide-in-from-top-1 duration-200"
      style={{ top: position.top, left: position.left }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="rounded-xl border border-border bg-card shadow-2xl ring-1 ring-black/5 overflow-hidden">
        <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-border bg-muted/30">
          <span className="text-xs font-semibold text-foreground truncate max-w-[300px]">
            {type === 'theme' ? '🎨' : '🖼️'} {label}
          </span>
          <button
            onClick={onClose}
            className="shrink-0 p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          >
            <X size={14} />
          </button>
        </div>
        <div className="p-3 bg-muted/10">
          {type === 'theme' ? (
            <iframe src={url} className="w-[500px] h-[380px] rounded-lg border border-border bg-white" title={label} />
          ) : imgError ? (
            <div className="w-[400px] h-[220px] rounded-lg border border-border bg-muted flex flex-col items-center justify-center gap-2 text-muted-foreground">
              <AlertCircle size={24} />
              <span className="text-xs">预览图加载失败</span>
            </div>
          ) : (
            <img src={url} alt={label} className="max-w-[400px] max-h-[320px] rounded-lg border border-border object-contain bg-white" onError={() => setImgError(true)} />
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}

// ============================================================
// 密度徽章
// ============================================================
function DensityBadge({ density }: { density: string }) {
  const cls =
    density === '高'
      ? 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-800'
      : density === '低'
        ? 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800'
        : 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800'
  return (
    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${cls}`}>
      {density}密度
    </span>
  )
}

// ============================================================
// 主页
// ============================================================
export function Themes() {
  const [tab, setTab] = useState<TabKey>('themes')
  const [themes, setThemes] = useState<ThemeInfo[]>([])
  const [styles, setStyles] = useState<ImageStyleInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  // 悬浮预览状态
  const [hoverPreview, setHoverPreview] = useState<{
    type: 'theme' | 'image-style'; code: string; label: string; pos: { top: number; left: number }
  } | null>(null)
  const previewTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const openPreview = (e: React.MouseEvent, type: 'theme' | 'image-style', code: string, label: string) => {
    if (previewTimerRef.current) clearTimeout(previewTimerRef.current)
    const el = e.currentTarget as HTMLElement
    const rect = el.getBoundingClientRect()
    const popupWidth = type === 'theme' ? 530 : 430
    const popupHeight = type === 'theme' ? 460 : 380
    let left = rect.right + 8
    if (left + popupWidth > window.innerWidth - 16) left = rect.left - popupWidth - 8
    if (left < 16) left = 16
    // 垂直方向：如果弹窗底部超出视口，则把弹窗底部对齐到视口底部以上
    let top = rect.top - 10
    if (top + popupHeight > window.innerHeight - 16) {
      top = window.innerHeight - popupHeight - 16
    }
    if (top < 8) top = 8
    setHoverPreview({ type, code, label, pos: { top, left } })
  }

  const handleCardLeave = (e: React.MouseEvent) => {
    // 如果鼠标仍在卡片内（移动到子元素），忽略
    if (e.currentTarget.contains(e.relatedTarget as Node)) return
    closePreview()
  }

  const closePreview = () => {
    previewTimerRef.current = setTimeout(() => setHoverPreview(null), 150)
  }

  const cancelCloseTimer = () => {
    if (previewTimerRef.current) clearTimeout(previewTimerRef.current)
  }

  useEffect(() => {
    setLoading(true)
    getThemeStyles()
      .then((res) => {
        if (res.data) {
          setThemes(res.data.themes || [])
          setStyles(res.data.image_styles || [])
        } else {
          setError(res.message || '加载失败')
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [])

  // 搜索过滤
  const filterThemes = (list: ThemeInfo[]) =>
    search
      ? list.filter((t) => t.label.includes(search) || t.description.includes(search) || t.code.includes(search))
      : list

  const filterStyles = (list: ImageStyleInfo[]) =>
    search
      ? list.filter((s) => s.label.includes(search) || s.keywords.includes(search) || s.topics.includes(search) || s.code.includes(search))
      : list

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div>
        <h2 className="text-page-title text-foreground">主题 & 风格</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          浏览排版主题与配图风格，点击预览查看效果
        </p>
      </div>

      {/* TAB 切换 + 搜索 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center rounded-lg border bg-muted/30 p-0.5">
          <button
            onClick={() => setTab('themes')}
            className={`flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium transition-all ${
              tab === 'themes'
                ? 'bg-background text-foreground shadow-sm border border-border'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Palette size={15} />
            排版主题
            <span className="ml-1 text-xs opacity-60">({themes.length})</span>
          </button>
          <button
            onClick={() => setTab('styles')}
            className={`flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium transition-all ${
              tab === 'styles'
                ? 'bg-background text-foreground shadow-sm border border-border'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Image size={15} />
            图片风格
            <span className="ml-1 text-xs opacity-60">({styles.length})</span>
          </button>
        </div>
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索..."
            className="w-56 rounded-md border bg-background pl-9 pr-3 py-2 text-sm
              placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
      </div>

      {/* 加载 */}
      {loading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 size={24} className="animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">加载中...</span>
        </div>
      )}

      {/* 错误 */}
      {!loading && error && (
        <div className="flex flex-col items-center justify-center py-24 gap-3">
          <div className="rounded-full bg-destructive/10 p-4">
            <X size={24} className="text-destructive" />
          </div>
          <p className="text-sm text-muted-foreground">{error}</p>
        </div>
      )}

      {/* ================================================================ */}
      {/* 排版主题 */}
      {/* ================================================================ */}
      {!loading && !error && tab === 'themes' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filterThemes(themes).map((theme) => {
            const colors = THEME_PALETTE[theme.code] || FALLBACK_PALETTE
            return (
              <div
                key={theme.code}
                onMouseEnter={e => openPreview(e, 'theme', theme.code, theme.label)}
                onMouseLeave={handleCardLeave}
                className="group rounded-xl border bg-card hover:shadow-lg hover:border-primary/30 transition-all duration-200 overflow-hidden cursor-pointer"
              >
                {/* 色条 */}
                <div className="flex h-1.5">
                  {colors.map((c, i) => (
                    <div key={i} className="flex-1" style={{ backgroundColor: c }} />
                  ))}
                </div>

                <div className="p-4 space-y-2.5">
                  {/* 标题行：标签 + code */}
                  <div className="flex items-start gap-2">
                    <h3 className="flex-1 min-w-0 text-sm font-semibold text-foreground leading-tight">
                      {theme.label}
                    </h3>
                    <span className="shrink-0 text-[10px] font-mono text-muted-foreground/50 mt-0.5">
                      {theme.code}
                    </span>
                    <Eye size={12} className="shrink-0 text-muted-foreground/30 group-hover:text-primary/60 transition-colors mt-0.5" />
                  </div>

                  {/* 描述 */}
                  <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                    {theme.description}
                  </p>
                </div>
              </div>
            )
          })}
          {filterThemes(themes).length === 0 && (
            <div className="col-span-full py-16 text-center text-sm text-muted-foreground">
              {search ? '没有匹配的主题' : '暂无主题'}
            </div>
          )}
        </div>
      )}

      {/* ================================================================ */}
      {/* 图片风格 */}
      {/* ================================================================ */}
      {!loading && !error && tab === 'styles' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filterStyles(styles).map((style) => (
            <div
              key={style.code}
              onMouseEnter={e => openPreview(e, 'image-style', style.code, style.label)}
              onMouseLeave={handleCardLeave}
              className="group rounded-xl border bg-card hover:shadow-lg hover:border-primary/30 transition-all duration-200 overflow-hidden cursor-pointer"
            >
              <div className="p-4 space-y-2.5">
                {/* 标题行：标签 + 密度 */}
                <div className="flex items-start gap-2">
                  <h3 className="flex-1 min-w-0 text-sm font-semibold text-foreground leading-tight">
                    {style.label}
                  </h3>
                  <DensityBadge density={style.density} />
                  <Eye size={12} className="shrink-0 text-muted-foreground/30 group-hover:text-primary/60 transition-colors mt-0.5" />
                </div>

                {/* code */}
                <p className="text-[10px] font-mono text-muted-foreground/50 truncate">{style.code}</p>

                {/* 关键词 */}
                <div className="flex flex-wrap gap-1">
                  {style.keywords.split(/[、,+，／ ]/).filter(Boolean).slice(0, 5).map((w, i) => (
                    <span
                      key={i}
                      className="rounded-full border bg-secondary/60 px-2 py-0.5 text-[10px] text-muted-foreground"
                    >
                      {w}
                    </span>
                  ))}
                </div>

                {/* 适用话题 */}
                <p className="text-[11px] text-muted-foreground/70 leading-relaxed line-clamp-2">
                  <span className="font-medium">适用话题：</span>
                  {style.topics}
                </p>
              </div>
            </div>
          ))}
          {filterStyles(styles).length === 0 && (
            <div className="col-span-full py-16 text-center text-sm text-muted-foreground">
              {search ? '没有匹配的风格' : '暂无风格'}
            </div>
          )}
        </div>
      )}

      {/* ================================================================ */}
      {/* 悬浮预览弹窗 */}
      {/* ================================================================ */}
      {hoverPreview && (
        <ThemePreview
          url={hoverPreview.type === 'theme'
            ? `/assets/theme-previews/${hoverPreview.code}.html`
            : `/assets/image-styles/previews/${hoverPreview.code}.webp`}
          type={hoverPreview.type}
          position={hoverPreview.pos}
          label={hoverPreview.label}
          onClose={closePreview}
          onMouseEnter={cancelCloseTimer}
          onMouseLeave={(e) => {
            if (e.currentTarget.contains(e.relatedTarget as Node)) return
            closePreview()
          }}
        />
      )}
    </div>
  )
}
