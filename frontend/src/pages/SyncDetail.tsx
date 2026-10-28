import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Loader2, ArrowLeft, CheckCircle, XCircle, RefreshCw, Clock,
  RotateCcw, AlertCircle, FileText, Link as LinkIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getSyncTask, retrySyncTask } from '@/lib/api'
import { PLATFORM_LABELS } from '@/lib/constants'
import type { SyncTaskDetail } from '@/lib/api'

const SYNC_STATUS_LABELS: Record<string, string> = {
  pending: '待同步',
  syncing: '同步中',
  success: '全部成功',
  partial: '部分成功',
  failed: '全部失败',
  draft: '草稿',
}

const SYNC_STATUS_STYLES: Record<string, string> = {
  pending: 'bg-muted text-muted-foreground',
  syncing: 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  success: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
  partial: 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  failed: 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
  draft: 'bg-slate-50 text-slate-600 dark:bg-slate-900 dark:text-slate-400',
}

function fmtTime(ts: number): string {
  if (!ts) return '--'
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}


export function SyncDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<SyncTaskDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 重试状态
  const [retryingAll, setRetryingAll] = useState(false)
  const [retryingPlatforms, setRetryingPlatforms] = useState<Set<string>>(new Set())
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const res = await getSyncTask(Number(id))
      if (res.code === 0 && res.data) {
        // draft 状态（尚未执行过同步）→ 跳转到编辑页面
        if (res.data.status === 'draft') {
          navigate(`/sync/new?syncId=${id}`, { replace: true })
          return
        }
        setDetail(res.data)
      } else {
        setError(res.message || '加载失败')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [id, navigate])

  useEffect(() => { load() }, [load])

  // 重试全部失败平台
  const handleRetryAll = async () => {
    if (!detail || !id) return
    const failedPlatforms = detail.results
      .filter(r => r.status === 'failed')
      .map(r => r.platform)
    if (failedPlatforms.length === 0) return

    setRetryingAll(true)
    setError(null)
    try {
      const res = await retrySyncTask(Number(id))
      if (res.code === 0 && res.data) {
        setDetail(res.data)
        setToast({ type: 'success', message: `已重试 ${failedPlatforms.length} 个平台` })
      } else {
        setError(res.message || '重试失败')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '重试请求失败')
    } finally {
      setRetryingAll(false)
    }
  }

  // 重试单个平台
  const handleRetrySingle = async (platform: string) => {
    if (!id) return
    setRetryingPlatforms(prev => new Set(prev).add(platform))
    setError(null)
    try {
      const res = await retrySyncTask(Number(id), [platform])
      if (res.code === 0 && res.data) {
        setDetail(res.data)
        // 检查该平台结果
        const result = res.data.results.find(r => r.platform === platform)
        if (result?.status === 'success') {
          setToast({ type: 'success', message: `${PLATFORM_LABELS[platform] || platform} 重试成功` })
        } else {
          setToast({ type: 'error', message: `${PLATFORM_LABELS[platform] || platform} 重试失败: ${result?.error_msg || '未知错误'}` })
        }
      } else {
        setError(res.message || '重试失败')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '重试请求失败')
    } finally {
      setRetryingPlatforms(prev => {
        const next = new Set(prev)
        next.delete(platform)
        return next
      })
    }
  }

  // 自动清除 toast
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 4000)
      return () => clearTimeout(timer)
    }
  }, [toast])

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="animate-spin text-muted-foreground" size={28} />
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate('/sync')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft size={14} /> 返回列表
        </button>
        <div className="text-sm text-destructive">{error || '记录不存在'}</div>
      </div>
    )
  }

  const successCount = detail.results.filter(r => r.status === 'success').length
  const failedCount = detail.results.filter(r => r.status === 'failed').length
  const hasFailed = failedCount > 0

  return (
    <div className="space-y-6 pb-8 max-w-4xl">
      {/* Toast */}
      {toast && (
        <div className={`flex items-center gap-3 rounded-lg border px-4 py-3 shadow-lg transition-all ${
          toast.type === 'success'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
            : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300'
        }`}>
          {toast.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          <span className="text-sm flex-1">{toast.message}</span>
          <button onClick={() => setToast(null)} className="text-current opacity-50 hover:opacity-100">
            <XCircle size={14} />
          </button>
        </div>
      )}

      {/* 顶栏 */}
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => navigate('/sync')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors mb-1">
            <ArrowLeft size={14} /> 返回列表
          </button>
          <h2 className="text-xl font-bold text-foreground tracking-tight">同步详情</h2>
        </div>
        <div className="flex items-center gap-2">
          {hasFailed && (
            <Button
              variant="outline" size="sm"
              onClick={handleRetryAll}
              disabled={retryingAll}
            >
              {retryingAll ? (
                <Loader2 size={14} className="animate-spin mr-1" />
              ) : (
                <RotateCcw size={14} className="mr-1" />
              )}
              重试全部失败（{failedCount}）
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => navigate('/sync/new')}>
            <RefreshCw size={14} className="mr-1" />
            新建同步
          </Button>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertCircle size={16} className="shrink-0 mt-0.5" />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError(null)} className="shrink-0 text-destructive/60 hover:text-destructive">
            <XCircle size={14} />
          </button>
        </div>
      )}

      {/* 基本信息卡片 */}
      <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
        <div className="flex items-center gap-2.5 px-5 py-3 border-b border-border bg-muted/30">
          <Clock size={16} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">基本信息</h3>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-[auto_1fr_auto_1fr] text-sm">
            <div className="px-3 py-2 border-b border-r border-border bg-muted/30">
              <span className="text-xs text-muted-foreground">来源</span>
            </div>
            <div className="px-3 py-2 border-b border-border">
              <span className="inline-flex items-center gap-1.5">
                {detail.sync_from === 'task' ? (
                  <span className="text-foreground font-mono">任务 #{detail.task_id}</span>
                ) : detail.sync_from === 'local' ? (
                  <>
                    <FileText size={14} className="text-purple-500" />
                    <span className="text-xs px-1.5 py-0.5 rounded bg-purple-50 text-purple-600 dark:bg-purple-950 dark:text-purple-300">本地文件</span>
                    {detail.file_path && <span className="text-xs text-muted-foreground truncate max-w-[160px]" title={detail.file_path}>{detail.file_path.split('/').pop()?.split('\\').pop()}</span>}
                  </>
                ) : (
                  <>
                    <LinkIcon size={14} className="text-cyan-500" />
                    <span className="text-xs px-1.5 py-0.5 rounded bg-cyan-50 text-cyan-600 dark:bg-cyan-950 dark:text-cyan-300">网址</span>
                    {detail.url && <span className="text-xs text-muted-foreground truncate max-w-[160px]" title={detail.url}>{detail.url}</span>}
                  </>
                )}
              </span>
            </div>
            <div className="px-3 py-2 border-b border-r border-border bg-muted/30">
              <span className="text-xs text-muted-foreground">话题</span>
            </div>
            <div className="px-3 py-2 border-b border-border">
              <span className="text-foreground">{detail.topic || '--'}</span>
            </div>
            <div className="px-3 py-2 border-b border-r border-border bg-muted/30">
              <span className="text-xs text-muted-foreground">标题</span>
            </div>
            <div className="px-3 py-2 border-b border-border">
              <span className="text-foreground truncate">{detail.title || '--'}</span>
            </div>
            <div className="px-3 py-2 border-b border-r border-border bg-muted/30">
              <span className="text-xs text-muted-foreground">状态</span>
            </div>
            <div className="px-3 py-2 border-b border-border">
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${SYNC_STATUS_STYLES[detail.status] || ''}`}>
                {SYNC_STATUS_LABELS[detail.status] || detail.status}
              </span>
            </div>
            <div className="px-3 py-2 border-r border-border bg-muted/30">
              <span className="text-xs text-muted-foreground">平台数</span>
            </div>
            <div className="px-3 py-2">
              <span className="text-foreground">{detail.platform_count} 个平台</span>
            </div>
            <div className="px-3 py-2 border-r border-border bg-muted/30">
              <span className="text-xs text-muted-foreground">同步时间</span>
            </div>
            <div className="px-3 py-2">
              <span className="text-foreground">{fmtTime(detail.updated_at)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* 同步结果 */}
      <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-muted/30">
          <h3 className="text-sm font-semibold text-foreground">各平台同步结果</h3>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <CheckCircle size={12} className="text-emerald-500" />
              成功 {successCount}
            </span>
            <span className="flex items-center gap-1">
              <XCircle size={12} className="text-red-500" />
              失败 {failedCount}
            </span>
          </div>
        </div>

        <div className="p-5">
          {detail.results.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              <Clock size={24} className="mx-auto mb-2 opacity-30" />
              暂无结果数据
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">平台</th>
                    <th className="text-center px-3 py-2 text-xs font-medium text-muted-foreground w-24">状态</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">错误信息</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground w-40">时间</th>
                    <th className="text-center px-3 py-2 text-xs font-medium text-muted-foreground w-16">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.results.map(r => {
                    const isRetrying = retryingPlatforms.has(r.platform)
                    return (
                      <tr key={r.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                        <td className="px-3 py-2 font-medium text-foreground">
                          {r.platform_label || PLATFORM_LABELS[r.platform] || r.platform}
                        </td>
                        <td className="px-3 py-2 text-center">
                          {r.status === 'success' ? (
                            <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                              <CheckCircle size={12} /> 成功
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
                              <XCircle size={12} /> 失败
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-xs text-muted-foreground max-w-[300px]">
                          <span className="line-clamp-2" title={r.error_msg || undefined}>
                            {r.error_msg || '--'}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-xs text-muted-foreground">{fmtTime(r.created_at)}</td>
                        <td className="px-2 py-2 text-center">
                          {r.status === 'failed' && (
                            <button
                              onClick={() => handleRetrySingle(r.platform)}
                              disabled={isRetrying}
                              className="p-1 rounded text-muted-foreground/60 hover:text-primary
                                         hover:bg-primary/10 transition-colors"
                              title={`重试 ${PLATFORM_LABELS[r.platform] || r.platform}`}
                            >
                              {isRetrying ? (
                                <Loader2 size={14} className="animate-spin" />
                              ) : (
                                <RotateCcw size={14} />
                              )}
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
