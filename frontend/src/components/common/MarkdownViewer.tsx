import { useState } from 'react'
import { TiptapEditor } from 'shadcn-tiptap-editor'
import { Eye, FileCode } from 'lucide-react'

type ViewMode = 'preview' | 'source'

interface MarkdownViewerProps {
  content: string
  className?: string
}

export function MarkdownViewer({ content, className = '' }: MarkdownViewerProps) {
  const [mode, setMode] = useState<ViewMode>('source')

  if (!content) return null

  return (
    <div className={`bg-card rounded-lg border border-border overflow-hidden ${className}`}>
      {/* 模式切换 */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-border bg-muted/30">
        <ModeButton active={mode === 'source'} onClick={() => setMode('source')} icon={<FileCode size={14} />} label="内容" />
        <ModeButton active={mode === 'preview'} onClick={() => setMode('preview')} icon={<Eye size={14} />} label="预览" />
      </div>

      {/* 内容区 */}
      {mode === 'source' && (
        <pre className="whitespace-pre-wrap font-mono text-xs text-foreground leading-relaxed p-5 min-h-[200px] max-h-[70vh] overflow-auto">
          {content}
        </pre>
      )}

      {mode === 'preview' && (
        <TiptapEditor content={content} editable={false} placeholder="" />
      )}
    </div>
  )
}

function ModeButton({ active, onClick, icon, label }: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
        active
          ? 'bg-background text-foreground shadow-sm border border-border'
          : 'text-muted-foreground hover:text-foreground hover:bg-background/50'
      }`}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  )
}
