/**
 * 审核详情页 —— 独立于任务详情，展示审核内容并提供通过/驳回操作。
 * 路由: /review/:id
 */
import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Loader2, ClipboardCheck, ThumbsUp,
  ExternalLink, CheckCircle, AlertTriangle, Clock,
  Save, Eye, FileText, Image, Plus,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getReviewDetail, approveReview, getTask, updateTaskBrief, updateTaskArticle, replaceTaskImage, regenerateTaskImage, saveNewspicReview, appendTaskImages } from '@/lib/api'
import { TiptapEditor } from 'shadcn-tiptap-editor'
import { MarkdownViewer } from '@/components/common/MarkdownViewer'
import { ImageReviewCard } from '@/components/common/ImageReviewCard'
import { STATUS_LABELS } from '@/lib/constants'
import type { ReviewDetail as ReviewDetailType, TaskDetail as TaskDetailType, TaskImage } from '@/types/task'

// ============================================================
// 审核阶段标签
// ============================================================
const REVIEW_STAGE_LABELS: Record<number, string> = {
  20: '选题简报已就绪',
  35: '卡片已规划',
  40: '文章已就绪',
  60: '配图已生成',
  85: 'AI 味检测未通过',
}

// ============================================================
// 辅助函数
// ============================================================

/** 新增图片按钮：上传到任务 images/ 目录，锚点追加到文章末尾（article）或作为末尾新卡片（newspic） */
function AppendImageButton({ disabled, onAppend }: { disabled: boolean; onAppend: (files: FileList | null) => void }) {
  return (
    <label className={`inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/5 px-2 py-1 text-[11px] font-medium text-primary cursor-pointer hover:bg-primary/10 transition-colors ${disabled ? 'opacity-50 pointer-events-none' : ''}`}>
      <Plus size={12} />
      新增图片
      <input
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        disabled={disabled}
        onChange={e => onAppend(e.target.files)}
      />
    </label>
  )
}

