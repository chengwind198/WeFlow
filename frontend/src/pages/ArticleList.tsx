import { FileText, Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { EmptyState } from '@/components/common/EmptyState'

export function ArticleList() {
  const navigate = useNavigate()

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-page-title text-foreground">文章列表</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            浏览和管理所有文章
          </p>
        </div>
        <button
          onClick={() => navigate('/articles/new')}
          className="flex items-center gap-2 rounded-md bg-primary px-4 py-2
            text-sm font-medium text-primary-foreground
            hover:opacity-90 transition-opacity duration-150"
        >
          <Plus size={16} />
          新建文章
        </button>
      </div>

      {/* 筛选区（占位） */}
      <div className="flex items-center gap-3">
        <div className="rounded-md border bg-card px-3 py-1.5 text-sm text-muted-foreground">
          全部
        </div>
        <div className="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-secondary cursor-pointer">
          草稿
        </div>
        <div className="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-secondary cursor-pointer">
          已发布
        </div>
      </div>

      {/* 文章列表（空状态） */}
      <EmptyState
        icon={<FileText size={40} />}
        title="还没有文章"
        description="点击「新建文章」按钮，通过 AI 辅助创作你的第一篇文章"
        action={
          <button
            onClick={() => navigate('/articles/new')}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground
              hover:opacity-90 transition-opacity duration-150"
          >
            开始创作
          </button>
        }
      />
    </div>
  )
}
