import React, { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Loader2, XCircle, RotateCw, History, RefreshCw,
  FileText, Image, FileUp, Activity, Eye, FileCheck, Clock, ExternalLink,
  CheckCircle, AlertTriangle, Info, FileCode, Save,
  ClipboardCheck, Plus,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getTask, getConfigConstants, getRetryInfo, retryTask, updateTaskBrief, replaceTaskImage, regenerateTaskImage, appendTaskImages } from '@/lib/api'
import { TiptapEditor } from 'shadcn-tiptap-editor'
import type { ConfigConstants } from '@/types/config'
import { STATUS_LABELS } from '@/lib/constants'
import type { TaskDetail as TaskDetailType, TaskStatusHistory, RetryInfo } from '@/types/task'
import { MarkdownViewer } from '@/components/common/MarkdownViewer'
import { ImageReviewCard } from '@/components/common/ImageReviewCard'

// ============================================================
// 格式化工具
// ============================================================

function formatTime(ts: number): string {
  if (!ts) return '--'
  const d = new Date(ts * 1000)
  return d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function formatDuration(seconds: number): string {
  if (seconds <= 0) return '--'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}h${m}m${s}s`
  if (m > 0) return `${m}m${s}s`
  return `${s}s`
}

// ============================================================
// Tab 定义
// ============================================================

const NEWS_TABS = [
  { key: 'info', label: '基础信息', icon: Info },
  { key: 'brief', label: '选题简报', icon: FileText },
  { key: 'article', label: '文章内容', icon: FileCheck },
  { key: 'images', label: '文章配图', icon: Image },
  { key: 'ai', label: 'AI检测', icon: Activity },
  { key: 'preview', label: '文章预览', icon: Eye },
] as const

const NEWSPIC_TABS = [
  { key: 'info', label: '基础信息', icon: Info },
  { key: 'brief', label: '选题简报', icon: FileText },
  { key: 'images', label: '文章配图', icon: Image },
  { key: 'ai', label: 'AI检测', icon: Activity },
] as const

type TabKey = typeof NEWS_TABS[number]['key'] | typeof NEWSPIC_TABS[number]['key']

// ============================================================
// 页面入口
// ============================================================

export function TaskDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const taskId = Number(id)

  const [task, setTask] = useState<TaskDetailType | null>(null)
  const [constants, setConstants] = useState<ConfigConstants | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('info')

  // 重试
  const [retryInfo, setRetryInfo] = useState<RetryInfo | null>(null)
  const [retrying, setRetrying] = useState(false)
  const [showRetryConfirm, setShowRetryConfirm] = useState(false)

  const load = useCallback(async () => {
    if (!taskId) return
    setLoading(true)
    setError(null)
    try {
      const res = await getTask(taskId)
      if (res.data) setTask(res.data)
      else setError('任务不存在')
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [taskId])

  useEffect(() => { load() }, [load])

  // 加载常量（用于 label 映射）
  useEffect(() => {
    getConfigConstants().then(res => { if (res.data) setConstants(res.data) }).catch(() => {})
  }, [])

  // 加载重试信息（失败状态时）
  useEffect(() => {
    if (!task || !taskId) return
    const retryableStatuses = [0, 85, 88]
    if (retryableStatuses.includes(task.status)) {
      getRetryInfo(taskId)
        .then(res => { if (res.data) setRetryInfo(res.data) })
        .catch(() => setRetryInfo(null))
    } else {
      setRetryInfo(null)
    }
  }, [task, taskId])

  // 自动轮询：中间态快轮询（3s），待审核时不轮询（等人操作），
  // 但页面重新可见时刷新一次（审核可能在 ReviewDetail 页通过）
  useEffect(() => {
    if (!task) return
    const isIntermediate = task.status >= 10 && task.status < 90
    if (!isIntermediate) return

    const hasPendingReview = task.review_records?.some(r => r.status === 'pending')
    if (hasPendingReview) {
      // 待审核不轮询，但页面可见时刷新
      const onVisible = () => { if (document.visibilityState === 'visible') load() }
      document.addEventListener('visibilitychange', onVisible)
      return () => document.removeEventListener('visibilitychange', onVisible)
    }

    const timer = setInterval(load, 3000)
    return () => clearInterval(timer)
  }, [task, load])

  // --- 加载态 ---
  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="animate-spin text-muted-foreground" size={28} />
      </div>
    )
  }

  if (error || !task) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3">
        <XCircle size={40} className="text-destructive" />
        <p className="text-sm text-muted-foreground">{error || '无法加载任务'}</p>
        <Button variant="outline" size="sm" onClick={load}>
          <RotateCw size={14} /> 重试
        </Button>
      </div>
    )
  }

  const isNewspic = task.type === 'image'
  const isMd = task.type === 'md'
  const tabs = isNewspic ? NEWSPIC_TABS : NEWS_TABS
  const statusLabel = STATUS_LABELS[task.status] || `状态 ${task.status}`
  // 是否有待审核记录
  const pendingReview = task.review_records?.find(r => r.status === 'pending')
  // 中间态（10-70）且无待审核 → pipeline 运行中
  const isRunning = task.status >= 10 && task.status <= 70 && !pendingReview

  return (
    <div className="space-y-4 pb-8">
      {/* 顶栏 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/tasks')}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <h2 className="text-page-title text-foreground">{task.topic}</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              任务 #{task.id} · {task.account} · {isNewspic ? '贴图消息 (image)' : isMd ? '去味发布 (md)' : '图文消息 (article)'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* 模式徽章 */}
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium border ${
            isNewspic
              ? 'bg-purple-50 border-purple-200 text-purple-700 dark:bg-purple-950 dark:border-purple-800 dark:text-purple-300'
              : isMd
                ? 'bg-amber-50 border-amber-200 text-amber-700 dark:bg-amber-950 dark:border-amber-800 dark:text-amber-300'
                : 'bg-sky-50 border-sky-200 text-sky-700 dark:bg-sky-950 dark:border-sky-800 dark:text-sky-300'
          }`}>
            {isNewspic ? <Image size={12} /> : isMd ? <FileUp size={12} /> : <FileText size={12} />}
            {isNewspic ? '贴图消息' : isMd ? '去味发布' : '图文消息'}
          </span>
          {/* 状态徽章 */}
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
            task.status === 0 ? 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300' :
            isRunning ? 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300' :
            pendingReview ? 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300' :
            task.status === 80 || task.status === 90 ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300' :
            task.status === 85 ? 'bg-yellow-50 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300' :
            task.status === 88 ? 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300' :
            'bg-muted text-muted-foreground'
          }`}>
            {isRunning ? (
              <Loader2 size={12} className="animate-spin" />
            ) : pendingReview ? (
              <Clock size={12} />
            ) : task.status === 0 || task.status === 88 ? (
              <AlertTriangle size={12} />
            ) : task.status === 85 ? (
              <AlertTriangle size={12} />
            ) : (
              <CheckCircle size={12} />
            )}
            {isRunning ? '运行中' : statusLabel}
          </span>
          {/* 审核中标记 —— 点击跳转审核页面 */}
          {pendingReview && (
            <button
              onClick={() => navigate(`/review/${pendingReview.id}`)}
              className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium
                         bg-amber-50 text-amber-700 hover:bg-amber-100
                         dark:bg-amber-950 dark:text-amber-300 dark:hover:bg-amber-900
                         transition-colors cursor-pointer"
              title="前往审核页面"
            >
              <ClipboardCheck size={12} />
              审核中
              <ExternalLink size={10} />
            </button>
          )}
          {/* 预览发布链接（已发布时显示） */}
          {task.status === 90 && task.publish_records?.some(r => r.url) && (
            <button
              onClick={() => {
                const url = task.publish_records?.find(r => r.url)?.url
                if (url) window.open(url, '_blank', 'noopener')
              }}
              className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium
                         bg-emerald-50 text-emerald-700 hover:bg-emerald-100
                         dark:bg-emerald-950 dark:text-emerald-300 dark:hover:bg-emerald-900
                         transition-colors cursor-pointer"
              title="在新窗口预览发布文章"
            >
              <ExternalLink size={12} />
              <span className="hidden sm:inline">预览</span>
            </button>
          )}
          {/* 重试按钮（仅可重试状态显示） */}
          {retryInfo?.retryable && (
            <Button
              variant={task.status === 88 ? 'default' : 'outline'}
              size="sm"
              onClick={() => setShowRetryConfirm(true)}
              disabled={retrying}
            >
              {retrying ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RotateCw size={14} />
              )}
              <span className="ml-1.5 hidden sm:inline">
                {task.status === 88 ? '重新发布' : task.status === 85 ? '重新生成' : '断点重试'}
              </span>
            </Button>
          )}
          {/* 同步到其他平台（仅已完成状态的任务显示） */}
          {[60, 70, 80, 85, 88, 90].includes(task.status) && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/sync/new?taskId=${task.id}`)}
              title="同步到其他平台"
            >
              <RefreshCw size={14} />
              <span className="ml-1.5 hidden sm:inline">同步其他平台</span>
            </Button>
          )}
          {/* 刷新页面（不显示在已发布和出错状态） */}
          {task.status !== 0 && task.status !== 88 && task.status !== 90 && (
            <Button variant="outline" size="sm" onClick={load} title="刷新任务数据">
              <History size={14} />
              <span className="ml-1.5 hidden sm:inline">刷新页面</span>
            </Button>
          )}
        </div>
      </div>

      {/* 两栏布局 */}
      <div className="flex gap-6">
        {/* 左侧 —— 时间线 */}
        <div className="w-64 shrink-0">
          <h3 className="text-sm font-medium text-foreground mb-3 flex items-center gap-1.5">
            <Clock size={15} /> 流程时间线
          </h3>
          <StatusTimeline history={task.status_history} currentStatus={task.status} />
        </div>

        {/* 右侧 —— Tab 内容 */}
        <div className="flex-1 min-w-0">
          {/* Tab 导航 */}
          <div className="flex gap-1 border-b border-border mb-4">
            {tabs.map(tab => {
              const Icon = tab.icon
              const active = tab.key === activeTab
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition-colors -mb-[1px] ${
                    active
                      ? 'border-primary text-primary'
                      : 'border-transparent text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Icon size={15} />
                  {tab.label}
                </button>
              )
            })}
          </div>

          {/* Tab 内容 */}
          <div className="min-h-[400px]">
            {activeTab === 'info' && <InfoTab task={task} constants={constants} />}
            {activeTab === 'brief' && <BriefTab task={task} onSaved={load} />}
            {activeTab === 'article' && <ArticleTab content={task.markdown} />}
            {activeTab === 'images' && (
              <ImagesTab
                images={task.images}
                taskId={task.id}
                taskType={task.type}
                showActions={task.status < 90 && !isRunning}
                onRefresh={load}
              />
            )}
            {activeTab === 'ai' && <AIScoreTab history={task.status_history} />}
            {activeTab === 'preview' && <PreviewTab html={task.html} />}
          </div>
        </div>
      </div>

      {/* 重试确认弹窗 */}
      {showRetryConfirm && retryInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowRetryConfirm(false)}>
          <div className="bg-card rounded-xl border border-border shadow-xl max-w-md w-full mx-4 p-6 space-y-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-start gap-3">
              <div className={`size-10 rounded-full flex items-center justify-center shrink-0 ${
                task.status === 88 ? 'bg-yellow-100 text-yellow-600' :
                task.status === 85 ? 'bg-orange-100 text-orange-600' :
                'bg-red-100 text-red-600'
              }`}>
                <RotateCw size={20} />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-lg font-semibold text-foreground">
                  确认{retryInfo.action_label}
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                  {retryInfo.description}
                </p>
                <div className="mt-3 p-3 rounded-lg bg-muted/50 border border-border space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">当前状态</span>
                    <span className="font-medium text-destructive">{retryInfo.current_status_label}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">重试起点</span>
                    <span className="font-medium">{retryInfo.retry_from_label}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">预估成本</span>
                    <span className="font-medium text-emerald-600">{retryInfo.cost_hint}</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowRetryConfirm(false)}>
                取消
              </Button>
              <Button
                size="sm"
                onClick={async () => {
                  setRetrying(true)
                  setShowRetryConfirm(false)
                  try {
                    await retryTask(taskId)
                    await load()
                  } catch (e) {
                    alert(e instanceof Error ? e.message : '重试失败')
                  } finally {
                    setRetrying(false)
                  }
                }}
              >
                确认重试
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================
// 状态时间线
// ============================================================

