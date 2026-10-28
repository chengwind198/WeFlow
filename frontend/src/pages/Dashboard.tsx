import { useNavigate } from 'react-router-dom'
import { PenLine, FileText, ClipboardCheck, Send } from 'lucide-react'
import { EmptyState } from '@/components/common/EmptyState'

/** 快捷入口卡片 */
function QuickAction({
  icon,
  label,
  description,
  path,
}: {
  icon: React.ReactNode
  label: string
  description: string
  path: string
}) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate(path)}
      className="flex flex-col items-start gap-2 rounded-lg border bg-card p-6 text-left
        shadow-surface hover:bg-secondary/50 transition-colors duration-150"
    >
      <div className="rounded-md bg-accent p-2 text-accent-foreground">
        {icon}
      </div>
      <h3 className="text-sm font-medium text-foreground">{label}</h3>
      <p className="text-xs text-muted-foreground">{description}</p>
    </button>
  )
}

export function Dashboard() {
  return (
    <div className="space-y-8">
      {/* 欢迎区 */}
      <div>
        <h2 className="text-page-title text-foreground">仪表盘</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          微信公众号 AI 创作工作台
        </p>
      </div>

      {/* 快捷入口 */}
      <div>
        <h3 className="mb-4 text-sm font-medium text-foreground">快捷入口</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <QuickAction
            icon={<PenLine size={20} />}
            label="新建文章"
            description="通过 AI 辅助写作，快速创建一篇公众号文章"
            path="/articles/new"
          />
          <QuickAction
            icon={<FileText size={20} />}
            label="AI任务列表"
            description="浏览和管理所有文章，继续编辑或发布"
            path="/articles"
          />
          <QuickAction
            icon={<ClipboardCheck size={20} />}
            label="人工审核队列"
            description="检查 AI 味评分未通过的文章"
            path="/review"
          />
          <QuickAction
            icon={<Send size={20} />}
            label="发布管理"
            description="将文章推送到微信草稿箱或多平台同步"
            path="/publishing"
          />
        </div>
      </div>

      {/* 最近任务区 */}
      <div>
        <h3 className="mb-4 text-sm font-medium text-foreground">最近任务</h3>
        <EmptyState
          icon={<FileText size={40} />}
          title="暂无任务"
          description="创建第一篇文章，开始你的 AI 写作之旅"
        />
      </div>
    </div>
  )
}
