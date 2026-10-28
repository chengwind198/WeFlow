import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Loader2,
  ChevronLeft,
  ChevronRight,
  Trash2,
  ExternalLink,
  AlertTriangle,
  FileText,
  Plus,
  Pencil,
  Eye,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getDraftList, deleteDraft } from '@/lib/api'
import type { DraftItem } from '@/lib/api'

const PAGE_SIZE = 20

/** 格式化 Unix 时间戳为可读日期 */
function formatTime(ts: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${h}:${min}`
}

export function DraftList() {
  const navigate = useNavigate()
  const [items, setItems] = useState<DraftItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<DraftItem | null>(null)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getDraftList(offset, PAGE_SIZE)
      if (res.data) {
        setItems(res.data.items || [])
        setTotal(res.data.total_count || 0)
      } else {
        setError(res.message || '加载失败')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '请求失败，请检查后端服务是否启动')
    } finally {
      setLoading(false)
    }
  }, [offset])

  useEffect(() => {
    load()
  }, [load])

  /** 执行删除 */
  const handleDelete = async (draft: DraftItem) => {
    setConfirmDelete(null)
    setDeleting(draft.media_id)
    try {
      const res = await deleteDraft(draft.media_id)
      if (res.code === 0) {
        setItems((prev) => prev.filter((i) => i.media_id !== draft.media_id))
        setTotal((prev) => Math.max(0, prev - 1))
      } else {
        alert(res.message || '删除失败')
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : '删除请求失败')
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-page-title text-foreground">草稿列表</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            查看和管理微信公众号草稿箱中的文章
          </p>
        </div>
        <Button size="sm" onClick={() => navigate('/wechat/drafts/new')}>
          <Plus size={16} />
          新增草稿
        </Button>
      </div>

      {/* 删除确认弹窗 */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="mx-4 w-full max-w-md rounded-lg border bg-card p-6 shadow-lg">
            <div className="flex items-start gap-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-destructive/10">
                <AlertTriangle size={18} className="text-destructive" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-foreground">确认删除</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  确定要删除草稿「{confirmDelete.title || '(无标题)'}」吗？此操作不可撤销。
                </p>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirmDelete(null)}>
                取消
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => handleDelete(confirmDelete)}
              >
                确认删除
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* 加载状态 */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">加载中...</span>
        </div>
      )}

      {/* 错误状态 */}
      {!loading && error && (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <AlertTriangle size={36} className="text-destructive/70" />
          <p className="text-sm text-muted-foreground">{error}</p>
          <Button variant="outline" size="sm" onClick={load}>
            重试
          </Button>
        </div>
      )}

      {/* 数据表格 */}
      {!loading && !error && (
        <>
          {items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <FileText size={36} className="text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">草稿箱为空</p>
              <Button variant="outline" size="sm" onClick={() => navigate('/wechat/drafts/new')}>
                <Plus size={14} />
                创建第一个草稿
              </Button>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="px-4 py-3 text-left font-medium text-muted-foreground">标题</th>
                      <th className="px-4 py-3 text-left font-medium text-muted-foreground">作者</th>
                      <th className="px-4 py-3 text-left font-medium text-muted-foreground">更新时间</th>
                      <th className="px-4 py-3 text-center font-medium text-muted-foreground w-[120px]">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((draft) => (
                      <tr
                        key={draft.media_id}
                        className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                      >
                        <td className="px-4 py-3 max-w-[260px]">
                          <span
                            className="text-foreground truncate block"
                            title={draft.title}
                          >
                            {draft.title || '(无标题)'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                          {draft.author || '-'}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                          {formatTime(draft.update_time)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-center gap-0.5">
                            {/* 查看 */}
                            <button
                              onClick={() => navigate(`/wechat/drafts/${draft.media_id}?view=1`)}
                              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                              title="查看详情"
                            >
                              <Eye size={15} />
                            </button>
                            {/* 编辑 */}
                            <button
                              onClick={() => navigate(`/wechat/drafts/${draft.media_id}`)}
                              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                              title="编辑草稿"
                            >
                              <Pencil size={15} />
                            </button>
                            {/* 预览 */}
                            {draft.url && (
                              <a
                                href={draft.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                                title="在微信中预览"
                              >
                                <ExternalLink size={15} />
                              </a>
                            )}
                            {/* 删除 */}
                            <button
                              onClick={() => setConfirmDelete(draft)}
                              disabled={deleting === draft.media_id}
                              className="p-1.5 rounded-md text-destructive/70 hover:text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
                              title="删除草稿"
                            >
                              {deleting === draft.media_id ? (
                                <Loader2 size={15} className="animate-spin" />
                              ) : (
                                <Trash2 size={15} />
                              )}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* 分页 */}
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <span>
                  共 {total} 条，第 {currentPage}/{totalPages} 页
                </span>
                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="icon-sm"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    <ChevronLeft size={16} />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon-sm"
                    disabled={offset + PAGE_SIZE >= total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    <ChevronRight size={16} />
                  </Button>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
