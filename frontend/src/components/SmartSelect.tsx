/**
 * SmartSelect —— 自定义下拉框，支持 hover 预览（排版主题 / 配图风格）。
 * 提取自 Settings 页面，供 ArticleCreate、NewspicCreate 等共用。
 */
import { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown, X, AlertCircle } from 'lucide-react'

// ============================================================
// 类型
// ============================================================

export interface SmartOption {
  value: string
  label: string
  info?: string      // 选中后下方提示信息
  tooltip?: string   // hover 时的 title
}

export interface SmartSelectProps {
  /** 外层 label 文本 */
  label?: string
  /** 当前值 */
  value: string
  /** 选项列表 */
  options: SmartOption[]
  /** 占位文案 */
  placeholder?: string
  /** 值变更回调 */
  onChange: (v: string) => void
  /** 预览类型：theme → iframe 预览，image-style → 图片预览 */
  previewType?: 'theme' | 'image-style'
  /** 自定义 className（用于外层容器） */
  className?: string
}

// ============================================================
// PreviewPopover
// ============================================================

function PreviewPopover({
  previewRef, url, type, position, label, onClose, onMouseEnter, onMouseLeave,
}: {
  previewRef: React.RefObject<HTMLDivElement | null>
  url: string
  type: 'theme' | 'image-style'
  position: { top: number; left: number }
  label: string
  onClose: () => void
  onMouseEnter?: (e: React.MouseEvent) => void
  onMouseLeave?: (e: React.MouseEvent) => void
}) {
  const [imgError, setImgError] = useState(false)

  return createPortal(
    <div
      ref={previewRef}
      className="fixed z-[60] animate-in fade-in slide-in-from-top-1 duration-200"
      style={{ top: position.top, left: position.left }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="rounded-xl border border-border bg-card shadow-2xl ring-1 ring-black/5 overflow-hidden">
        {/* 标题栏 */}
        <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-border bg-muted/30">
          <span className="text-xs font-semibold text-foreground truncate max-w-[300px]">
            {type === 'theme' ? '🎨' : '🖼️'} {label}
          </span>
          <button
            onClick={onClose}
            className="shrink-0 p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="关闭预览"
          >
            <X size={14} />
          </button>
        </div>
        {/* 预览内容 */}
        <div className="p-3 bg-muted/10">
          {type === 'theme' ? (
            <iframe
              src={url}
              className="w-[500px] h-[380px] rounded-lg border border-border bg-white"
              title={label}
            />
          ) : imgError ? (
            <div className="w-[400px] h-[220px] rounded-lg border border-border bg-muted flex flex-col items-center justify-center gap-2 text-muted-foreground">
              <AlertCircle size={24} />
              <span className="text-xs">预览图加载失败</span>
            </div>
          ) : (
            <img
              src={url}
              alt={label}
              className="max-w-[400px] max-h-[320px] rounded-lg border border-border object-contain bg-white"
              onError={() => setImgError(true)}
            />
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}

// ============================================================
// SmartSelect
// ============================================================

export function SmartSelect({
  label, value, options, placeholder = '请选择...', onChange,
  previewType, className = '',
}: SmartSelectProps) {
  const selected = options.find(o => o.value === value)
  const containerRef = useRef<HTMLDivElement>(null)
  const previewRef = useRef<HTMLDivElement>(null)
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [open, setOpen] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [previewOpt, setPreviewOpt] = useState<{ value: string; label: string } | null>(null)
  const [previewPos, setPreviewPos] = useState({ top: 0, left: 0 })

  // 点击外部关闭下拉
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // 清理定时器
  useEffect(() => {
    return () => { if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current) }
  }, [])

  const handleSelect = (opt: SmartOption) => {
    onChange(opt.value)
    setOpen(false)
  }

  // hover 选项行 → 显示预览弹窗
  const handlePreviewEnter = (e: React.MouseEvent, opt: SmartOption) => {
    e.stopPropagation()
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    const el = e.currentTarget as HTMLElement
    const rect = el.getBoundingClientRect()
    const popupWidth = previewType === 'theme' ? 520 : 420
    const popupHeight = previewType === 'theme' ? 460 : 380
    let left = rect.right + 8
    if (left + popupWidth > window.innerWidth - 16) left = rect.left - popupWidth - 8
    if (left < 16) left = 16
    // 垂直方向：如果弹窗底部超出视口，则把弹窗底部对齐到视口底部以上
    let top = rect.top - 10
    if (top + popupHeight > window.innerHeight - 16) {
      top = window.innerHeight - popupHeight - 16
    }
    if (top < 8) top = 8
    setPreviewPos({ top, left })
    setPreviewOpt({ value: opt.value, label: opt.label })
    setShowPreview(true)
  }

  const handlePreviewLeave = (e: React.MouseEvent) => {
    // 如果鼠标仍在当前选项行内（移动到子元素），忽略
    if (e.currentTarget.contains(e.relatedTarget as Node)) return
    // 如果鼠标移入了预览弹窗，不关闭
    if (previewRef.current?.contains(e.relatedTarget as Node)) return
    // 延迟关闭，给用户时间移入弹窗
    hoverTimerRef.current = setTimeout(() => setShowPreview(false), 150)
  }

  const handlePopoverEnter = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
  }

  const closePreview = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    setShowPreview(false)
  }

  const previewUrl = previewOpt?.value
    ? previewType === 'theme'
      ? `/assets/theme-previews/${previewOpt.value}.html`
      : `/assets/image-styles/previews/${previewOpt.value}.webp`
    : null

  const selectButton = (
    <button
      type="button"
      onClick={() => setOpen(!open)}
      className="input flex items-center justify-between text-left"
    >
      <span className={selected ? 'text-foreground' : 'text-muted-foreground'}>
        {selected ? selected.label : placeholder}
      </span>
      <ChevronDown size={14} className={`shrink-0 ml-2 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} />
    </button>
  )

  const dropdown = open && (
    <div className="absolute z-50 top-full left-0 right-0 mt-1 max-h-60 overflow-y-auto rounded-lg border border-border bg-card shadow-overlay py-1">
      {/* 占位选项 */}
      <button
        type="button"
        onClick={() => { onChange(''); setOpen(false) }}
        className={`w-full text-left px-3 py-2 text-sm hover:bg-muted transition-colors ${!value ? 'text-primary font-medium' : 'text-muted-foreground'}`}
      >
        {placeholder}
      </button>
      {options.map(opt => (
        <div
          key={opt.value}
          onMouseEnter={previewType ? (e) => handlePreviewEnter(e, opt) : undefined}
          onMouseLeave={previewType ? handlePreviewLeave : undefined}
          className={`group flex items-center hover:bg-muted transition-colors ${opt.value === value ? 'bg-muted/50' : ''}`}
        >
          <button
            type="button"
            onClick={() => handleSelect(opt)}
            className={`flex-1 text-left px-3 py-2 text-sm truncate ${opt.value === value ? 'text-primary font-medium' : 'text-foreground'}`}
            title={opt.tooltip}
          >
            {opt.label}
          </button>
          {/* 预览图标 —— 仅在 hover 选项时显示 */}
          {previewType && (
            <span className="shrink-0 px-2 py-2 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground pointer-events-none">
              👁
            </span>
          )}
        </div>
      ))}
    </div>
  )

  const selectedInfo = selected && !open && selected.info && (
    <p className="mt-1 text-xs text-muted-foreground truncate">{selected.info}</p>
  )

  const previewPopover = showPreview && previewUrl && (
    <PreviewPopover
      previewRef={previewRef}
      url={previewUrl}
      type={previewType!}
      position={previewPos}
      label={previewOpt?.label || ''}
      onClose={closePreview}
      onMouseEnter={handlePopoverEnter}
      onMouseLeave={handlePreviewLeave}
    />
  )

  // 有 label → 水平布局（Settings 风格）
  if (label) {
    return (
      <label className={`flex items-center gap-3 ${className}`}>
        <span className="text-xs font-medium text-muted-foreground w-24 shrink-0">{label}</span>
        <div className="flex-1">
          <div className="relative" ref={containerRef}>
            {selectButton}
            {dropdown}
          </div>
          {selectedInfo}
          {previewPopover}
        </div>
      </label>
    )
  }

  // 无 label → 垂直布局（Article/Newspic 创建页风格）
  return (
    <div className={className}>
      <div className="relative" ref={containerRef}>
        {selectButton}
        {dropdown}
      </div>
      {selectedInfo}
      {previewPopover}
    </div>
  )
}
