/**
 * 图片审核卡片 —— 审核详情页 stage=60 使用。
 * 展示缩略图、元数据、可编辑 prompt，支持替换/重新生成。
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Upload, Sparkles, Loader2, X, Pencil, AlertTriangle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SmartSelect } from '@/components/SmartSelect'
import { getTaskImageUrl, updateTaskImage, getConfigConstants } from '@/lib/api'
import type { TaskImage } from '@/types/task'
import type { ImageStyleMeta } from '@/types/config'

// ============================================================
// 工具函数
// ============================================================

function formatBytes(bytes: number): string {
  if (!bytes) return '--'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** 图片占位图（待生成 / 生成失败） */
function ImagePlaceholder({ status }: { status: string }) {
  const isFailed = status === 'generate_failed'
  const bgColor = isFailed ? '#fef2f2' : '#f1f5f9'
  const accentColor = isFailed ? '#fecaca' : '#e2e8f0'
  const iconColor = isFailed ? '#ef4444' : '#94a3b8'
  const textColor = isFailed ? '#dc2626' : '#64748b'
  const label = isFailed ? '生图失败' : '待生成'

  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-1.5" style={{ background: bgColor }}>
      {/* 图片图标 */}
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="6" width="28" height="20" rx="3" stroke={iconColor} strokeWidth="1.5" fill={accentColor} />
        <circle cx="10.5" cy="13.5" r="2.5" fill={iconColor} opacity="0.4" />
        <path d="M4 22 L10 16 L15 20 L20 12 L28 22" stroke={iconColor} strokeWidth="1.5" strokeLinejoin="round" fill={iconColor} fillOpacity="0.15" />
      </svg>
      <span className="text-[11px] font-medium" style={{ color: textColor }}>{label}</span>
      {isFailed && (
        <span className="text-[10px] opacity-70" style={{ color: textColor }}>请检查生成日志</span>
      )}
    </div>
  )
}