function StatusTimeline({ history, currentStatus }: { history: TaskStatusHistory[]; currentStatus: number }) {
  if (!history || history.length === 0) {
    return <p className="text-xs text-muted-foreground">暂无状态记录</p>
  }

  return (
    <div className="space-y-0">
      {history.map((item, i) => {
        const isLast = i === history.length - 1
        const isActive = item.to_status === currentStatus
        const isFailed = item.to_status === 85
        const isPublishFailed = item.to_status === 88
        const isAbandoned = item.to_status === 0
        const isPassed = item.to_status === 80

        return (
          <div key={item.id} className="flex gap-2">
            {/* 时间线竖线 + 圆点 */}
            <div className="flex flex-col items-center">
              <div className={`size-2.5 rounded-full border-2 shrink-0 mt-1 ${
                isAbandoned ? 'border-red-500 bg-red-200 dark:bg-red-800' :
                isPublishFailed ? 'border-red-500 bg-red-100 dark:bg-red-900' :
                isFailed ? 'border-red-500 bg-red-100 dark:bg-red-900' :
                isPassed ? 'border-emerald-500 bg-emerald-100 dark:bg-emerald-900' :
                isActive ? 'border-primary bg-primary/20' :
                'border-muted-foreground/30 bg-muted'
              }`} />
              {!isLast && <div className="w-px flex-1 bg-border min-h-[8px]" />}
            </div>
            {/* 内容 */}
            <div className={`pb-3 flex-1 min-w-0 ${isLast ? '' : ''}`}>
              <div className={`text-xs font-medium ${
                isAbandoned || isPublishFailed ? 'text-destructive' :
                isActive ? 'text-foreground' :
                'text-muted-foreground'
              }`}>
                {item.to_label || STATUS_LABELS[item.to_status] || `状态 ${item.to_status}`}
              </div>
              <p className="text-[10px] text-muted-foreground mt-0.5">
                {formatTime(item.created_at)}
                {item.duration_s > 0 && <span className="ml-2">耗时 {formatDuration(item.duration_s)}</span>}
              </p>
              {item.to_info && (
                <p className={`text-[10px] mt-0.5 whitespace-pre-wrap break-all ${isAbandoned ? 'text-destructive/80' : 'text-muted-foreground/70'}`}>{item.to_info}</p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ============================================================
// Tab 面板
// ============================================================

/** 基础信息 */
function InfoTab({ task, constants }: { task: TaskDetailType; constants: ConfigConstants | null }) {
  // 根据 code 查找 label
  const label = (type: 'themes' | 'image_styles' | 'article_structures' | 'opening_hooks', code: string | undefined) => {
    if (!code || !constants) return null
    const list = constants[type] as { code: string; label: string }[] | undefined
    const item = list?.find((i: { code: string; label: string }) => i.code === code)
    return item ? `${item.label} (${code})` : code
  }

  const statusColor = task.status >= 80 ? 'from-emerald-400 to-emerald-600' :
    task.status === 85 ? 'from-yellow-400 to-yellow-600' :
    task.status === 0 ? 'from-red-400 to-red-600' :
    'from-blue-400 to-blue-600'

  const isNewspic = task.type === 'image'
  const isMd = task.type === 'md'

  // 常规信息项（一行两列）
  const gridItems = [
    { label: '话题', value: task.topic },
    { label: '标题', value: task.title || '(未生成)' },
    { label: '类型', value: isNewspic ? '贴图消息' : isMd ? '去味发布' : '图文消息',
      extra: <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${isNewspic ? 'bg-purple-50 text-purple-600 dark:bg-purple-950 dark:text-purple-300' : isMd ? 'bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-300' : 'bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-300'}`}>{isNewspic ? 'image' : isMd ? 'md' : 'article'}</span> },
    { label: '账号名称', value: task.account_name || task.account },
    { label: '账号标识', value: task.account },
    { label: '作者', value: task.author || '--' },
    { label: '排版主题', value: label('themes', task.theme) || 'AI自动' },
    { label: '配图风格', value: label('image_styles', task.image_style) || 'AI自动' },
    ...(isNewspic ? [
      { label: '短文本', value: task.short_text || '(无)', fullWidth: true },
      { label: '文章体裁', value: task.genre || 'AI自动' },
    ] : [
      { label: '文章结构', value: label('article_structures', task.article_structure) || 'AI自动' },
      { label: '开篇钩子', value: label('opening_hooks', task.opening_hook) || 'AI自动' },
      { label: '文章体裁', value: task.genre || 'AI自动' },
    ]),
    { label: '语气风格', value: task.voice || 'AI自动' },
    { label: '字数', value: task.word_count ? `${task.word_count.toLocaleString()} 字` : '--',
      extra: task.ai_score != null ? <span className={`text-xs font-mono font-medium ${task.ai_score > 45 ? 'text-destructive' : 'text-emerald-500'}`}>AI {task.ai_score}分</span> : null },
    ...(task.need_images === 0 ? [{ label: '是否需要配图', value: '否（跳过配图）' }] : []),
    ...(task.user_details ? [{ label: '用户要求或细节', value: task.user_details, fullWidth: true }] : []),
    { label: '同步平台', value: task.sync_platforms || '(未配置)' },
    { label: '创建时间', value: task.created_at ? new Date(task.created_at * 1000).toLocaleString('zh-CN') : '--' },
    { label: '更新时间', value: task.updated_at ? new Date(task.updated_at * 1000).toLocaleString('zh-CN') : '--' },
  ]

  return (
    <div className="space-y-3">
      {/* 头部概览卡片 */}
      <div className={`rounded-xl bg-gradient-to-r ${statusColor.replace('400', '50').replace('600', '50').replace('500', '50')} p-5 border`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wider">任务 #{task.id}</p>
            <h3 className="text-lg font-semibold text-foreground mt-0.5">{task.topic}</h3>
          </div>
        </div>
        <div className="flex items-center gap-3 mt-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-current" />{task.account}</span>
          <span className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-current" />{isNewspic ? '贴图' : isMd ? '去味发布' : '图文'}</span>
          {task.ai_verdict && <span className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-current" />{task.ai_verdict}</span>}
        </div>
      </div>

      {/* 常规信息 —— 四列网格：label | value | label | value */}
      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <div className="grid grid-cols-[auto_1fr_auto_1fr]">
          {gridItems.map((item) => {
            if ('fullWidth' in item && item.fullWidth) {
              return (
                <div key={item.label} className="col-span-4 px-4 py-2.5 border-b border-border last:border-b-0">
                  <span className="text-xs text-muted-foreground">{item.label}</span>
                  <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words mt-1 max-h-[7.5rem] overflow-y-auto">{item.value}</p>
                </div>
              )
            }
            return (
              <React.Fragment key={item.label}>
                <div className="px-3 py-2.5 border-b border-r border-border bg-muted/30">
                  <span className="text-xs text-muted-foreground whitespace-nowrap">{item.label}</span>
                </div>
                <div className="px-3 py-2.5 border-b border-border flex items-center gap-2 min-w-0 hover:bg-muted/30 transition-colors">
                  <span className="text-sm text-foreground truncate flex-1 min-w-0">{item.value}</span>
                  {'extra' in item && item.extra ? <div className="shrink-0">{item.extra as React.ReactNode}</div> : null}
                </div>
              </React.Fragment>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/** 选题简报（news + newspic 共用）
 *  当任务状态为 0（出错了）且是从 20（简报已就绪）转入时，支持编辑保存。 */
function BriefTab({ task, onSaved }: { task: TaskDetailType; onSaved: () => void }) {
  const statusLabel = STATUS_LABELS[task.status] || `状态 ${task.status}`
  // 判断是否可编辑：状态为 0 且上一条状态为 20（相邻记录 20→0）
  const editable = (() => {
    if (task.status !== 0) return false
    const history = task.status_history
    for (let i = 1; i < history.length; i++) {
      if (history[i].to_status === 0 && history[i - 1].to_status === 20) {
        return true
      }
    }
    return false
  })()

  const [editing, setEditing] = useState(false)
  const [editContent, setEditContent] = useState(task.brief || '')
  const [saving, setSaving] = useState(false)
  const [showSaveConfirm, setShowSaveConfirm] = useState(false)

  if (!task.brief && !editable) {
    return <EmptyTab icon={<FileText size={32} />} text="简报尚未生成" />
  }

  if (!editable) {
    // 不可编辑：使用只读 MarkdownViewer
    if (!task.brief) {
      return <EmptyTab icon={<FileText size={32} />} text="简报尚未生成" />
    }
    return <MarkdownViewer content={task.brief} />
  }

  // 可编辑模式
  if (!editing) {
    // 未进入编辑状态：显示只读视图 + 编辑按钮
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-end">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setEditContent(task.brief || '')
              setEditing(true)
            }}
          >
            <FileCode size={14} />
            <span className="ml-1.5">编辑简报</span>
          </Button>
        </div>
        {task.brief ? (
          <MarkdownViewer content={task.brief} />
        ) : (
          <EmptyTab icon={<FileText size={32} />} text="简报尚未生成" />
        )}
      </div>
    )
  }

  // 编辑状态：显示 TiptapEditor（带工具条）+ 保存/取消按钮
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-foreground">编辑选题简报</span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditing(false)}
            disabled={saving}
          >
            取消
          </Button>
          <Button
            size="sm"
            onClick={() => setShowSaveConfirm(true)}
            disabled={saving}
          >
            {saving ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Save size={14} />
            )}
            <span className="ml-1.5">保存</span>
          </Button>
        </div>
      </div>

      <div className="rounded-lg border bg-card overflow-hidden">
        <div
          className="tiptap-auto-height [&_[class*='ProseMirror']]:min-h-[300px] [&_[class*='ProseMirror']]:overflow-visible"
          style={{ overflow: 'visible' }}
        >
          <TiptapEditor
            content={editContent}
            onChange={(html: string) => setEditContent(html)}
            editable={true}
            placeholder="开始编辑选题简报..."
            contentClassName="min-h-[300px] p-4"
          />
          <style>{`
            .tiptap-auto-height [class*="ProseMirror"] {
              overflow: visible !important;
              height: auto !important;
              min-height: 300px;
            }
          `}</style>
        </div>
      </div>

      {/* 保存确认弹窗 */}
      {showSaveConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowSaveConfirm(false)}>
          <div className="bg-card rounded-xl border border-border shadow-xl max-w-md w-full mx-4 p-6 space-y-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-start gap-3">
              <div className="size-10 rounded-full bg-blue-100 text-blue-600 dark:bg-blue-900 dark:text-blue-300 flex items-center justify-center shrink-0">
                <Save size={20} />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-lg font-semibold text-foreground">确认保存</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  确定要保存对选题简报的修改吗？此操作将覆盖原有简报内容。
                </p>
                <div className="mt-3 p-3 rounded-lg bg-muted/50 border border-border">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">任务</span>
                    <span className="font-medium">#{task.id} {task.topic}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs mt-1">
                    <span className="text-muted-foreground">当前状态</span>
                    <span className="font-medium text-destructive">{statusLabel}</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowSaveConfirm(false)}>
                取消
              </Button>
              <Button
                size="sm"
                onClick={async () => {
                  setSaving(true)
                  setShowSaveConfirm(false)
                  try {
                    await updateTaskBrief(task.id, editContent)
                    setEditing(false)
                    onSaved()
                  } catch (e) {
                    alert(e instanceof Error ? e.message : '保存失败')
                  } finally {
                    setSaving(false)
                  }
                }}
              >
                确认保存
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** 文章内容（仅 news） */
function ArticleTab({ content }: { content: string }) {
  if (!content) {
    return <EmptyTab icon={<FileCheck size={32} />} text="文章尚未生成" />
  }
  return <MarkdownViewer content={content} />
}

/** 文章配图（使用 ImageReviewCard，支持替换/重新生成/更新等操作） */
function ImagesTab({ images, taskId, taskType, showActions, onRefresh }: {
  images: TaskDetailType['images']
  taskId: number
  taskType: string
  showActions: boolean  // 是否显示操作按钮（替换/重新生成/更新）
  onRefresh: () => void
}) {
  const [opsDisabled, setOpsDisabled] = useState(false)
  const [appendDisabled, setAppendDisabled] = useState(false)

  /** 新增图片：上传到任务 images/ 目录，锚点追加到文章末尾（article）或作为末尾新卡片（newspic） */
  const handleAppendImages = async (fileList: FileList | null) => {
    const list = Array.from(fileList ?? []).filter(f => f.type.startsWith('image/'))
    if (list.length === 0) return
    setAppendDisabled(true)
    try {
      await appendTaskImages(taskId, list)
      onRefresh()
    } catch (e) {
      alert(e instanceof Error ? e.message : '新增图片失败')
    } finally {
      setAppendDisabled(false)
    }
  }

  const hasCoverRecord = images.some(i => i.is_cover === 1)

  const handleReplace = async (imageId: number, file: File) => {
    setOpsDisabled(true)
    try {
      await replaceTaskImage(taskId, imageId, file)
      onRefresh()
    } catch (e) {
      alert(e instanceof Error ? e.message : '替换失败')
    } finally {
      setOpsDisabled(false)
    }
  }

  const handleRegenerate = async (imageId: number, prompt: string) => {
    setOpsDisabled(true)
    try {
      await regenerateTaskImage(taskId, imageId, prompt)
      onRefresh()
    } catch (e) {
      throw e  // 由 ImageReviewCard 内部处理错误展示
    } finally {
      setOpsDisabled(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* 新增图片：上传到任务 images/ 目录，锚点追加到文章末尾（仅未发布且非运行中时显示） */}
      {showActions && (
        <div className="flex items-center justify-end">
          <label className={`inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/5 px-2.5 py-1.5 text-xs font-medium text-primary cursor-pointer hover:bg-primary/10 transition-colors ${appendDisabled ? 'opacity-50 pointer-events-none' : ''}`}>
            <Plus size={14} />
            新增图片
            <input
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              disabled={appendDisabled}
              onChange={e => handleAppendImages(e.target.files)}
            />
          </label>
        </div>
      )}
      {!images || images.length === 0 ? (
        <EmptyTab icon={<Image size={32} />} text="暂无配图" />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {images.map(img => (
            <ImageReviewCard
              key={img.id}
              image={img}
              taskId={taskId}
              taskType={taskType}
              hasCoverRecord={hasCoverRecord}
              onReplace={(file) => handleReplace(img.id, file)}
              onRegenerate={(prompt) => handleRegenerate(img.id, prompt)}
              onRefresh={onRefresh}
              showActions={showActions}
              disabled={opsDisabled}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/** AI检测 */
function AIScoreTab({ history }: { history: TaskStatusHistory[] }) {
  const aiEntry = history.find(h => h.to_status === 80 || h.to_status === 85)

  if (!aiEntry) {
    return <EmptyTab icon={<Activity size={32} />} text="AI 检测尚未完成" />
  }

  // 解析 remark JSON（后端字段: total_score, dimensions, hit_phrases, hit_vocab, threshold）
  let report: {
    total_score?: number; mode?: string; threshold?: number
    dimensions?: Record<string, number>
    hit_phrases?: string[]; hit_vocab?: string[]
  } | null = null
  if (aiEntry.remark) {
    try { report = JSON.parse(aiEntry.remark) } catch { /* 非JSON */ }
  }

  // 维度英文 → 中文映射
  const DIM_LABELS: Record<string, string> = {
    burstiness: '突发性', phrases: '短语', vocab: '词汇',
    structural: '结构性', punctuation: '标点符号', style: '风格',
  }

  if (!report) {
    return (
      <div className="space-y-3">
        <ResultBanner passed={aiEntry.to_status === 80} label={aiEntry.to_label} info={aiEntry.to_info} />
        <div className="rounded-lg border border-border bg-card p-5">
          <pre className="text-sm text-muted-foreground whitespace-pre-wrap">{aiEntry.remark || '(无详细报告)'}</pre>
        </div>
      </div>
    )
  }

  const passed = aiEntry.to_status === 80
  const totalScore = report.total_score ?? 0
  const threshold = report.threshold ?? 45
  const dimensions = report.dimensions || {}
  const hitPhrases = report.hit_phrases || []
  const hitWords = report.hit_vocab || []
  const maxDimScore = Math.max(...Object.values(dimensions), 1)

  return (
    <div className="space-y-5">
      <ResultBanner passed={passed} label={aiEntry.to_label} info={aiEntry.to_info} />

      {/* 总分大盘 */}
      <div className="grid grid-cols-3 gap-4">
        <ScoreGauge label="AI 味总分" score={totalScore} threshold={threshold} inverse />
        <ScoreGauge label="阈值" score={threshold} max={100} />
        <div className="rounded-lg border border-border bg-card p-4 flex flex-col items-center justify-center gap-1">
          <span className="text-xs text-muted-foreground">结果</span>
          <span className={`text-lg font-bold ${passed ? 'text-emerald-500' : 'text-red-500'}`}>
            {passed ? 'PASS' : 'FAIL'}
          </span>
          <span className="text-xs text-muted-foreground">
            {passed ? 'AI 味在可接受范围' : `超过阈值 ${threshold}`}
          </span>
        </div>
      </div>

      {/* 各维度得分 */}
      <div className="rounded-lg border border-border bg-card p-5">
        <h4 className="text-sm font-medium text-foreground mb-4">维度得分</h4>
        <div className="space-y-2.5">
          {Object.entries(dimensions).map(([name, score]) => {
            const pct = maxDimScore > 0 ? (score / maxDimScore) * 100 : 0
            const barColor = score > 40 ? 'bg-red-400' : score > 20 ? 'bg-yellow-400' : 'bg-emerald-400'
            const textColor = score > 40 ? 'text-red-500' : score > 20 ? 'text-yellow-600' : 'text-emerald-500'
            const label = DIM_LABELS[name] || name
            return (
              <div key={name} className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground w-16 shrink-0">{label}</span>
                <div className="flex-1 h-2.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${barColor}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className={`text-xs font-mono font-medium w-10 text-right ${textColor}`}>
                  {score.toFixed(1)}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* 命中明细 */}
      {(hitWords.length > 0 || hitPhrases.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          {hitWords.length > 0 && (
            <div className="rounded-lg border border-border bg-card p-4">
              <h4 className="text-sm font-medium text-foreground mb-2">命中词汇</h4>
              <div className="flex flex-wrap gap-1.5">
                {hitWords.map(w => (
                  <span key={w} className="px-2 py-0.5 bg-yellow-50 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300 rounded text-xs font-medium">
                    {w}
                  </span>
                ))}
              </div>
            </div>
          )}
          {hitPhrases.length > 0 && (
            <div className="rounded-lg border border-border bg-card p-4">
              <h4 className="text-sm font-medium text-foreground mb-2">命中短语</h4>
              <div className="flex flex-wrap gap-1.5">
                {hitPhrases.map(p => (
                  <span key={p} className="px-2 py-0.5 bg-orange-50 text-orange-700 dark:bg-orange-950 dark:text-orange-300 rounded text-xs font-medium">
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ResultBanner({ passed, label, info }: { passed: boolean; label: string; info: string }) {
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${
      passed
        ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
        : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300'
    }`}>
      <div className="flex items-center gap-2">
        {passed ? <CheckCircle size={18} /> : <AlertTriangle size={18} />}
        <p className="font-medium">{label}</p>
      </div>
      <p className="text-xs mt-1 opacity-80">{info}</p>
    </div>
  )
}

function ScoreGauge({ label, score, threshold, max = 100, inverse }: {
  label: string; score: number; threshold?: number; max?: number; inverse?: boolean
}) {
  const pct = Math.min((score / max) * 100, 100)
  const danger = inverse ? score < (threshold ?? 45) : score > (threshold ?? 45)
  const color = danger ? 'text-red-500' : 'text-emerald-500'
  const ringColor = danger ? 'stroke-red-400' : 'stroke-emerald-400'

  return (
    <div className="rounded-lg border border-border bg-card p-4 flex flex-col items-center gap-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="relative size-20">
        <svg className="size-20 -rotate-90" viewBox="0 0 36 36">
          <circle cx="18" cy="18" r="15.5" fill="none" stroke="currentColor" className="text-muted/20" strokeWidth="2.5" />
          <circle cx="18" cy="18" r="15.5" fill="none" stroke="currentColor"
            className={ringColor}
            strokeWidth="2.5"
            strokeDasharray={`${pct * 0.97} 100`}
            strokeLinecap="round"
          />
        </svg>
        <span className={`absolute inset-0 flex items-center justify-center text-lg font-bold ${color}`}>
          {score.toFixed(0)}
        </span>
      </div>
      {threshold != null && (
        <span className="text-[10px] text-muted-foreground">阈值 {threshold}</span>
      )}
    </div>
  )
}

/** 文章预览 —— 默认显示预览，可切换到源码 */
function PreviewTab({ html }: { html: string }) {
  const [mode, setMode] = useState<'preview' | 'source'>('preview')

  if (!html) {
    return <EmptyTab icon={<Eye size={32} />} text="文章 HTML 尚未生成" />
  }

  return (
    <div className="bg-card rounded-lg border border-border overflow-hidden">
      <div className="flex items-center gap-1 px-3 py-2 border-b border-border bg-muted/30">
        <button
          onClick={() => setMode('preview')}
          className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
            mode === 'preview' ? 'bg-background text-foreground shadow-sm border border-border' : 'text-muted-foreground hover:text-foreground'
          }`}
        ><Eye size={14} /><span className="hidden sm:inline">预览</span></button>
        <button
          onClick={() => setMode('source')}
          className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
            mode === 'source' ? 'bg-background text-foreground shadow-sm border border-border' : 'text-muted-foreground hover:text-foreground'
          }`}
        ><FileCode size={14} /><span className="hidden sm:inline">源码</span></button>
      </div>

      {mode === 'preview' ? (
        <div className="flex justify-center py-6 bg-muted/30">
          <PhoneFrame html={html} />
        </div>
      ) : (
        <pre className="whitespace-pre-wrap font-mono text-xs text-foreground leading-relaxed p-5 min-h-[200px] max-h-[70vh] overflow-auto">
          {html}
        </pre>
      )}
    </div>
  )
}

/** 手机外框 */
function PhoneFrame({ html }: { html: string }) {
  return (
    <div className="w-[375px] shrink-0">
      {/* 机身 */}
      <div className="rounded-[2.5rem] border-[6px] border-gray-800 dark:border-gray-700 bg-white shadow-xl overflow-hidden">
        {/* 状态栏 */}
        <div className="bg-white pt-2 pb-1 px-6 flex items-center justify-between">
          <span className="text-[10px] font-medium text-gray-900">9:41</span>
          <div className="flex items-center gap-1">
            <svg className="size-3" viewBox="0 0 16 12" fill="currentColor"><rect x="0" y="2" width="2" height="8" rx="0.5" /><rect x="3" y="1" width="2" height="10" rx="0.5" /><rect x="6" y="0" width="2" height="12" rx="0.5" /><rect x="9" y="1" width="2" height="10" rx="0.5" /><rect x="12" y="2" width="2" height="8" rx="0.5" /></svg>
            <svg className="size-3" viewBox="0 0 16 12" fill="currentColor"><rect x="0" y="0" width="2" height="12" rx="1" /><rect x="4" y="4" width="2" height="6" rx="1" /><rect x="8" y="2" width="2" height="8" rx="1" /></svg>
            <svg className="size-3" viewBox="0 0 25 12" fill="currentColor"><rect x="0.5" y="0.5" width="21" height="11" rx="2.5" stroke="currentColor" fill="none" strokeWidth="1" /><rect x="22" y="3" width="1.5" height="6" rx="0.75" /><rect x="2" y="2.5" width="17" height="7" rx="1.5" fill="currentColor" opacity="0.8" /></svg>
          </div>
        </div>
        {/* 正文区 */}
        <div className="bg-white" style={{ height: 580 }}>
          <iframe
            srcDoc={html}
            className="w-full h-full border-0"
            sandbox="allow-same-origin"
            title="手机预览"
            scrolling="yes"
          />
        </div>
        {/* 底部导航条 */}
        <div className="bg-white pt-2 pb-1 flex justify-center">
          <div className="w-32 h-1 bg-gray-300 rounded-full" />
        </div>
      </div>
    </div>
  )
}

// ============================================================
// 空状态
// ============================================================

/** 空状态 */
function EmptyTab({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-2 text-muted-foreground">
      {icon}
      <p className="text-sm">{text}</p>
    </div>
  )
}
