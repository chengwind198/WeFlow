import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Loader2, ChevronLeft, ChevronRight, ArrowUp, ArrowDown, Eye, X,
  ClipboardCheck, Clock, CheckCircle, XCircle, Search,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getReviewQueue } from '@/lib/api'
import type { ReviewListItem } from '@/types/task'

const PAGE_SIZE = 20

/** 审核阶段的标签 */
const STAGE_LABELS: Record<number, string> = {
  20: '选题简报',
  35: '卡片规划',
  40: '文章草稿',
  60: '配图审核',
  85: 'AI 味检测',
}

export function ReviewQueue() {
  const navigate = useNavigate()
  const [items, setItems] = useState<ReviewListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 筛选
  const [filterStatus, setFilterStatus] = useState('pending')
  const [filterTaskType, setFilterTaskType] = useState('')
  const [filterStage, setFilterStage] = useState('')

  // 排序
  const [sortBy, setSortBy] = useState('created_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  // 日期过滤
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const hasActiveFilters = filterStatus || filterTaskType || filterStage || dateFrom || dateTo

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getReviewQueue({
        page,
        page_size: PAGE_SIZE,
        status: filterStatus || undefined,
        task_type: filterTaskType || undefined,
        stage: filterStage ? Number(filterStage) : undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        date_from: dateFrom ? String(Math.floor(new Date(dateFrom).getTime() / 1000)) : undefined,
        date_to: dateTo ? String(Math.floor(new Date(dateTo).getTime() / 1000) + 86400) : undefined,
      })
      if (res.data) {
        setItems((res.data.items || []) as ReviewListItem[])
        setTotal(res.data.total || 0)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, filterStatus, filterTaskType, filterStage, sortBy, sortOrder, dateFrom, dateTo])

  useEffect(() => { load() }, [load])

  const handleSort = (column: string) => {
    if (sortBy === column) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(column)
      setSortOrder('desc')
    }
    setPage(1)
  }

  const sortIcon = (column: string) => {
    if (sortBy !== column) return null
    return sortOrder === 'asc'
      ? <ArrowUp size={11} className="text-primary" />
      : <ArrowDown size={11} className="text-primary" />
  }

  const handleView = (item: ReviewListItem) => {
    navigate(`/review/${item.id}`)
  }

  const resetFilters = () => {
    setFilterStatus('pending')
    setFilterTaskType('')
    setFilterStage('')
    setDateFrom('')
    setDateTo('')
    setPage(1)
  }

  // 状态标签
  const statusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return {
          icon: Clock,
          label: '待审核',
          className: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800',
        }
      case 'approved':
        return {
          icon: CheckCircle,
          label: '已通过',
          className: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800',
        }
      case 'rejected':
        return {
          icon: XCircle,
          label: '已驳回',
          className: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/60 dark:text-red-300 dark:border-red-800',
        }
      default:
        return { icon: Clock, label: status, className: 'bg-muted text-muted-foreground border-border' }
    }
  }

  return (
    <div className="space-y-5 pb-8">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="size-10 rounded-xl bg-gradient-to-br from-amber-100 to-amber-200 flex items-center justify-center shadow-sm dark:from-amber-900 dark:to-amber-800">
            <ClipboardCheck size={20} className="text-amber-700 dark:text-amber-200" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">人工审核队列</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              共 <span className="font-semibold text-foreground">{total}</span> 条记录
              {totalPages > 1 && <> · 第 {page}/{totalPages} 页</>}
            </p>
          </div>
        </div>
      </div>

      {/* 筛选栏 */}
      <div className="rounded-xl border bg-card px-4 py-3 shadow-sm">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mr-1">
            <Search size={13} />
            筛选
          </span>

          {/* 状态筛选 */}
          <select
            value={filterStatus}
            onChange={e => { setFilterStatus(e.target.value); setPage(1) }}
            className="h-8 rounded-lg border border-border bg-background px-2.5 text-xs text-foreground
                       focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500/50
                       transition-all cursor-pointer"
          >
            <option value="">全部状态</option>
            <option value="pending">待审核</option>
            <option value="approved">已通过</option>
            <option value="rejected">已驳回</option>
          </select>

          {/* 任务类型 */}
          <select
            value={filterTaskType}
            onChange={e => { setFilterTaskType(e.target.value); setPage(1) }}
            className="h-8 rounded-lg border border-border bg-background px-2.5 text-xs text-foreground
                       focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500/50
                       transition-all cursor-pointer"
          >
            <option value="">全部类型</option>
            <option value="article">图文</option>
            <option value="image">贴图</option>
          </select>

          {/* 审核阶段 */}
          <select
            value={filterStage}
            onChange={e => { setFilterStage(e.target.value); setPage(1) }}
            className="h-8 rounded-lg border border-border bg-background px-2.5 text-xs text-foreground
                       focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500/50
                       transition-all cursor-pointer"
          >
            <option value="">全部阶段</option>
            {Object.entries(STAGE_LABELS).map(([code, label]) => (
              <option key={code} value={code}>{label} ({code})</option>
            ))}
          </select>

          <span className="h-4 w-px bg-border mx-1" />

          {/* 日期范围 */}
          <input
            type="date"
            value={dateFrom}
            onChange={e => { setDateFrom(e.target.value); setPage(1) }}
            className="h-8 rounded-lg border border-border bg-background px-2.5 text-xs text-foreground
                       focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500/50
                       transition-all"
            title="提交时间起始"
          />
          <span className="text-xs text-muted-foreground">至</span>
          <input
            type="date"
            value={dateTo}
            onChange={e => { setDateTo(e.target.value); setPage(1) }}
            className="h-8 rounded-lg border border-border bg-background px-2.5 text-xs text-foreground
                       focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500/50
                       transition-all"
            title="提交时间截止"
          />

          {/* 清除筛选 */}
          {hasActiveFilters && (
            <button
              onClick={resetFilters}
              className="flex items-center gap-1 ml-1 h-8 rounded-lg px-2.5 text-xs text-muted-foreground
                         hover:text-foreground hover:bg-muted transition-all border border-transparent hover:border-border"
            >
              <X size={13} /> 重置
            </button>
          )}
        </div>
      </div>

      {/* 错误 */}
      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <XCircle size={16} />
          <span className="flex-1">{error}</span>
          <Button variant="outline" size="sm" onClick={load}>重试</Button>
        </div>
      )}

      {/* 表格 */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-4 rounded-xl border bg-card">
          <div className="size-12 rounded-full bg-muted flex items-center justify-center">
            <Loader2 className="animate-spin text-muted-foreground" size={24} />
          </div>
          <p className="text-sm text-muted-foreground">加载审核队列...</p>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-border shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  {[
                    { key: 'id', label: 'ID', className: 'w-16' },
                    { key: 'topic', label: '话题', className: '' },
                    { key: 'type', label: '类型', className: 'w-20' },
                    { key: 'stage', label: '审核节点', className: 'w-28' },
                    { key: 'status', label: '状态', className: 'w-24' },
                    { key: 'created_at', label: '提交时间', className: 'w-40' },
                    { key: 'updated_at', label: '更新时间', className: 'w-40' },
                  ].map(col => (
                    <th
                      key={col.key}
                      className={`text-center px-3 py-2.5 text-xs font-semibold text-muted-foreground
                                  cursor-pointer select-none hover:text-foreground hover:bg-muted/30
                                  transition-colors uppercase tracking-wide ${col.className}`}
                      onClick={() => handleSort(col.key)}
                    >
                      <span className="inline-flex items-center justify-center gap-1">
                        {col.label}
                        {sortIcon(col.key)}
                      </span>
                    </th>
                  ))}
                  <th className="text-center px-2 py-2.5 text-xs font-semibold text-muted-foreground uppercase tracking-wide w-16">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={8}>
                      <div className="flex flex-col items-center justify-center py-16 gap-3">
                        <div className="size-12 rounded-full bg-muted flex items-center justify-center">
                          <ClipboardCheck size={22} className="text-muted-foreground/50" />
                        </div>
                        <p className="text-sm text-muted-foreground">暂无审核记录</p>
                        {hasActiveFilters && (
                          <button
                            onClick={resetFilters}
                            className="text-xs text-primary hover:underline"
                          >
                            清除筛选条件
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ) : items.map(item => {
                  const badge = statusBadge(item.status)
                  return (
                    <tr
                      key={item.id}
                      className="border-b border-border/60 last:border-0 hover:bg-muted/30 cursor-pointer transition-colors group"
                      onClick={() => handleView(item)}
                    >
                      <td className="px-3 py-3 text-center">
                        <span className="text-xs font-mono text-muted-foreground/70">#{item.id}</span>
                      </td>
                      <td className="px-3 py-3">
                        <span className="font-medium text-foreground line-clamp-1 max-w-[300px] group-hover:text-primary transition-colors">
                          {item.topic}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-center">
                        <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium border ${
                          item.type === 'image'
                            ? 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-800'
                            : item.type === 'md'
                              ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800'
                              : 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800'
                        }`}>
                          {item.type === 'image' ? '贴图' : item.type === 'md' ? '去味' : '图文'}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-center">
                        <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium border
                                         bg-amber-50 text-amber-700 border-amber-200
                                         dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800">
                          {STAGE_LABELS[item.stage] || `阶段 ${item.stage}`}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-center">
                        <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium border ${badge.className}`}>
                          {badge.label}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-center">
                        <span className="text-xs text-muted-foreground">
                          {item.created_at
                            ? new Date(item.created_at * 1000).toLocaleString('zh-CN', {
                                month: '2-digit', day: '2-digit',
                                hour: '2-digit', minute: '2-digit',
                              })
                            : '--'}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-center">
                        <span className="text-xs text-muted-foreground">
                          {item.updated_at
                            ? new Date(item.updated_at * 1000).toLocaleString('zh-CN', {
                                month: '2-digit', day: '2-digit',
                                hour: '2-digit', minute: '2-digit',
                              })
                            : '--'}
                        </span>
                      </td>
                      <td className="px-2 py-3 text-center">
                        <button
                          onClick={e => { e.stopPropagation(); handleView(item) }}
                          className="inline-flex items-center rounded-lg p-1.5 text-muted-foreground
                                     hover:text-primary hover:bg-primary/5 transition-all"
                          title="查看审核"
                        >
                          <Eye size={15} />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* 分页 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between rounded-xl border bg-card px-4 py-3 shadow-sm">
              <span className="text-xs text-muted-foreground">
                第 <span className="font-semibold text-foreground">{page}</span> 页，
                共 <span className="font-semibold text-foreground">{totalPages}</span> 页
              </span>
              <div className="flex gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(p => p - 1)}
                  className="h-8 text-xs gap-1"
                >
                  <ChevronLeft size={14} /> 上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage(p => p + 1)}
                  className="h-8 text-xs gap-1"
                >
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
