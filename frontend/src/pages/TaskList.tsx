import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Search, ChevronLeft, ChevronRight, X, Trash2, AlertTriangle, ArrowUp, ArrowDown, CheckCircle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getTasks, deleteTask } from '@/lib/api'
import { STATUS_LABELS } from '@/lib/constants'
import type { Task } from '@/types/task'

const PAGE_SIZE = 20

/** 可同步到多平台的任务状态（与 SyncCreate 搜索条件一致） */
const SYNCABLE_STATUSES = [60, 70, 80, 85, 88, 90]

// 所有状态选项
const STATUS_OPTIONS = Object.entries(STATUS_LABELS).map(([code, label]) => ({
  code: Number(code), label: `${label} (${code})`,
}))

export function TaskList() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<Task[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 筛选
  const [filterAccount, setFilterAccount] = useState('')
  const [filterKeyword, setFilterKeyword] = useState('')
  const [filterStatus, setFilterStatus] = useState<string[]>([])
  const [filterAfter, setFilterAfter] = useState('')
  const [filterBefore, setFilterBefore] = useState('')
  const [statusOpen, setStatusOpen] = useState(false)

  // 账号列表（从接口获取）
  const [accounts, setAccounts] = useState<string[]>([])

  // 排序
  const [sortBy, setSortBy] = useState('created_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  // 删除确认
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, string | number> = {
        page,
        pageSize: PAGE_SIZE,
      }
      if (filterAccount) params.account = filterAccount
      if (filterKeyword) params.keyword = filterKeyword
      if (filterStatus.length > 0 && filterStatus.length < STATUS_OPTIONS.length) {
        params.status = filterStatus.join(',')
      }
      if (filterAfter) params.created_after = Math.floor(new Date(filterAfter).getTime() / 1000)
      if (filterBefore) params.created_before = Math.floor(new Date(filterBefore).getTime() / 1000) + 86399
      params.sort_by = sortBy
      params.sort_order = sortOrder

      const res = await getTasks(params as never)
      if (res.data) {
        setTasks((res.data.items || []) as Task[])
        setTotal(res.data.total || 0)
      }
      // 收集账号列表
      if (accounts.length === 0) {
        // 从任务中提取唯一账号（首次加载后）
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, filterAccount, filterKeyword, filterStatus, filterAfter, filterBefore, accounts.length, sortBy, sortOrder])

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
    return sortOrder === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />
  }

  // 收集账号
  useEffect(() => {
    if (tasks.length > 0 && accounts.length === 0) {
      setAccounts([...new Set(tasks.map(t => t.account))].sort())
    }
  }, [tasks, accounts.length])

  const toggleStatus = (code: number) => {
    setFilterStatus(prev => {
      const s = String(code)
      return prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]
    })
    setPage(1)
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      const res = await deleteTask(deleteTarget.id)
      setDeleteTarget(null)
      if (res.code === 0) {
        setToast({ type: 'success', message: `任务 #${deleteTarget.id} 已删除` })
      } else {
        setToast({ type: 'error', message: res.message || '删除失败' })
      }
      load()
    } catch (e) {
      setDeleteTarget(null)
      setToast({ type: 'error', message: e instanceof Error ? e.message : '删除请求失败' })
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="space-y-4 pb-8">
      <div>
        <h2 className="text-page-title text-foreground">AI任务列表</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          共 {total} 条记录 · 第 {page}/{totalPages} 页
        </p>
      </div>

      {/* Toast */}
      {toast && (
        <div className={`flex items-center gap-3 rounded-lg border px-4 py-3 shadow-overlay transition-all ${
          toast.type === 'success'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
            : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300'
        }`}>
          {toast.type === 'success' ? <CheckCircle size={16} /> : <AlertTriangle size={16} />}
          <span className="text-sm flex-1">{toast.message}</span>
          <button onClick={() => setToast(null)} className="text-current opacity-50 hover:opacity-100">
            <X size={14} />
          </button>
        </div>
      )}

      {/* 筛选栏 */}
      <div className="flex flex-wrap items-center gap-2">
        {/* 账号 */}
        <select
          value={filterAccount}
          onChange={e => { setFilterAccount(e.target.value); setPage(1) }}
          className="input w-auto min-w-[120px]"
        >
          <option value="">全部账号</option>
          {accounts.map(a => <option key={a} value={a}>{a}</option>)}
        </select>

        {/* 关键词 */}
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={filterKeyword}
            onChange={e => { setFilterKeyword(e.target.value); setPage(1) }}
            className="input pl-8"
            placeholder="搜索话题或标题..."
            onKeyDown={e => { if (e.key === 'Enter') load() }}
          />
        </div>

        {/* 状态多选 */}
        <div className="relative">
          <button
            onClick={() => setStatusOpen(!statusOpen)}
            className="input w-auto min-w-[120px] text-left"
          >
            {filterStatus.length === 0 || filterStatus.length === STATUS_OPTIONS.length
              ? '全部状态'
              : `${filterStatus.length} 个状态`}
          </button>
          {statusOpen && (
            <div className="absolute top-full mt-1 z-10 bg-card border border-border rounded-md shadow-overlay p-2 w-56 max-h-60 overflow-y-auto">
              {STATUS_OPTIONS.map(opt => (
                <label key={opt.code} className="flex items-center gap-2 px-2 py-1 text-xs hover:bg-muted rounded cursor-pointer">
                  <input
                    type="checkbox"
                    checked={filterStatus.includes(String(opt.code))}
                    onChange={() => toggleStatus(opt.code)}
                    className="size-3.5"
                  />
                  {opt.label}
                </label>
              ))}
              <div className="border-t border-border mt-1 pt-1 flex gap-2 px-2">
                <button onClick={() => { setFilterStatus([]); setPage(1) }} className="text-xs text-primary">全选</button>
                <button onClick={() => { setFilterStatus(STATUS_OPTIONS.map(o => String(o.code))); setPage(1) }} className="text-xs text-primary">全不选</button>
              </div>
            </div>
          )}
        </div>

        {/* 时间范围 */}
        <input type="date" value={filterAfter} onChange={e => { setFilterAfter(e.target.value); setPage(1) }} className="input w-auto" title="开始日期" />
        <span className="text-xs text-muted-foreground">至</span>
        <input type="date" value={filterBefore} onChange={e => { setFilterBefore(e.target.value); setPage(1) }} className="input w-auto" title="结束日期" />

        {/* 清除 */}
        {(filterAccount || filterKeyword || filterStatus.length > 0 || filterAfter || filterBefore) && (
          <button onClick={() => {
            setFilterAccount(''); setFilterKeyword(''); setFilterStatus([])
            setFilterAfter(''); setFilterBefore(''); setPage(1)
          }} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <X size={14} /> 清除
          </button>
        )}
      </div>

      {/* 删除确认弹窗 */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="mx-4 w-full max-w-md rounded-lg border bg-card p-6 shadow-lg">
            <div className="flex items-start gap-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-destructive/10">
                <AlertTriangle size={18} className="text-destructive" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-foreground">确认删除任务</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  确定要删除任务 #{deleteTarget.id}「{deleteTarget.topic}」吗？此操作将删除所有关联数据及产物文件，不可撤销。
                </p>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                取消
              </Button>
              <Button variant="destructive" size="sm" onClick={handleDelete} disabled={deleting}>
                {deleting ? <Loader2 size={14} className="animate-spin mr-1" /> : null}
                确认删除
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* 表格 */}
      {error ? (
        <div className="text-sm text-destructive">{error}</div>
      ) : loading ? (
        <div className="flex justify-center py-16"><Loader2 className="animate-spin text-muted-foreground" size={28} /></div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  {[
                    { key: 'id', label: 'ID', className: 'w-16' },
                    { key: 'topic', label: '话题', className: '' },
                    { key: 'type', label: '类型', className: 'w-20' },
                    { key: 'account', label: '账号', className: 'w-16' },
                    { key: 'status', label: '状态', className: 'w-24' },
                    { key: 'created_at', label: '创建时间', className: 'w-36' },
                    { key: 'updated_at', label: '更新时间', className: 'w-36' },
                  ].map(col => (
                    <th key={col.key} className={`text-left px-3 py-2 text-xs font-medium text-muted-foreground cursor-pointer select-none hover:text-foreground hover:bg-muted/50 transition-colors ${col.className}`}
                      onClick={() => handleSort(col.key)}>
                      <span className="inline-flex items-center gap-1">
                        {col.label}
                        {sortIcon(col.key)}
                      </span>
                    </th>
                  ))}
                  <th className="text-center px-2 py-2 text-xs font-medium text-muted-foreground w-16">操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 ? (
                  <tr><td colSpan={8} className="text-center py-12 text-muted-foreground">暂无数据</td></tr>
                ) : tasks.map(task => (
                  <tr
                    key={task.id}
                    onClick={() => navigate(task.type === 'image' ? `/newspic/${task.id}` : task.type === 'md' ? `/md/${task.id}` : `/tasks/${task.id}`)}
                    className="border-b border-border last:border-0 hover:bg-muted/50 cursor-pointer transition-colors"
                  >
                    <td className="px-3 py-2 text-xs text-muted-foreground">#{task.id}</td>
                    <td className="px-3 py-2 font-medium text-foreground truncate max-w-[300px]">{task.topic}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${task.type === 'image' ? 'bg-purple-50 text-purple-700 dark:bg-purple-950 dark:text-purple-300' : task.type === 'md' ? 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300' : 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300'}`}>
                        {task.type === 'image' ? '贴图' : task.type === 'md' ? '去味' : '图文'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{task.account}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        task.status >= 80 ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300' :
                        task.status === 0 ? 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300' :
                        'bg-muted text-muted-foreground'
                      }`}>
                        {task.status_label || STATUS_LABELS[task.status] || task.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {task.created_at ? new Date(task.created_at * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '--'}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {task.updated_at ? new Date(task.updated_at * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '--'}
                    </td>
                    <td className="px-2 py-2 text-center">
                      <div className="flex items-center justify-center gap-0.5">
                        {SYNCABLE_STATUSES.includes(task.status) && (
                          <button
                            onClick={e => { e.stopPropagation(); navigate(`/sync/new?taskId=${task.id}`) }}
                            className="p-1 rounded text-muted-foreground/60 hover:text-primary hover:bg-primary/10 transition-colors"
                            title="同步到其他平台"
                          >
                            <RefreshCw size={14} />
                          </button>
                        )}
                        <button
                          onClick={e => { e.stopPropagation(); setDeleteTarget(task) }}
                          className="p-1 rounded text-muted-foreground/60 hover:text-destructive hover:bg-destructive/10 transition-colors"
                          title="删除任务"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
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
