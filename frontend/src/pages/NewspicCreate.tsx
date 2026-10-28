import { useState, useEffect, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Send, Loader2, ChevronDown, ChevronRight, XCircle, Image,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SmartSelect } from '@/components/SmartSelect'
import { getConfigConstants, createTask } from '@/lib/api'
import { useConfigStore } from '@/stores/useConfigStore'
import type { ConfigConstants } from '@/types/config'
import type { CreateTaskRequest } from '@/types/api'

export function NewspicCreate() {
  const navigate = useNavigate()
  const config = useConfigStore(s => s.config)
  const [constants, setConstants] = useState<ConfigConstants | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 当前账号配置
  const defaultKey = config?.default || 'main'
  const account = config?.accounts?.[defaultKey]

  // 审核配置（只读展示，不可修改）
  const reviewEnabled = account?.review_enabled || false
  const imageReviewStages: number[] = account?.review_stages?.image || []

  // 表单字段
  const [topic, setTopic] = useState('')
  const [author, setAuthor] = useState('')
  const [newspicImageStyle, setNewspicImageStyle] = useState('')
  const [voice, setVoice] = useState('')
  const [genre, setGenre] = useState('')
  const [userDetails, setUserDetails] = useState('')

  // 加载常量元数据
  useEffect(() => {
    getConfigConstants()
      .then(res => { if (res.data) setConstants(res.data) })
      .catch(() => {})
  }, [])

  // 从账号配置加载默认值
  useEffect(() => {
    if (account) {
      setAuthor(account.author || '')
      setNewspicImageStyle(account.newspic_image_style || '')
      setVoice(account.voice || '')
      setGenre(account.genre || '')
    }
  }, [account])

  // 提交
  const handleSubmit = async () => {
    if (!topic.trim()) {
      setError('请输入贴图话题')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const body: CreateTaskRequest = {
        topic: topic.trim(),
        account: defaultKey,
        task_type: 'image',
        image_style: newspicImageStyle || undefined,
        voice: voice || undefined,
        genre: genre || undefined,
        user_details: userDetails.trim() || undefined,
      }
      const res = await createTask(body)
      console.log('[NewspicCreate] API response:', res)
      if (res.code && res.code !== 200) {
        setError(res.message || '创建任务失败')
        return
      }
      const taskId = res.data?.task_id ?? null
      console.log('[NewspicCreate] taskId:', taskId)
      if (taskId) {
        navigate(`/newspic/${taskId}`)
      } else {
        setError('创建成功但未获取到任务 ID')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  const hasConstants = constants != null

  return (
    <div className="space-y-6 pb-8">
      {/* 页头 */}
      <div>
        <h2 className="text-page-title text-foreground flex items-center gap-2">
          <Image size={24} className="text-primary" />
          AI 一言贴图
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          输入一句话，AI 自动生成多张信息图卡片，并发布为微信图片消息
        </p>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="flex items-center gap-3 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <XCircle size={16} />
          <span className="flex-1">{error}</span>
        </div>
      )}

      {/* 话题 —— 核心输入区 */}
      <div className="rounded-lg border-2 border-primary/20 bg-card p-6">
        <label className="block text-sm font-medium text-foreground mb-3">
          输入话题 <span className="text-destructive">*</span>
        </label>
        <textarea
          value={topic}
          onChange={e => setTopic(e.target.value)}
          className="w-full rounded-md border-0 bg-transparent text-lg text-foreground placeholder:text-muted-foreground/50 resize-none focus:outline-none"
          rows={2}
          placeholder="输入一句话，如：iPhone 17 十大升级亮点"
          autoFocus
        />
        <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
          {reviewEnabled ? (
            <div className="flex items-center gap-4">
              <ReviewStageCheckbox
                label="选题简报 (需审核)"
                checked={imageReviewStages.includes(20)}
              />
              <ReviewStageCheckbox
                label="贴图 (需审核)"
                checked={imageReviewStages.includes(60)}
              />
            </div>
          ) : (
            <span />
          )}
          <Button onClick={handleSubmit} disabled={submitting || !topic.trim()} size="lg">
            {submitting ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Send size={18} />
            )}
            {submitting ? '正在创建...' : '开始生成'}
          </Button>
        </div>
      </div>

      {/* 补充参考素材 */}
      <CollapsibleSection title="补充要求或素材（可选）" defaultOpen={true}>
        <label className="block">
          <textarea
            value={userDetails}
            onChange={e => setUserDetails(e.target.value)}
            className="input min-h-[60px] resize-y text-sm"
            rows={2}
            placeholder="补充素材或特殊要求（可选）"
          />
        </label>
      </CollapsibleSection>

      {/* 创作默认配置 */}
      <CollapsibleSection title="创作默认配置 (可修改)" defaultOpen={true}>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {/* 作者 */}
            <label className="block">
              <span className="text-xs font-medium text-muted-foreground mb-1 block">作者</span>
              <input
                type="text"
                value={author}
                onChange={e => setAuthor(e.target.value)}
                className="input"
                placeholder="作者名称"
              />
            </label>

            {/* 贴图风格 */}
            {hasConstants && (
              <label className="block">
                <span className="text-xs font-medium text-muted-foreground mb-1 block">贴图风格</span>
                <SmartSelect
                  value={newspicImageStyle}
                  options={constants.image_styles
                    .filter(s => s.for_newspic)
                    .map(s => ({
                      value: s.code,
                      label: `${s.label} (${s.code})`,
                      info: `${s.keywords} · ${s.topics}`,
                      tooltip: `${s.keywords}\n${s.topics}\n密度: ${s.density}\ncode: ${s.code}`,
                    }))}
                  placeholder="自动 (由 AI 选择)"
                  onChange={setNewspicImageStyle}
                  previewType="image-style"
                />
              </label>
            )}
          </div>

          {/* 文章体裁 */}
          {hasConstants && (
            <label className="block">
              <span className="text-xs font-medium text-muted-foreground mb-1 block">文章体裁</span>
              <select value={genre} onChange={e => setGenre(e.target.value)} className="input">
                <option value="">自动 (由AI选择)</option>
                {constants.genres.map(g => (
                  <option key={g.code} value={g.code}>{g.label} ({g.code})</option>
                ))}
              </select>
            </label>
          )}

          {/* 语气风格 */}
          <label className="block">
            <span className="text-xs font-medium text-muted-foreground mb-1 block">语气风格 (voice)</span>
            <textarea
              value={voice}
              onChange={e => setVoice(e.target.value)}
              className="input min-h-[60px] resize-y text-sm"
              rows={2}
              placeholder="描述作者的语气风格、身份、写作偏好..."
            />
          </label>
        </div>
      </CollapsibleSection>
    </div>
  )
}

function CollapsibleSection({
  title, children, defaultOpen = true,
}: {
  title: string; children: ReactNode; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        {open ? <ChevronDown size={16} className="text-muted-foreground" /> : <ChevronRight size={16} className="text-muted-foreground" />}
        <span className="text-sm font-medium text-foreground">{title}</span>
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  )
}

/** 审核阶段复选框（只读展示） */
function ReviewStageCheckbox({ label, checked }: { label: string; checked: boolean }) {
  return (
    <label className="flex items-center gap-2 cursor-not-allowed opacity-70">
      <input
        type="checkbox"
        checked={checked}
        disabled
        className="size-4 rounded border-input accent-amber-500 cursor-not-allowed"
      />
      <span className="text-sm text-muted-foreground">{label}</span>
    </label>
  )
}