/** 从编辑器内容（HTML 或 Markdown）中提取标题（首个 h1 / # heading） */
function extractTitleFromContent(content: string): string {
  if (!content) return ''
  // 尝试 HTML h1
  const h1Match = content.match(/<h1[^>]*>(.*?)<\/h1>/i)
  if (h1Match) return h1Match[1].replace(/<[^>]*>/g, '').trim()
  // 尝试 Markdown # heading
  const mdMatch = content.match(/^#\s+(.+?)(?:\n|$)/m)
  if (mdMatch) return mdMatch[1].trim()
  // 回退：第一个非空非标签行
  const firstLine = content.split('\n').find(l => l.trim() && !l.trim().startsWith('<'))
  return firstLine ? firstLine.replace(/<[^>]*>/g, '').trim() : ''
}

/** 从编辑器内容中提取摘要（去掉标题后的正文部分） */
function extractShortTextFromContent(content: string): string {
  if (!content) return ''
  let text = content
  // 移除 HTML h1
  text = text.replace(/<h1[^>]*>.*?<\/h1>/gi, '')
  // 移除 Markdown # heading 行
  text = text.replace(/^#\s+.+$/m, '')
  // 清理标签并去除首尾空白
  text = text.replace(/<[^>]*>/g, '').trim()
  return text
}

// ============================================================
// 页面
// ============================================================
export function ReviewDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const reviewId = Number(id)

  const [review, setReview] = useState<ReviewDetailType | null>(null)
  const [task, setTask] = useState<TaskDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 审核操作
  const [approved, setApproved] = useState(false)
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [showApproveConfirm, setShowApproveConfirm] = useState(false)

  // 内容编辑（stage 20/40 待审核时默认可编辑）
  const [editContent, setEditContent] = useState('')
  const [contentKey, setContentKey] = useState(0)             // 强制 TiptapEditor 重新挂载
  const [editMode, setEditMode] = useState<'visual' | 'source'>('visual')
  const [saving, setSaving] = useState(false)
  const [showSaveConfirm, setShowSaveConfirm] = useState(false)

  // 图片审核（stage=60 或 image 类型 stage=40）
  const [reviewImages, setReviewImages] = useState<TaskImage[]>([])
  const [imageOpsDisabled, setImageOpsDisabled] = useState(false)
  const [reviewTab, setReviewTab] = useState<'content' | 'images'>('content')

  // newspic stage 20 卡片编辑
  const [formCards, setFormCards] = useState<Array<{id: number, seq: number, description: string}>>([])

  const load = useCallback(async () => {
    if (!reviewId) return
    setLoading(true)
    setError(null)
    try {
      const res = await getReviewDetail(reviewId)
      if (!res.data) {
        setError('审核记录不存在')
        return
      }
      setReview(res.data)
      // 同时加载关联任务，用于内容预览
      if (res.data.task_id) {
        try {
          const taskRes = await getTask(res.data.task_id)
          if (taskRes.data) setTask(taskRes.data)
        } catch { /* 任务加载失败不影响审核页 */ }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [reviewId])

  useEffect(() => { load() }, [load])

  // stage=60 或 image 类型 stage=20/40 时加载图片列表
  useEffect(() => {
    const shouldLoadImages = review?.stage === 60 || (review?.stage === 40 && review?.type === 'article') || (review?.stage === 20 && review?.type === 'image')
    if (shouldLoadImages && review?.images) {
      setReviewImages(review.images)
    }
  }, [review])

  // 可编辑阶段（20/40 待审核）加载后自动填入初始内容（剥离 YAML frontmatter）
  useEffect(() => {
    if (!review || !task) return
    if (review.status !== 'pending') return
    const stripFrontmatter = (md: string) => {
      // 去掉开头的 YAML frontmatter（--- ... ---）
      const trimmed = md.trimStart()
      if (trimmed.startsWith('---')) {
        const end = trimmed.indexOf('---', 3)
        if (end !== -1) return trimmed.slice(end + 3).trimStart()
      }
      return md
    }
    if (review.stage === 20 && review.type === 'image') {
      // image 模式 stage=20 由下方的 useEffect 处理（title + short_text 格式）
      return
    }
    if (review.stage === 20 && task.brief) {
      setEditContent(stripFrontmatter(task.brief))
      setContentKey(k => k + 1)
    } else if (review.stage === 40 && task.markdown) {
      setEditContent(stripFrontmatter(task.markdown))
      setContentKey(k => k + 1)
    }
  }, [review, task])

  // newspic stage 20 审核：初始化结构化表单数据
  useEffect(() => {
    if (!review || review.status !== 'pending') return
    if (review.stage === 20 && review.type === 'image') {
      const title = review.task_title || ''
      const shortText = review.short_text || ''
      const combined = `# ${title}\n\n${shortText}`
      setEditContent(combined)
      setContentKey(k => k + 1)
      if (review.cards && review.cards.length > 0) {
        setFormCards(review.cards.map(c => ({ id: c.id, seq: c.seq, description: c.description || '' })))
      } else {
        setFormCards([])
      }
    }
  }, [review])

  // 图片审核操作
  const handleImageReplace = async (imageId: number, file: File) => {
    if (!review) return
    setImageOpsDisabled(true)
    try {
      await replaceTaskImage(review.task_id, imageId, file)
      // 刷新图片列表以获取最新元数据
      const updated = await getReviewDetail(review.id)
      if (updated.data?.images) {
        setReviewImages(updated.data.images)
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : '替换失败')
    } finally {
      setImageOpsDisabled(false)
    }
  }

  const handleImageRegenerate = async (imageId: number, prompt: string) => {
    console.log('[ReviewDetail] handleImageRegenerate called:', { reviewId: review?.id, taskId: review?.task_id, imageId, prompt })
    if (!review) {
      console.warn('[ReviewDetail] handleImageRegenerate: review is null, 跳过')
      return
    }
    setImageOpsDisabled(true)
    try {
      console.log('[ReviewDetail] 调用 regenerateTaskImage API...')
      const res = await regenerateTaskImage(review.task_id, imageId, prompt)
      console.log('[ReviewDetail] regenerateTaskImage 响应:', res)
      // 刷新图片列表
      const updated = await getReviewDetail(review.id)
      if (updated.data?.images) {
        setReviewImages(updated.data.images)
      }
    } catch (e) {
      console.error('[ReviewDetail] regenerateTaskImage 失败:', e)
      throw e
    } finally {
      setImageOpsDisabled(false)
    }
  }

  const handleImageRefresh = async () => {
    if (!review) return
    try {
      const updated = await getReviewDetail(review.id)
      if (updated.data?.images) {
        setReviewImages(updated.data.images)
      }
    } catch { /* 刷新失败不影响 */ }
  }

  /** 新增图片：上传到任务 images/ 目录，锚点追加到文章末尾（article）或作为末尾新卡片（newspic） */
  const handleAppendImages = async (fileList: FileList | null) => {
    if (!review) return
    const list = Array.from(fileList ?? []).filter(f => f.type.startsWith('image/'))
    if (list.length === 0) return
    setImageOpsDisabled(true)
    try {
      await appendTaskImages(review.task_id, list)
      await handleImageRefresh()
    } catch (e) {
      alert(e instanceof Error ? e.message : '新增图片失败')
    } finally {
      setImageOpsDisabled(false)
    }
  }

  // 通过审核
  const handleApprove = async () => {
    if (!review) return
    setSubmitting(true)
    setShowApproveConfirm(false)
    try {
      const res = await approveReview(review.id, { reviewer: '', comment })
      if (res.code === 0) {
        setApproved(true)
        const updated = await getReviewDetail(review.id)
        if (updated.data) setReview(updated.data)
      } else {
        alert(res.message || '操作失败')
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  // --- 加载态 ---
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-4">
        <div className="size-12 rounded-full bg-muted flex items-center justify-center">
          <Loader2 className="animate-spin text-muted-foreground" size={24} />
        </div>
        <p className="text-sm text-muted-foreground">加载审核详情...</p>
      </div>
    )
  }

  if (error || !review) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-4">
        <div className="size-14 rounded-2xl bg-destructive/10 flex items-center justify-center">
          <AlertTriangle size={28} className="text-destructive" />
        </div>
        <p className="text-sm text-muted-foreground">{error || '无法加载审核记录'}</p>
        <Button variant="outline" size="sm" onClick={() => navigate('/review')}>
          <ArrowLeft size={14} className="mr-1.5" /> 返回人工审核队列
        </Button>
      </div>
    )
  }

  const isPending = review.status === 'pending'
  const isNewspic = review.type === 'image'
  const stageLabel = REVIEW_STAGE_LABELS[review.stage] || `阶段 ${review.stage}`
  const resolved = approved || (review.status !== 'pending' ? review.status : null)
  const taskPath = isNewspic ? `/newspic/${review.task_id}` : `/tasks/${review.task_id}`

  // 可编辑阶段：20（选题简报）和 40（文章草稿）
  const isEditable = ((review.stage === 20 && !isNewspic) || review.stage === 40) && isPending
  const editLabel = review.stage === 20 ? '选题简报' : '文章草稿'

  return (
    <>
    <div className="space-y-4 pb-8">
      {/* 顶栏 */}
      <div className="flex items-center justify-between rounded-xl border bg-card px-5 py-3 shadow-sm">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/review')}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-all"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <h2 className="text-lg font-semibold text-foreground">审核详情</h2>
            <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <span className="size-1.5 rounded-full bg-muted-foreground/40" />
                审核 #{review.id}
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="size-1.5 rounded-full bg-muted-foreground/40" />
                任务 #{review.task_id}
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="size-1.5 rounded-full bg-muted-foreground/40" />
                {review.account}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* 审核状态 */}
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
            isPending
              ? 'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800'
              : 'bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800'
          }`}>
            {isPending ? <Clock size={12} /> : <CheckCircle size={12} />}
            {isPending ? '待审核' : '已通过'}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(taskPath)}
            className="gap-1.5"
          >
            <ExternalLink size={14} />
            任务详情
          </Button>
        </div>
      </div>

      {/* 审核面板 */}
      <div className={`rounded-xl border-2 shadow-sm p-5 space-y-4 ${
        isPending
          ? 'border-amber-200 bg-amber-50/20 dark:border-amber-800 dark:bg-amber-950/10'
          : 'border-emerald-200 bg-emerald-50/20 dark:border-emerald-800 dark:bg-emerald-950/10'
      }`}>
        {/* 头部信息 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`size-11 rounded-xl flex items-center justify-center shadow-sm ${
              isPending
                ? 'bg-gradient-to-br from-amber-100 to-amber-200 text-amber-700 dark:from-amber-900 dark:to-amber-800 dark:text-amber-200'
                : 'bg-gradient-to-br from-emerald-100 to-emerald-200 text-emerald-700 dark:from-emerald-900 dark:to-emerald-800 dark:text-emerald-200'
            }`}>
              <ClipboardCheck size={22} />
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground">
                审核：{stageLabel}
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                任务 #{review.task_id} · {review.topic} · {isNewspic ? '贴图' : '图文'}
              </p>
            </div>
          </div>
          {!isPending && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-100/80 text-emerald-700 border border-emerald-200 dark:bg-emerald-900/60 dark:text-emerald-300 dark:border-emerald-800">
              <CheckCircle size={14} />
              <span className="text-xs font-semibold">已通过</span>
            </div>
          )}
        </div>

        {/* 审核操作区（仅待审核时显示） */}
        {isPending && !resolved && (
          <div className="rounded-xl border border-amber-200 bg-amber-50/40 dark:border-amber-800 dark:bg-amber-950/30 p-4 space-y-3">
            <div className="flex items-center gap-2 text-amber-700 dark:text-amber-300">
              <ClipboardCheck size={16} />
              <span className="text-sm font-semibold">审核操作</span>
            </div>
            <div className="flex items-start gap-3">
              <label className="text-xs font-medium text-muted-foreground shrink-0 pt-1.5 w-24">审核意见</label>
              <textarea
                value={comment}
                onChange={e => setComment(e.target.value)}
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm
                           placeholder:text-muted-foreground/50 resize-none
                           focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500/50
                           transition-all"
                rows={2}
                placeholder="输入审核意见或备注（可选）..."
              />
            </div>
            <div className="flex justify-end">
              <Button
                onClick={() => setShowApproveConfirm(true)}
                disabled={submitting}
                className="bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm shadow-emerald-200 dark:shadow-emerald-900/50
                           transition-all hover:shadow-md hover:scale-[1.02]"
              >
                {submitting ? (
                  <Loader2 size={15} className="animate-spin mr-2" />
                ) : (
                  <ThumbsUp size={15} className="mr-2" />
                )}
                通过审核，进入后续流程
              </Button>
            </div>
          </div>
        )}

        {/* 审核内容 */}
        {review.stage === 20 && isNewspic && isPending ? (
          /* ---- image 模式 stage=20：双 Tab（选题简报 + 卡片审核） ---- */
          <div className="rounded-lg border bg-card">
            {/* Tab 导航 */}
            <div className="flex items-center border-b border-border/40 bg-muted/30">
              <button
                onClick={() => setReviewTab('content')}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-[1px] ${
                  reviewTab === 'content'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <FileText size={14} />
                选题简报
              </button>
              <button
                onClick={() => setReviewTab('images')}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-[1px] ${
                  reviewTab === 'images'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <Image size={14} />
                卡片审核
                {formCards.length > 0 && (
                  <span className="ml-1 rounded-full bg-muted-foreground/15 px-1.5 py-0.5 text-[10px] font-semibold">
                    {formCards.length}
                  </span>
                )}
              </button>
              <span className="ml-auto mr-3 text-xs text-muted-foreground/60">
                选题简报
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowSaveConfirm(true)}
                disabled={saving}
                className="gap-1.5 mr-2 border-blue-200 text-blue-700 hover:bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-950"
              >
                {saving ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Save size={14} />
                )}
                保存
              </Button>
            </div>

            {/* Tab 内容 */}
            {reviewTab === 'content' ? (
              <div>
                {/* 编辑模式切换 */}
                <div className="flex items-center gap-0.5 px-4 py-2 border-b border-border/20 bg-muted/15">
                  <div className="flex items-center gap-0.5 bg-muted/80 rounded-lg p-0.5">
                    <button
                      onClick={() => setEditMode('visual')}
                      className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-xs font-medium transition-all duration-200 ${
                        editMode === 'visual'
                          ? 'bg-card text-foreground shadow-sm ring-1 ring-border/30'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                      }`}
                    >
                      <Eye size={13} />
                      可视化编辑
                    </button>
                    <button
                      onClick={() => setEditMode('source')}
                      className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-xs font-medium transition-all duration-200 ${
                        editMode === 'source'
                          ? 'bg-card text-foreground shadow-sm ring-1 ring-border/30'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                      }`}
                    >
                      <FileText size={13} />
                      Markdown 源码
                    </button>
                  </div>
                </div>

                {/* 内容区 */}
                {editMode === 'visual' ? (
                  <div className="tiptap-auto-height">
                    <TiptapEditor
                      key={contentKey}
                      content={editContent}
                      onChange={(html: string) => setEditContent(html)}
                      editable={true}
                      placeholder="开始编辑选题简报（标题 + 摘要）..."
                      contentClassName="min-h-[350px] p-4"
                    />
                  </div>
                ) : editMode === 'source' ? (
                  <textarea
                    value={editContent}
                    onChange={e => setEditContent(e.target.value)}
                    className="w-full min-h-[370px] rounded-lg border border-border bg-background
                               p-4 font-mono text-sm leading-relaxed resize-y
                               focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50
                               placeholder:text-muted-foreground/50"
                    placeholder="开始编辑选题简报的 Markdown 源码（首行 # 标题 + 正文摘要）..."
                  />
                ) : null}
              </div>
            ) : (
              /* ---- 卡片审核网格（复用 ImageReviewCard） ---- */
              <div className="p-4">
                {reviewImages.length > 0 ? (
                  <div className="space-y-4">
                    <p className="text-xs text-muted-foreground">
                      共 <span className="font-semibold text-foreground">{reviewImages.length}</span> 张卡片，
                      描述已展示，可在各卡片上编辑 Prompt
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      {reviewImages.map(img => (
                        <ImageReviewCard
                          key={img.id}
                          image={img}
                          taskId={review.task_id}
                          taskType={review.type}
                          hasCoverRecord={reviewImages.some(i => i.is_cover === 1)}
                          onReplace={(file) => handleImageReplace(img.id, file)}
                          onRegenerate={(prompt) => handleImageRegenerate(img.id, prompt)}
                          onRefresh={handleImageRefresh}
                          disabled={false}
                          showActions={true}
                          regenerateLabel="生成"
                        />
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-center text-sm text-muted-foreground py-8">
                    暂无卡片数据，卡片将在 mode 35 自动生成
                  </p>
                )}
              </div>
            )}
          </div>
        ) : review.stage === 60 && isNewspic && isPending ? (
          /* ---- image 模式 stage=60：双 Tab（选题简报 + 配图审核） ---- */
          <div className="rounded-lg border bg-card">
            {/* Tab 导航 */}
            <div className="flex items-center border-b border-border/40 bg-muted/30">
              <button
                onClick={() => setReviewTab('content')}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-[1px] ${
                  reviewTab === 'content'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <FileText size={14} />
                选题简报
              </button>
              <button
                onClick={() => setReviewTab('images')}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-[1px] ${
                  reviewTab === 'images'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <Image size={14} />
                配图审核
                {reviewImages.length > 0 && (
                  <span className="ml-1 rounded-full bg-muted-foreground/15 px-1.5 py-0.5 text-[10px] font-semibold">
                    {reviewImages.length}
                  </span>
                )}
              </button>
            </div>

            {/* Tab 内容 */}
            {reviewTab === 'content' ? (
              <div className="p-4">
                {task?.brief ? (
                  <MarkdownViewer content={task.brief} />
                ) : (
                  <p className="text-muted-foreground">暂无简报内容</p>
                )}
              </div>
            ) : (
              /* ---- 配图审核网格 ---- */
              <div className="p-4">
                {reviewImages.length > 0 ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <p className="text-xs text-muted-foreground">
                        共 <span className="font-semibold text-foreground">{reviewImages.length}</span> 张图片，
                        封面判定：{reviewImages.some(img => img.is_cover === 1) ? '有独立封面记录' : '第一张配图即封面'}
                      </p>
                      {isPending && (
                        <AppendImageButton disabled={imageOpsDisabled} onAppend={handleAppendImages} />
                      )}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      {reviewImages.map(img => (
                        <ImageReviewCard
                          key={img.id}
                          image={img}
                          taskId={review.task_id}
                          taskType={review.type}
                          hasCoverRecord={reviewImages.some(i => i.is_cover === 1)}
                          onReplace={(file) => handleImageReplace(img.id, file)}
                          onRegenerate={(prompt) => handleImageRegenerate(img.id, prompt)}
                          onRefresh={handleImageRefresh}
                          disabled={imageOpsDisabled}
                        />
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-center text-sm text-muted-foreground py-8">暂无配图</p>
                )}
              </div>
            )}
          </div>
        ) : review.stage === 40 && !isNewspic && isPending ? (
          /* ---- article 模式 stage=40：双 Tab（文章内容 + 配图审核） ---- */
          <div className="rounded-lg border bg-card">
            {/* Tab 导航 */}
            <div className="flex items-center border-b border-border/40 bg-muted/30">
              <button
                onClick={() => setReviewTab('content')}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-[1px] ${
                  reviewTab === 'content'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <FileText size={14} />
                文章内容
              </button>
              <button
                onClick={() => setReviewTab('images')}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-[1px] ${
                  reviewTab === 'images'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <Image size={14} />
                配图审核
                {reviewImages.length > 0 && (
                  <span className="ml-1 rounded-full bg-muted-foreground/15 px-1.5 py-0.5 text-[10px] font-semibold">
                    {reviewImages.length}
                  </span>
                )}
              </button>
              <span className="ml-auto mr-3 text-xs text-muted-foreground/60">
                {editLabel}
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowSaveConfirm(true)}
                disabled={saving}
                className="gap-1.5 mr-2 border-blue-200 text-blue-700 hover:bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-950"
              >
                {saving ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Save size={14} />
                )}
                保存
              </Button>
            </div>

            {/* Tab 内容 */}
            {reviewTab === 'content' ? (
              <div>
                {/* 编辑模式切换 */}
                <div className="flex items-center gap-0.5 px-4 py-2 border-b border-border/20 bg-muted/15">
                  <div className="flex items-center gap-0.5 bg-muted/80 rounded-lg p-0.5">
                    <button
                      onClick={() => setEditMode('visual')}
                      className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-xs font-medium transition-all duration-200 ${
                        editMode === 'visual'
                          ? 'bg-card text-foreground shadow-sm ring-1 ring-border/30'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                      }`}
                    >
                      <Eye size={13} />
                      可视化编辑
                    </button>
                    <button
                      onClick={() => setEditMode('source')}
                      className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-xs font-medium transition-all duration-200 ${
                        editMode === 'source'
                          ? 'bg-card text-foreground shadow-sm ring-1 ring-border/30'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                      }`}
                    >
                      <FileText size={13} />
                      Markdown 源码
                    </button>
                  </div>
                </div>

                {/* 内容区 */}
                {editMode === 'visual' ? (
                  <div
                    className="tiptap-auto-height"
                  >
                    <TiptapEditor
                      key={contentKey}
                      content={editContent}
                      onChange={(html: string) => setEditContent(html)}
                      editable={true}
                      placeholder={`开始编辑${editLabel}...`}
                      contentClassName="min-h-[350px] p-4"
                    />
                  </div>
                ) : editMode === 'source' ? (
                  <textarea
                    value={editContent}
                    onChange={e => setEditContent(e.target.value)}
                    className="w-full min-h-[370px] rounded-lg border border-border bg-background
                               p-4 font-mono text-sm leading-relaxed resize-y
                               focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50
                               placeholder:text-muted-foreground/50"
                    placeholder={`开始编辑${editLabel}的 Markdown 源码...`}
                  />
                ) : null}
              </div>
            ) : (
              /* ---- 配图审核网格 ---- */
              <div className="p-4">
                {reviewImages.length > 0 ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <p className="text-xs text-muted-foreground">
                        共 <span className="font-semibold text-foreground">{reviewImages.length}</span> 张图片，
                        封面判定：{reviewImages.some(img => img.is_cover === 1) ? '有独立封面记录' : '第一张配图即封面'}
                      </p>
                      {isPending && (
                        <AppendImageButton disabled={imageOpsDisabled} onAppend={handleAppendImages} />
                      )}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      {reviewImages.map(img => (
                        <ImageReviewCard
                          key={img.id}
                          image={img}
                          taskId={review.task_id}
                          taskType={review.type}
                          hasCoverRecord={reviewImages.some(i => i.is_cover === 1)}
                          onReplace={(file) => handleImageReplace(img.id, file)}
                          onRegenerate={(prompt) => handleImageRegenerate(img.id, prompt)}
                          onRefresh={handleImageRefresh}
                          disabled={imageOpsDisabled}
                        />
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-center text-sm text-muted-foreground py-8">暂无配图</p>
                )}
              </div>
            )}
          </div>
        ) : isEditable ? (
          <div className="rounded-lg border bg-card">
            {/* 工具栏：tab 切换 + 保存 */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/40 bg-muted/30">
              <div className="flex items-center gap-0.5 bg-muted/80 rounded-lg p-0.5">
                <button
                  onClick={() => setEditMode('visual')}
                  className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-xs font-medium transition-all duration-200 ${
                    editMode === 'visual'
                      ? 'bg-card text-foreground shadow-sm ring-1 ring-border/30'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                  }`}
                >
                  <Eye size={13} />
                  可视化编辑
                </button>
                <button
                  onClick={() => setEditMode('source')}
                  className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-xs font-medium transition-all duration-200 ${
                    editMode === 'source'
                      ? 'bg-card text-foreground shadow-sm ring-1 ring-border/30'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                  }`}
                >
                  <FileText size={13} />
                  Markdown 源码
                </button>
              </div>
              <span className="text-xs text-muted-foreground/60">
                {editLabel}
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowSaveConfirm(true)}
                disabled={saving}
                className="gap-1.5 border-blue-200 text-blue-700 hover:bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-950"
              >
                {saving ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Save size={14} />
                )}
                保存
              </Button>
            </div>

            {/* 内容区 */}
            {editMode === 'visual' ? (
              <div className="tiptap-auto-height">
                <TiptapEditor
                  key={contentKey}
                  content={editContent}
                  onChange={(html: string) => setEditContent(html)}
                  editable={true}
                  placeholder={`开始编辑${editLabel}...`}
                  contentClassName="min-h-[350px] p-4"
                />
              </div>
            ) : editMode === 'source' ? (
              <textarea
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
                className="w-full min-h-[370px] rounded-lg border border-border bg-background
                           p-4 font-mono text-sm leading-relaxed resize-y
                           focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50
                           placeholder:text-muted-foreground/50"
                placeholder={`开始编辑${editLabel}的 Markdown 源码...`}
              />
            ) : null}
          </div>
        ) : (
          /* ---- 只读预览（非 20/40 阶段或已审核完成） ---- */
          <div className="rounded-xl border bg-card/60 overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-border/40 bg-muted/30">
              <FileText size={14} className="text-muted-foreground" />
              <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                {review.stage === 20 ? '选题简报' : review.stage === 40 ? '文章内容' : review.stage === 60 ? '配图审核' : review.stage === 85 ? '去味文章（AI 检测未通过）' : '审核内容'}
              </h4>
            </div>
            <div className={`${review.stage === 60 ? 'p-4' : 'p-4 max-h-[60vh] overflow-y-auto'}`}>
              <div className="text-sm text-foreground prose prose-sm max-w-none dark:prose-invert">
                {review.stage === 20 ? (
                  task?.brief ? <MarkdownViewer content={task.brief} /> : <p className="text-muted-foreground">暂无简报内容</p>
                ) : review.stage === 40 ? (
                  task?.markdown ? <MarkdownViewer content={task.markdown} /> : <p className="text-muted-foreground">暂无文章内容</p>
                ) : review.stage === 60 ? (
                  /* ---- 配图审核网格 ---- */
                  reviewImages.length > 0 ? (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <p className="text-xs text-muted-foreground">
                          共 <span className="font-semibold text-foreground">{reviewImages.length}</span> 张图片，
                          封面判定：{reviewImages.some(img => img.is_cover === 1) ? '有独立封面记录' : '第一张配图即封面'}
                        </p>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                        {reviewImages.map(img => (
                          <ImageReviewCard
                            key={img.id}
                            image={img}
                            taskId={review.task_id}
                            taskType={review.type}
                            hasCoverRecord={reviewImages.some(i => i.is_cover === 1)}
                            onReplace={(file) => handleImageReplace(img.id, file)}
                            onRegenerate={(prompt) => handleImageRegenerate(img.id, prompt)}
                            onRefresh={handleImageRefresh}
                            disabled={imageOpsDisabled}
                          />
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="text-center text-sm text-muted-foreground py-8">暂无配图</p>
                  )
                ) : review.stage === 85 ? (
                  /* ---- AI 味检测未通过：只读展示去味文章 + 检测报告 ---- */
                  <div className="space-y-4">
                    {task?.ai_score != null && (
                      <div className={`rounded-md border px-4 py-3 text-sm ${
                        (task.ai_score ?? 0) > 45
                          ? 'border-destructive/40 bg-destructive/5 text-destructive'
                          : 'border-amber-400/40 bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
                      }`}>
                        <p className="font-medium">
                          AI 味检测：{task.ai_score} 分
                          <span className="ml-2 font-mono text-xs">({task.ai_verdict || 'FAIL'})</span>
                        </p>
                        <p className="mt-1 text-xs opacity-80">
                          分数超过阈值 45 判定未通过；审核通过后将以当前文章内容直接发布，
                          驳回后可在任务页手动重新去味改写。
                        </p>
                      </div>
                    )}
                    {task?.markdown ? (
                      <MarkdownViewer content={task.markdown} />
                    ) : (
                      <p className="text-muted-foreground">暂无文章内容</p>
                    )}
                  </div>
                ) : (
                  <p className="text-muted-foreground">暂不支持此阶段的预览</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* 任务状态信息 */}
        {task && (
          <div className="rounded-xl border bg-card/60 p-3 flex items-center gap-6 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">任务状态</span>
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                task.status >= 80 ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300' :
                task.status === 0 ? 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300' :
                'bg-muted text-muted-foreground'
              }`}>
                {STATUS_LABELS[task.status] || `状态 ${task.status}`}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">任务类型</span>
              <span className="font-medium text-foreground">{isNewspic ? '贴图消息' : '图文消息'}</span>
            </div>
            <button
              onClick={() => navigate(taskPath)}
              className="ml-auto inline-flex items-center gap-1 text-primary hover:underline text-xs"
            >
              查看任务详情 <ExternalLink size={11} />
            </button>
          </div>
        )}

        {/* 已有审核意见 */}
        {review.comment && (
          <div className="rounded-lg border-l-4 border-l-blue-400 bg-blue-50/50 dark:border-l-blue-600 dark:bg-blue-950/30 p-3">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-xs font-semibold text-blue-600 dark:text-blue-400">审核意见</span>
            </div>
            <p className="text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed">{review.comment}</p>
          </div>
        )}

        {/* 已完成状态提示 */}
        {resolved && (
          <div className="rounded-lg flex items-center gap-3 px-4 py-3 bg-emerald-50 border border-emerald-200 dark:bg-emerald-950/40 dark:border-emerald-800">
            <div className="size-8 rounded-full bg-emerald-100 dark:bg-emerald-900 flex items-center justify-center">
              <CheckCircle size={16} className="text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300">审核已通过</p>
              <p className="text-xs text-emerald-600/70 dark:text-emerald-400/60">任务将继续执行后续 pipeline 流程</p>
            </div>
          </div>
        )}
      </div>

      {/* 通过审核确认弹窗 */}
      {showApproveConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => setShowApproveConfirm(false)}>
          <div className="bg-card rounded-2xl border border-border shadow-2xl max-w-md w-full mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="bg-gradient-to-r from-emerald-500 to-emerald-600 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="size-10 rounded-xl bg-white/20 flex items-center justify-center">
                  <ThumbsUp size={20} className="text-white" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white">确认通过审核</h3>
                  <p className="text-sm text-emerald-100/80">审核通过后任务将继续执行后续流程</p>
                </div>
              </div>
            </div>
            <div className="p-6 space-y-4">
              <div className="rounded-xl bg-muted/40 border border-border/60 p-4 space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">审核编号</span>
                  <span className="font-semibold text-foreground">#{review.id} · {stageLabel}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">关联任务</span>
                  <span className="font-semibold text-foreground">#{review.task_id} {review.topic}</span>
                </div>
              </div>
              <div className="flex justify-end gap-3">
                <Button variant="outline" size="sm" onClick={() => setShowApproveConfirm(false)}>
                  取消
                </Button>
                <Button
                  size="sm"
                  onClick={handleApprove}
                  disabled={submitting}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm"
                >
                  {submitting ? (
                    <Loader2 size={14} className="animate-spin mr-1.5" />
                  ) : (
                    <ThumbsUp size={14} className="mr-1.5" />
                  )}
                  确认通过
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 保存确认弹窗 */}
      {showSaveConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => setShowSaveConfirm(false)}>
          <div className="bg-card rounded-2xl border border-border shadow-2xl max-w-md w-full mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="bg-gradient-to-r from-blue-500 to-blue-600 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="size-10 rounded-xl bg-white/20 flex items-center justify-center">
                  <Save size={20} className="text-white" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white">确认保存</h3>
                  <p className="text-sm text-blue-100/80">此操作将覆盖原有{editLabel}内容</p>
                </div>
              </div>
            </div>
            <div className="p-6 space-y-4">
              <div className="rounded-xl bg-muted/40 border border-border/60 p-4 space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">审核编号</span>
                  <span className="font-semibold text-foreground">#{review.id} · {stageLabel}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">关联任务</span>
                  <span className="font-semibold text-foreground">#{review.task_id} {review.topic}</span>
                </div>
              </div>
              <div className="flex justify-end gap-3">
                <Button variant="outline" size="sm" onClick={() => setShowSaveConfirm(false)}>
                  取消
                </Button>
                <Button
                  size="sm"
                  onClick={async () => {
                    setSaving(true)
                    setShowSaveConfirm(false)
                    try {
                      let res
                      if (review.stage === 20 && isNewspic) {
                        // newspic stage 20：解析标题+摘要
                        const title = extractTitleFromContent(editContent)
                        const shortText = extractShortTextFromContent(editContent)
                        res = await saveNewspicReview(review.task_id, {
                          title,
                          short_text: shortText,
                          image_style: review.image_style,
                        })
                      } else if (review.stage === 20) {
                        res = await updateTaskBrief(review.task_id, editContent)
                      } else {
                        res = await updateTaskArticle(review.task_id, editContent)
                      }
                      if (res.code && res.code !== 200 && res.code !== 0) {
                        alert(res.message || '保存失败')
                        return
                      }
                      if (review.task_id) {
                        try {
                          const taskRes = await getTask(review.task_id)
                          if (taskRes.data) setTask(taskRes.data)
                        } catch { /* 刷新失败不影响 */ }
                      }
                    } catch (e) {
                      alert(e instanceof Error ? e.message : '保存失败')
                    } finally {
                      setSaving(false)
                    }
                  }}
                >
                  确认保存
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
    <style>{`
      .tiptap-auto-height [class*="ProseMirror"] {
        overflow: visible !important;
        height: auto !important;
        min-height: 350px;
      }
    `}</style>
    </>
  )
}

