import { Eye } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { EmptyState } from '@/components/common/EmptyState'

export function ArticlePreview() {
  const { id } = useParams<{ id: string }>()

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-page-title text-foreground">文章预览</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          微信公众号样式预览 {id && `· 文章 ID: ${id}`}
        </p>
      </div>

      <EmptyState
        icon={<Eye size={40} />}
        title="微信样式预览"
        description="此功能将在 Phase 2 中实现。届时可以在此查看文章在微信公众号中的实际显示效果。"
      />
    </div>
  )
}