/** upload_status → 显示标签 + 颜色 */
const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  generated:      { label: '已生成',   cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300' },
  generate_failed:{ label: '生图失败', cls: 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300' },
  pending:        { label: '待生成',   cls: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' },
  uploading:      { label: '上传中',   cls: 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300' },
  uploaded:       { label: '已上传',   cls: 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300' },
  failed:         { label: '上传失败', cls: 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300' },
  skipped:        { label: '已跳过',   cls: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400' },
}

function statusBadge(status: string) {
  const s = STATUS_MAP[status] || { label: status || '未知', cls: 'bg-gray-100 text-gray-600' }
  return (
    <span className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${s.cls}`}>
      {s.label}
    </span>
  )
}

// ============================================================
// Props
// ============================================================

export interface ImageReviewCardProps {
  image: TaskImage
  taskId: number
  /** 'article' | 'image'，用于过滤配图风格 */
  taskType: string
  /** 图片列表中是否有 is_cover=1 的记录 */
  hasCoverRecord: boolean
  onReplace: (file: File) => void
  onRegenerate: (prompt: string) => Promise<void>
  /** 刷新图片列表（重新生成后回调） */
  onRefresh: () => void
  disabled: boolean
  /** 是否显示操作按钮（替换/重新生成），默认 true */
  showActions?: boolean
  /** 重新生成按钮标签，默认 "重新生成" */
  regenerateLabel?: string
}

// ============================================================
// 组件
// ============================================================

export function ImageReviewCard({
  image,
  taskId,
  taskType,
  hasCoverRecord,
  onReplace,
  onRegenerate,
  onRefresh,
  disabled,
  showActions = true,
  regenerateLabel = '重新生成',
}: ImageReviewCardProps) {
  const imgUrl = getTaskImageUrl(taskId, image.local_path)
  const imgKeyRef = useRef(0)

  // inline prompt（供重新生成快速编辑）
  const [prompt, setPrompt] = useState(image.prompt || '')
  const [regenerating, setRegenerating] = useState(false)
  const [regenerateError, setRegenerateError] = useState<string | null>(null)
  const [showFullscreen, setShowFullscreen] = useState(false)
  const [showRegenConfirm, setShowRegenConfirm] = useState(false)
  const [regenConfirmPrompt, setRegenConfirmPrompt] = useState('')
  const [regenConfirmStyle, setRegenConfirmStyle] = useState('')
  const [regenConfirmSaving, setRegenConfirmSaving] = useState(false)
  const [regenConfirmError, setRegenConfirmError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── 当 image prop 变化时同步本地状态 ──
  useEffect(() => {
    setPrompt(image.prompt || '')
  }, [image.prompt, image.description, image.image_style])

  const [styles, setStyles] = useState<ImageStyleMeta[]>([])

  // 封面识别（仅 article 模式有封面概念，image/newspic 模式跳过）
  const isImageMode = taskType === 'image'
  const isStandaloneCover = !isImageMode && image.is_cover === 1
  const isFallbackCover = !isImageMode && !hasCoverRecord && image.seq === 1 && !isStandaloneCover

  // ── 操作 ──

  const handleReplace = () => fileInputRef.current?.click()

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    onReplace(file)
    imgKeyRef.current++
    e.target.value = ''
  }

  /** 点击"生成/重新生成"按钮 → 弹出确认窗口 */
  const handleRegenerate = useCallback(async () => {
    // 若 prompt 为空但有 description，自动用 description 作为初始 prompt
    const effective = prompt.trim() || (image.description || '').trim()
    if (!effective) {
      alert('Prompt 不能为空，请先输入生图提示词')
      return
    }
    setRegenerateError(null)
    setRegenConfirmPrompt(effective)
    setRegenConfirmStyle(image.image_style || '')
    setRegenConfirmError(null)
    setShowRegenConfirm(true)
    if (styles.length === 0) {
      try {
        const res = await getConfigConstants()
        if (res.data?.image_styles) {
          setStyles(res.data.image_styles)
        }
      } catch { /* 加载失败也不影响使用 */ }
    }
  }, [prompt, image.image_style, styles.length])

  /** 仅保存元数据（不重新生成） */
  const handleRegenSave = async () => {
    setRegenConfirmSaving(true)
    setRegenConfirmError(null)
    try {
      await updateTaskImage(taskId, image.id, {
        prompt: regenConfirmPrompt.trim() || undefined,
        image_style: regenConfirmStyle || undefined,
      })
      setPrompt(regenConfirmPrompt)
      setShowRegenConfirm(false)
      onRefresh()
    } catch (e) {
      setRegenConfirmError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setRegenConfirmSaving(false)
    }
  }

  /** 确认重新生成：保存元数据 + 重新生图 */
  const handleConfirmRegenerate = async () => {
    const trimmed = regenConfirmPrompt.trim()
    if (!trimmed) {
      setRegenConfirmError('Prompt 不能为空')
      return
    }

    // 先保存元数据（prompt + image_style）
    setRegenConfirmSaving(true)
    setRegenConfirmError(null)
    try {
      await updateTaskImage(taskId, image.id, {
        prompt: trimmed,
        image_style: regenConfirmStyle || undefined,
      })
      setPrompt(trimmed)
    } catch (e) {
      setRegenConfirmError(e instanceof Error ? e.message : '保存失败')
      setRegenConfirmSaving(false)
      return
    }
    setRegenConfirmSaving(false)

    // 再重新生图
    setShowRegenConfirm(false)
    setRegenerating(true)
    setRegenerateError(null)
    try {
      console.log('[ImageReviewCard] 开始重新生成:', { taskId, imageId: image.id, prompt: trimmed })
      await onRegenerate(trimmed)
      imgKeyRef.current++
      onRefresh()
      console.log('[ImageReviewCard] 重新生成完成')
    } catch (e) {
      console.error('[ImageReviewCard] 重新生成失败:', e)
      setRegenerateError(e instanceof Error ? e.message : '生成失败')
    } finally {
      setRegenerating(false)
    }
  }

  // 配图风格选项（根据任务类型过滤）
  const styleOptions = styles
    .filter(s => taskType === 'image' ? s.for_newspic : s.for_news)
    .map(s => ({
      value: s.code,
      label: `${s.label} (${s.code})`,
      info: `${s.keywords} · ${s.topics}`,
      tooltip: `${s.keywords}\n${s.topics}\n密度: ${s.density}\ncode: ${s.code}`,
    }))

  const displayUrl = `${imgUrl}${imgUrl.includes('?') ? '&' : '?'}_v=${imgKeyRef.current}`

  // 判断图片是否已实际生成（可查看）
  const isPlaceholder = image.upload_status === 'pending' || image.upload_status === 'generate_failed' || !image.local_path
  const canView = !isPlaceholder

  return (
    <>
      {/* 卡片 */}
      <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm hover:shadow-md transition-shadow duration-200">
        {/* 缩略图区域 */}
        <div
          className={`relative aspect-[16/9] bg-muted overflow-hidden ${canView ? 'cursor-pointer group' : ''}`}
          onClick={() => canView && setShowFullscreen(true)}
        >
          {isPlaceholder ? (
            <ImagePlaceholder status={image.upload_status} />
          ) : (
            <>
              <img
                src={displayUrl}
                alt={image.description || `图片 ${image.seq}`}
                className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                onError={(e) => {
                  (e.target as HTMLImageElement).src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90"><rect fill="%23fef2f2" width="160" height="90"/><rect fill="%23fecaca" width="160" height="90" rx="4"/><text x="80" y="48" text-anchor="middle" fill="%23dc2626" font-size="12">加载失败</text></svg>'
                }}
              />
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors duration-200 flex items-center justify-center">
                <span className="text-white text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-black/40 rounded-full px-3 py-1">
                  点击放大
                </span>
              </div>
            </>
          )}

          {/* 封面徽章 */}
          {isStandaloneCover && (
            <span className="absolute top-2 left-2 inline-flex items-center gap-1 rounded-full bg-amber-500/90 text-white px-2 py-0.5 text-[10px] font-semibold shadow-sm">
              封面图
            </span>
          )}
          {isFallbackCover && (
            <span className="absolute top-2 left-2 inline-flex items-center gap-1 rounded-full bg-amber-400/60 text-amber-900 dark:text-amber-100 px-2 py-0.5 text-[10px] font-semibold shadow-sm">
              配图 · 同时作为封面
            </span>
          )}

          {/* 状态徽章（顶部居中偏左） */}
          <span className="absolute top-2 left-1/2 -translate-x-1/2">
            {statusBadge(image.upload_status)}
          </span>

          <span className="absolute top-2 right-2 bg-black/50 text-white rounded-full size-5 flex items-center justify-center text-[10px] font-mono">
            {image.seq}
          </span>
        </div>

        {/* 元数据区域 */}
        <div className="p-3 space-y-2.5">
          {/* 描述 */}
          {image.description && (
            <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
              {image.description}
            </p>
          )}

          {/* 封面文字提示（当同时作为封面时） */}
          {isFallbackCover && (
            <p className="text-[10px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 rounded px-2 py-1">
              ⚠️ 此图片是第 1 张配图，发布时将作为封面使用
            </p>
          )}

          {/* 生图参数标签 */}
          <div className="flex flex-wrap gap-1.5">
            {image.provider && (
              <code className="text-[10px] bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300 rounded px-1.5 py-0.5 font-mono">
                {image.provider}
              </code>
            )}
            {image.model && (
              <code className="text-[10px] bg-purple-50 text-purple-700 dark:bg-purple-950 dark:text-purple-300 rounded px-1.5 py-0.5 font-mono truncate max-w-[120px]">
                {image.model}
              </code>
            )}
            {image.image_style && (
              <code className="text-[10px] bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300 rounded px-1.5 py-0.5 font-mono">
                {image.image_style}
              </code>
            )}
            {image.width > 0 && image.height > 0 && (
              <code className="text-[10px] bg-muted text-muted-foreground rounded px-1.5 py-0.5 font-mono">
                {image.width}×{image.height}
              </code>
            )}
            {image.local_size > 0 && (
              <code className="text-[10px] bg-muted text-muted-foreground rounded px-1.5 py-0.5 font-mono">
                {formatBytes(image.local_size)}
              </code>
            )}
          </div>

          {/* Prompt 快速编辑区 */}
          <div>
            <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
              Prompt
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={3}
              disabled={disabled || regenerating}
              className="w-full rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-mono
                         placeholder:text-muted-foreground/40 resize-none
                         focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50
                         disabled:opacity-50 disabled:cursor-not-allowed
                         transition-all"
              placeholder="输入生图提示词..."
            />
          </div>

          {regenerateError && (
            <p className="text-xs text-red-500 bg-red-50 dark:bg-red-950/30 rounded px-2 py-1">
              {regenerateError}
            </p>
          )}

          {/* 操作按钮（仅 showActions=true 时可见） */}
          {showActions && (
            <div className="flex items-center gap-1.5 pt-1 border-t border-border/50 flex-wrap">
              <Button
                variant="ghost"
                size="sm"
                disabled={disabled}
                onClick={handleReplace}
                className="h-7 px-2 text-xs text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-950/30 gap-1"
              >
                <Upload size={12} />
                替换
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={handleFileChange}
                className="hidden"
              />

              <Button
                variant="ghost"
                size="sm"
                disabled={disabled || regenerating || (!prompt.trim() && !image.description?.trim())}
                onClick={handleRegenerate}
                className="h-7 px-2 text-xs text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 gap-1"
              >
                {regenerating ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Sparkles size={12} />
                )}
                {regenerateLabel}</Button>
            </div>
          )}
        </div>
      </div>

      {/* 重新生成确认弹窗 */}
      {showRegenConfirm && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 backdrop-blur-sm overflow-y-auto py-10" onClick={() => setShowRegenConfirm(false)}>
          <div
            className="bg-card rounded-2xl border border-border shadow-2xl max-w-lg w-full mx-4 overflow-visible"
            onClick={e => e.stopPropagation()}
          >
            <div className="bg-gradient-to-r from-emerald-500 to-emerald-600 px-6 py-4 rounded-t-2xl">
              <div className="flex items-center gap-3">
                <div className="size-10 rounded-xl bg-white/20 flex items-center justify-center">
                  <Sparkles size={20} className="text-white" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white">重新生成 · 图片 #{image.seq}</h3>
                  <p className="text-sm text-emerald-100/80">可修改 Prompt 和配图风格后重新生成</p>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-4">
              {/* 只读参数表 */}
              <div className="rounded-lg border border-border bg-muted/30 overflow-hidden">
                <table className="w-full text-sm">
                  <tbody>
                    <tr className="border-b border-border">
                      <td className="px-3 py-2 text-muted-foreground whitespace-nowrap font-medium">图片序号</td>
                      <td className="px-3 py-2 text-foreground">#{image.seq}</td>
                    </tr>
                    {image.description && (
                      <tr className="border-b border-border">
                        <td className="px-3 py-2 text-muted-foreground whitespace-nowrap font-medium">描述</td>
                        <td className="px-3 py-2 text-foreground">{image.description}</td>
                      </tr>
                    )}
                    <tr className="border-b border-border">
                      <td className="px-3 py-2 text-muted-foreground whitespace-nowrap font-medium">生图提供商</td>
                      <td className="px-3 py-2">
                        <code className="text-xs bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300 rounded px-1.5 py-0.5 font-mono">
                          {image.provider || '(默认)'}
                        </code>
                      </td>
                    </tr>
                    <tr className="border-b border-border">
                      <td className="px-3 py-2 text-muted-foreground whitespace-nowrap font-medium">模型</td>
                      <td className="px-3 py-2">
                        <code className="text-xs bg-purple-50 text-purple-700 dark:bg-purple-950 dark:text-purple-300 rounded px-1.5 py-0.5 font-mono">
                          {image.model || '(默认)'}
                        </code>
                      </td>
                    </tr>
                    <tr className="border-b border-border">
                      <td className="px-3 py-2 text-muted-foreground whitespace-nowrap font-medium">尺寸</td>
                      <td className="px-3 py-2">
                        <code className="text-xs bg-muted text-muted-foreground rounded px-1.5 py-0.5 font-mono">
                          {image.size || '默认'}
                        </code>
                      </td>
                    </tr>
                    <tr>
                      <td className="px-3 py-2 text-muted-foreground whitespace-nowrap font-medium">质量</td>
                      <td className="px-3 py-2 text-foreground">normal</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* 可编辑：配图风格 */}
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  配图风格 <span className="text-muted-foreground font-normal">(image_style)</span>
                </label>
                {styleOptions.length > 0 ? (
                  <SmartSelect
                    value={regenConfirmStyle}
                    options={styleOptions}
                    placeholder="保持现有风格"
                    onChange={v => setRegenConfirmStyle(v)}
                    previewType="image-style"
                  />
                ) : (
                  <input
                    value={regenConfirmStyle}
                    onChange={e => setRegenConfirmStyle(e.target.value)}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm
                               focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500/50
                               transition-all"
                    placeholder="输入风格标识..."
                  />
                )}
              </div>

              {/* 可编辑：Prompt */}
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  新的生图 Prompt <span className="text-muted-foreground font-normal">(可编辑)</span>
                </label>
                <textarea
                  value={regenConfirmPrompt}
                  onChange={e => setRegenConfirmPrompt(e.target.value)}
                  rows={5}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs font-mono
                             placeholder:text-muted-foreground/40 resize-none
                             focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500/50
                             transition-all"
                  placeholder="输入生图提示词..."
                />
              </div>

              {/* 错误提示 */}
              {regenConfirmError && (
                <div className="flex items-start gap-2 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 px-3 py-2">
                  <AlertTriangle size={14} className="text-red-500 shrink-0 mt-0.5" />
                  <p className="text-xs text-red-700 dark:text-red-300">{regenConfirmError}</p>
                </div>
              )}

              {/* 提示 */}
              <div className="flex items-start gap-2 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 px-3 py-2">
                <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" />
                <p className="text-xs text-amber-700 dark:text-amber-300">
                  AI 生图耗时约 2–10 秒，将覆盖当前图片文件。"保存并重新生成"会先保存元数据再调用 AI 生图。
                </p>
              </div>

              {/* 操作按钮 */}
              <div className="flex justify-end gap-3 pt-2 border-t border-border/50">
                <Button variant="outline" size="sm" onClick={() => setShowRegenConfirm(false)}>
                  取消
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRegenSave}
                  disabled={regenConfirmSaving}
                  className="text-violet-600 hover:text-violet-700 hover:bg-violet-50 dark:hover:bg-violet-950/30"
                >
                  {regenConfirmSaving ? (
                    <Loader2 size={14} className="animate-spin mr-1.5" />
                  ) : (
                    <Pencil size={14} className="mr-1.5" />
                  )}
                  保存
                </Button>
                <Button
                  size="sm"
                  onClick={handleConfirmRegenerate}
                  disabled={regenConfirmSaving || !regenConfirmPrompt.trim()}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm"
                >
                  <Sparkles size={14} className="mr-1.5" />
                  保存并重新生成
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 全屏预览 */}
      {showFullscreen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm" onClick={() => setShowFullscreen(false)}>
          <button
            onClick={() => setShowFullscreen(false)}
            className="absolute top-4 right-4 p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            <X size={24} />
          </button>
          <img
            src={displayUrl}
            alt={image.description || `图片 ${image.seq}`}
            className="max-w-[90vw] max-h-[90vh] object-contain rounded-xl shadow-2xl"
            onClick={e => e.stopPropagation()}
          />
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-3 bg-black/60 backdrop-blur rounded-full px-5 py-2.5 text-white/90 text-sm">
            <span className="font-medium">#{image.seq}</span>
            {image.description && (
              <>
                <span className="text-white/30">|</span>
                <span className="text-white/80">{image.description}</span>
              </>
            )}
            {image.width > 0 && image.height > 0 && (
              <>
                <span className="text-white/30">|</span>
                <span className="font-mono text-xs">{image.width}×{image.height}</span>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
