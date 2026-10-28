import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, ChevronLeft, ChevronRight, Plus, Eye, RefreshCw, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getSyncTasks } from '@/lib/api'
import type { SyncTaskItem } from '@/lib/api'

const PAGE_SIZE = 20

const SYNC_STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  pending: '待同步',
  syncing: '同步中',
  success: '全部成功',
  partial: '部分成功',
  failed: '全部失败',
}

const SYNC_STATUS_STYLES: Record<string, string> = {
  draft: 'bg-slate-50 text-slate-600 dark:bg-slate-900 dark:text-slate-400',
  pending: 'bg-muted text-muted-foreground',
  syncing: 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  success: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
  partial: 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  failed: 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
}

/** 格式化时间戳 */
function fmtTime(ts: number): string {
  if (!ts) return '--'
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

export function SyncList() {
  const navigate = useNavigate()
  const [items, setItems] = useState<SyncTaskItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [sortBy, setSortBy] = useState<string>('created_at')
  const [sortOrder, setSortOrder] = useState<string>('desc')

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getSyncTasks({ page, pageSize: PAGE_SIZE, sort_by: sortBy, sort_order: sortOrder })
      if (res.data) {
        setItems(res.data.items || [])
        setTotal(res.data.total || 0)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, sortBy, sortOrder])

  useEffect(() => { load() }, [load])

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      setSortOrder(field === 'created_at' || field === 'task_id' ? 'desc' : 'asc')
    }
  }

  const SortIcon = ({ field }: { field: string }) => {
    if (sortBy !== field) return <ArrowUpDown size={11} className="opacity-30" />
    return sortOrder === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />
  }

  return (
    <div className="space-y-4 pb-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-page-title text-foreground">多平台同步</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            共 {total} 条记录 · 第 {page}/{totalPages} 页
          </p>
        </div>
        <Button size="sm" onClick={() => navigate('/sync/new')}>
          <Plus size={14} className="mr-1" />
          新增同步
        </Button>
      </div>

      {error ? (
        <div className="text-sm text-destructive">{error}</div>
      ) : loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="animate-spin text-muted-foreground" size={28} />
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm table-fixed">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-center px-2 py-2 text-xs font-medium text-muted-foreground w-[52px]">ID</th>
                  <th className="text-center px-3 py-2 text-xs font-medium text-muted-foreground w-[112px]">
                    <button onClick={() => handleSort('sync_from')} className="inline-flex items-center gap-1 hover:text-foreground transition-colors">
                      来源 <SortIcon field="sync_from" />
                    </button>
                  </th>
                  <th className="text-center px-3 py-2 text-xs font-medium text-muted-foreground">
                    <button onClick={() => handleSort('topic')} className="inline-flex items-center gap-1 hover:text-foreground transition-colors">
                      话题/标题 <SortIcon field="topic" />
                    </button>
                  </th>
                  <th className="text-center px-3 py-2 text-xs font-medium text-muted-foreground w-[72px]">平台数</th>
                  <th className="text-center px-3 py-2 text-xs font-medium text-muted-foreground w-[120px]">
                    <button onClick={() => handleSort('status')} className="inline-flex items-center gap-1 hover:text-foreground transition-colors">
                      状态 <SortIcon field="status" />
                    </button>
                  </th>
                  <th className="text-center px-3 py-2 text-xs font-medium text-muted-foreground w-[148px]">
                    <button onClick={() => handleSort('created_at')} className="inline-flex items-center gap-1 hover:text-foreground transition-colors">
                      同步时间 <SortIcon field="created_at" />
                    </button>
                  </th>
                  <th className="text-center px-3 py-2 text-xs font-medium text-muted-foreground w-[148px]">
                    <button onClick={() => handleSort('updated_at')} className="inline-flex items-center gap-1 hover:text-foreground transition-colors">
                      更新时间 <SortIcon field="updated_at" />
                    </button>
                  </th>
                  <th className="text-center px-2 py-2 text-xs font-medium text-muted-foreground w-[44px]">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-12 text-muted-foreground">
                      <RefreshCw size={24} className="mx-auto mb-2 opacity-30" />
                      暂无同步记录
                    </td>
                  </tr>
                ) : items.map(item => (
                  <tr
                    key={item.id}
                    onClick={() => {
                      // 全部失败且无结果 → 跳编辑页，方便用户修改后重试
                      if (item.status === 'failed' && item.result_count === 0) {
                        navigate(`/sync/new?syncId=${item.id}`)
                      } else {
                        navigate(`/sync/${item.id}`)
                      }
                    }}
                    className="border-b border-border last:border-0 hover:bg-muted/50 cursor-pointer transition-colors"
                  >
                    <td className="px-3 py-2 text-center text-xs text-muted-foreground font-mono">
                      {item.id}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {item.sync_from === 'task' ? (
                        <span className="text-xs px-1 py-0.5 rounded bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-300">任务</span>
                      ) : item.sync_from === 'local' ? (
                        <span className="text-xs px-1 py-0.5 rounded bg-purple-50 text-purple-600 dark:bg-purple-950 dark:text-purple-300">本地文件</span>
                      ) : (
                        <span className="text-xs px-1 py-0.5 rounded bg-cyan-50 text-cyan-600 dark:bg-cyan-950 dark:text-cyan-300">网址</span>
                      )}
                    </td>
                    <td className="px-3 py-2 min-w-0">
                      <div className="font-medium text-foreground truncate">{item.topic || item.title}</div>
                      {item.topic && item.title && item.topic !== item.title && (
                        <div className="text-xs text-muted-foreground truncate">{item.title}</div>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground text-center">{item.platform_count}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${SYNC_STATUS_STYLES[item.status] || ''}`}>
                        {SYNC_STATUS_LABELS[item.status] || item.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground text-center">{fmtTime(item.created_at)}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground text-center">{fmtTime(item.updated_at)}</td>
                    <td className="px-2 py-2 text-center">
                      <button
                        onClick={e => {
                          e.stopPropagation()
                          // 全部失败且无结果 → 跳编辑页
                          const target = (item.status === 'failed' && item.result_count === 0)
                            ? `/sync/new?syncId=${item.id}`
                            : `/sync/${item.id}`
                          navigate(target)
                        }}
                        className="p-1 rounded text-muted-foreground/60 hover:text-primary hover:bg-primary/10 transition-colors"
                        title="查看详情"
                      >
                        <Eye size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 分页 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">第 {page} 页，共 {totalPages} 页</span>
              <div className="flex gap-1">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                  <ChevronLeft size={14} /> 上一页
                </Button>
                <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                  下一页 <ChevronRight size={14} />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
