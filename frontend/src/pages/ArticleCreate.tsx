import { useState, useEffect, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sparkles, Send, Loader2, ChevronDown, ChevronRight, XCircle, RotateCw,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SmartSelect } from '@/components/SmartSelect'
import { getConfigConstants, createTask } from '@/lib/api'
import { useConfigStore } from '@/stores/useConfigStore'
import type { ConfigConstants } from '@/types/config'
import type { CreateTaskRequest } from '@/types/api'

export function ArticleCreate() {
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
  const articleReviewStages: number[] = account?.review_stages?.article || []

  // 表单字段
  const [topic, setTopic] = useState('')
  const [author, setAuthor] = useState('')
  const [theme, setTheme] = useState('')
  const [imageStyle, setImageStyle] = useState('')
  const [articleStructure, setArticleStructure] = useState('')
  const [openingHook, setOpeningHook] = useState('')
  const [voice, setVoice] = useState('')
  const [genre, setGenre] = useState('')
  const [autoImage, setAutoImage] = useState(true)
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
      setTheme(account.theme || '')
      setImageStyle(account.image_style || '')
      setArticleStructure(account.article_structure || '')
      setOpeningHook(account.opening_hook || '')
      setVoice(account.voice || '')
      setGenre(account.genre || '')
    }
  }, [account])

  // 重试加载
  const retryLoad = () => {
    setError(null)
    getConfigConstants()
      .then(res => {
        if (res.data) setConstants(res.data)
      })
      .catch(e => {
        setError(e instanceof Error ? e.message : '加载失败')
      })
  }

  // 提交
  const handleSubmit = async () => {
    if (!topic.trim()) {
      setError('请输入文章话题')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const body: CreateTaskRequest = {
        topic: topic.trim(),
        account: defaultKey,
        task_type: 'article',
        theme: theme || undefined,
        image_style: imageStyle || undefined,
        article_structure: articleStructure || undefined,
        opening_hook: openingHook || undefined,
        voice: voice || undefined,
        genre: genre || undefined,
        no_images: !autoImage,
        user_details: userDetails.trim() || undefined,
      }
      const res = await createTask(body)
      console.log('[ArticleCreate] API response:', res)
      // 后端业务错误（code != 200）
      if (res.code && res.code !== 200) {
        setError(res.message || '创建任务失败')
        return
      }
      // 从响应中提取 task_id
      const taskId = res.data?.task_id ?? null
      console.log('[ArticleCreate] taskId:', taskId, 'res.data:', res.data)
      if (taskId) {
        navigate(`/tasks/${taskId}`)
      } else {
        setError('创建成功但未获取到任务 ID，请检查后端日志')
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
          <Sparkles size={24} className="text-primary" />
          AI 一言成文
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          输入一句话，AI 自动完成选题、撰写、配图，并发布为微信草稿
        </p>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="flex items-center gap-3 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <XCircle size={16} />
          <span className="flex-1">{error}</span>
          {!hasConstants && (
            <Button variant="outline" size="sm" onClick={retryLoad}>
              <RotateCw size={14} /> 重试
            </Button>
          )}
        </div>
      )}

      {/* 话题 —— 核心输入区，突出 */}
      <div className="rounded-lg border-2 border-primary/20 bg-card p-6">
        <label className="block text-sm font-medium text-foreground mb-3">
          输入话题 <span className="text-destructive">*</span>
        </label>
        <textarea
          value={topic}
          onChange={e => setTopic(e.target.value)}
          className="w-full rounded-md border-0 bg-transparent text-lg text-foreground placeholder:text-muted-foreground/50 resize-none focus:outline-none"
          rows={2}
          placeholder="输入一句话，如：DeepSeek V4 模型发布，对比 GPT-5 的性能差异"
          autoFocus
        />
        <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={autoImage}
                onChange={e => setAutoImage(e.target.checked)}
                className="size-4 rounded border-input accent-primary"
              />
              <span className="text-sm text-muted-foreground">AI 自动配图</span>
            </label>
            {reviewEnabled && (
              <>
                <ReviewStageCheckbox
                  label="选题简报 (需审核)"
                  checked={articleReviewStages.includes(20)}
                />
                <ReviewStageCheckbox
                  label="文章草稿 (需审核)"
                  checked={articleReviewStages.includes(40)}
                />
                <ReviewStageCheckbox
                  label="配图 (需审核)"
                  checked={articleReviewStages.includes(60)}
                />
              </>
            )}
          </div>
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

            {/* 排版主题 */}
            {hasConstants && (
              <label className="block">
                <span className="text-xs font-medium text-muted-foreground mb-1 block">排版主题</span>
                <SmartSelect
                  value={theme}
                  options={constants.themes.map(t => ({
                    value: t.code,
                    label: `${t.label} (${t.code})`,
                    info: t.description,
                    tooltip: `${t.description}\ncode: ${t.code}`,
                  }))}
                  placeholder="自动 (由 AI 选择)"
                  onChange={setTheme}
                  previewType="theme"
                />
              </label>
            )}

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

            {/* 配图风格 */}
            {hasConstants && (
              <label className="block">
                <span className="text-xs font-medium text-muted-foreground mb-1 block">配图风格</span>
                <SmartSelect
                  value={imageStyle}
                  options={constants.image_styles
                    .filter(s => s.for_news)
                    .map(s => ({
                      value: s.code,
                      label: `${s.label} (${s.code})`,
                      info: `${s.keywords} · ${s.topics}`,
                      tooltip: `${s.keywords}\n${s.topics}\n密度: ${s.density}\ncode: ${s.code}`,
                    }))}
                  placeholder="自动 (由 AI 选择)"
                  onChange={setImageStyle}
                  previewType="image-style"
                />
              </label>
            )}

            {/* 文章结构 */}
            {hasConstants && (
              <label className="block">
                <span className="text-xs font-medium text-muted-foreground mb-1 block">文章结构</span>
                <select value={articleStructure} onChange={e => setArticleStructure(e.target.value)} className="input">
                  <option value="">自动 (由 AI 选择)</option>
                  {constants.article_structures.map(s => (
                    <option key={s.code} value={s.code}>{s.label} ({s.code})</option>
                  ))}
                </select>
              </label>
            )}

            {/* 开篇钩子 */}
            {hasConstants && (
              <label className="block">
                <span className="text-xs font-medium text-muted-foreground mb-1 block">开篇钩子</span>
                <select value={openingHook} onChange={e => setOpeningHook(e.target.value)} className="input">
                  <option value="">自动 (由 AI 选择)</option>
                  {constants.opening_hooks.map(h => (
                    <option key={h.code} value={h.code}>{h.label} ({h.code})</option>
                  ))}
                </select>
              </label>
            )}
          </div>

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

// ============================================================
// 内部组件
// ============================================================

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
