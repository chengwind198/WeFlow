import { Edit3 } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { EmptyState } from '@/components/common/EmptyState'

export function ArticleEdit() {
  const { id } = useParams<{ id: string }>()

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-page-title text-foreground">编辑文章</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {id ? `文章 ID: ${id}` : '新建文章'}
        </p>
      </div>

      {/* TipTap 编辑器（Phase 2 实现） */}
      <EmptyState
        icon={<Edit3 size={40} />}
        title="TipTap 编辑器"
        description="富文本编辑器将在 Phase 2 中集成。届时支持 Markdown 编辑、实时微信样式预览、排版主题切换、配图风格选择等功能。"
      />
    </div>
  )
}
