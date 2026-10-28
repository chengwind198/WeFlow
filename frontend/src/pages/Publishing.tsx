import { Send } from 'lucide-react'
import { EmptyState } from '@/components/common/EmptyState'

export function Publishing() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-page-title text-foreground">发布管理</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          管理文章发布状态，推送到微信草稿箱或同步到多平台
        </p>
      </div>

      <EmptyState
        icon={<Send size={40} />}
        title="暂无发布任务"
        description="完成 AI 味审核后的文章可以在此一键发布到微信草稿箱，并同步到知乎、掘金、CSDN 等平台。"
      />
    </div>
  )
}
