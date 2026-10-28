import { X, Image, Info, FileText, Settings, Upload, Clock } from 'lucide-react'
import type { TaskImage } from '@/types/task'

const UPLOAD_STATUS_COLORS: Record<string, string> = {
  generated: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  generate_failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  uploaded: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  uploading: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
  pending: 'bg-muted text-muted-foreground',
  skipped: 'bg-muted text-muted-foreground',
}

function formatBytes(bytes: number): string {
  if (!bytes) return '--'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(ts: number): string {
  if (!ts) return '--'
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

interface FieldRowProps {
  label: string
  value: string | number | undefined
  mono?: boolean
}

function FieldRow({ label, value, mono }: FieldRowProps) {
  if (value === undefined || value === null || value === '') return null
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 border-b border-border/50 last:border-0">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className={`text-xs text-right break-all ${mono ? 'font-mono' : 'font-medium text-foreground'}`}>
        {String(value)}
      </span>
    </div>
  )
}

interface CodeBadgeProps {
  label: string
  value: string
}

function CodeBadge({ label, value }: CodeBadgeProps) {
  if (!value) return null
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] text-muted-foreground">{label}:</span>
      <code className="text-[10px] bg-muted rounded px-1 py-0.5 font-mono">{value}</code>
    </div>
  )
}

interface ImageDetailModalProps {
  image: TaskImage
  open: boolean
  onClose: () => void
}

export function ImageDetailModal({ image, open, onClose }: ImageDetailModalProps) {
  if (!open) return null

  const statusColor = UPLOAD_STATUS_COLORS[image.upload_status] || UPLOAD_STATUS_COLORS.pending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-card rounded-xl border border-border shadow-xl max-w-lg w-full mx-4 max-h-[85vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border sticky top-0 bg-card rounded-t-xl z-10">
          <div className="flex items-center gap-2">
            <Image size={18} className="text-primary" />
            <h3 className="font-semibold text-foreground">图片详情</h3>
            <span className="text-xs text-muted-foreground">#{image.seq}</span>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* 内容 */}
        <div className="p-5 space-y-4">
          {/* 基本信息 */}
          <Section title="基本信息" icon={<Info size={14} />}>
            <FieldRow label="ID" value={image.id} mono />
            <FieldRow label="Task ID" value={image.task_id} mono />
            <FieldRow label="Seq" value={image.seq} mono />
            <FieldRow label="Anchor" value={image.anchor} mono />
          </Section>

          {/* 内容 */}
          <Section title="内容" icon={<FileText size={14} />}>
            <div className="space-y-2">
              <div>
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Description</span>
                <p className="text-sm text-foreground mt-0.5 leading-relaxed">{image.description || '--'}</p>
              </div>
              <div>
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Prompt</span>
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed font-mono whitespace-pre-wrap break-all">
                  {image.prompt || '--'}
                </p>
              </div>
            </div>
          </Section>

          {/* 生图参数 */}
          <Section title="生图参数" icon={<Settings size={14} />}>
            <div className="flex flex-wrap gap-2">
              <CodeBadge label="provider" value={image.provider} />
              <CodeBadge label="model" value={image.model} />
              <CodeBadge label="style" value={image.image_style} />
              <CodeBadge label="size" value={image.size} />
            </div>
          </Section>

          {/* 文件信息 */}
          <Section title="文件信息" icon={<Image size={14} />}>
            <FieldRow label="路径" value={image.local_path} mono />
            <FieldRow label="大小" value={formatBytes(image.local_size)} />
            <FieldRow label="尺寸" value={image.width && image.height ? `${image.width}×${image.height}` : '--'} />
            <FieldRow label="格式" value={image.format} />
          </Section>

          {/* 上传状态 */}
          <Section title="上传状态" icon={<Upload size={14} />}>
            <div className="flex items-center gap-2 mb-2">
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${statusColor}`}>
                {image.upload_status}
              </span>
              {image.is_cover === 1 && (
                <span className="text-[10px] bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 rounded px-1.5 py-0.5">
                  封面图
                </span>
              )}
            </div>
            <FieldRow label="CDN URL" value={image.upload_cdn_url} mono />
            <FieldRow label="Media ID" value={image.upload_media_id} mono />
          </Section>

          {/* 时间 */}
          <Section title="时间" icon={<Clock size={14} />}>
            <FieldRow label="创建时间" value={formatTime(image.created_at)} />
          </Section>
        </div>
      </div>
    </div>
  )
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wider">
        {icon}
        {title}
      </div>
      <div className="bg-muted/30 rounded-lg p-3 border border-border/50">
        {children}
      </div>
    </div>
  )
}
