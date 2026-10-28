import { useState, useEffect, useRef } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { TiptapEditor } from 'shadcn-tiptap-editor'
import { Loader2, ArrowLeft, Save, Eye, Upload, Image } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getDraftDetail, addDraft, updateDraft, uploadMaterial, getApiBaseUrl } from '@/lib/api'
import type { DraftDetail } from '@/lib/api'

export function DraftEdit() {
  const navigate = useNavigate()
  const { mediaId } = useParams<{ mediaId?: string }>()
  const [searchParams] = useSearchParams()
  const isNew = searchParams.get('new') === '1' || !mediaId

  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 表单字段
  const [title, setTitle] = useState('')
  const [author, setAuthor] = useState('')
  const [digest, setDigest] = useState('')
  const [content, setContent] = useState('')
  const [contentSourceUrl, setContentSourceUrl] = useState('')
  const [needOpenComment, setNeedOpenComment] = useState(0)
  const [onlyFansCanComment, setOnlyFansCanComment] = useState(0)
  const [thumbMediaId, setThumbMediaId] = useState('')
  const [coverUploading, setCoverUploading] = useState(false)
  const [coverPreview, setCoverPreview] = useState<string | null>(null)
  const coverInputRef = useRef<HTMLInputElement>(null)

  // 加载已有草稿详情
  useEffect(() => {
    if (isNew || !mediaId) return
    setLoading(true)
    setError(null)
    getDraftDetail(mediaId)
      .then((res) => {
        if (res.data) {
          const d = res.data as DraftDetail
          setTitle(d.title || '')
          setAuthor(d.author || '')
          setDigest(d.digest || '')
          setContent(d.content || '')
          setContentSourceUrl(d.content_source_url || '')
          setNeedOpenComment(d.show_cover_pic ?? 0)
          setOnlyFansCanComment(d.need_open_comment ?? 0)
          setThumbMediaId(d.thumb_media_id || '')
          if (d.thumb_url) setCoverPreview(d.thumb_url)
        } else {
          setError(res.message || '加载失败')
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : '加载草稿详情失败'))
      .finally(() => setLoading(false))
  }, [mediaId, isNew])

  // 保存
  const handleSave = async () => {
    if (!title.trim()) {
      alert('请输入文章标题')
      return
    }
    if (!content.trim()) {
      alert('请输入文章内容')
      return
    }
    if (isNew && !thumbMediaId) {
      alert('请先上传封面图')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const data = {
        title: title.trim(),
        content,
        author: author.trim(),
        digest: digest.trim(),
        content_source_url: contentSourceUrl.trim(),
        thumb_media_id: thumbMediaId,
        need_open_comment: needOpenComment,
        only_fans_can_comment: onlyFansCanComment,
      }
      if (isNew) {
        const res = await addDraft(data)
        if (res.code === 0) {
          navigate('/wechat/drafts')
        } else {
          setError(res.message || '新增失败')
        }
      } else if (mediaId) {
        const res = await updateDraft(mediaId, data)
        if (res.code === 0) {
          navigate('/wechat/drafts')
        } else {
          setError(res.message || '更新失败')
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  /** 上传封面图 */
  const handleCoverUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setCoverUploading(true)
    try {
      const res = await uploadMaterial(file, 'image')
      if (res.code === 0 && res.data?.media_id) {
        setThumbMediaId(res.data.media_id)
        // 用后端代理 URL 预览封面
        setCoverPreview(`${getApiBaseUrl()}/wechat/materials/${res.data.media_id}/image`)
      } else {
        alert(res.message || '封面上传失败')
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : '封面上传失败')
    } finally {
      setCoverUploading(false)
      if (coverInputRef.current) coverInputRef.current.value = ''
    }
  }

  return (
    <div className="space-y-4">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon-sm" onClick={() => navigate('/wechat/drafts')}>
            <ArrowLeft size={18} />
          </Button>
          <div>
            <h2 className="text-page-title text-foreground">
              {isNew ? '新增草稿' : '编辑草稿'}
            </h2>
            <p className="text-sm text-muted-foreground">
              {isNew ? '创建新的微信公众号草稿' : `编辑草稿: ${title || mediaId}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate('/wechat/drafts')}>
            取消
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Save size={16} />
            )}
            保存
          </Button>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* 加载中 */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">加载中...</span>
        </div>
      )}

      {/* 表单 */}
      {!loading && (
        <div className="space-y-4">
          {/* 基本信息 */}
          <div className="rounded-lg border bg-card p-4 space-y-3">
            <h3 className="text-sm font-semibold text-foreground">基本信息</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  标题 <span className="text-destructive">*</span>
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="文章标题"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm
                    placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  作者
                </label>
                <input
                  type="text"
                  value={author}
                  onChange={(e) => setAuthor(e.target.value)}
                  placeholder="作者名称（留空则使用公众号默认）"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm
                    placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  摘要
                </label>
                <textarea
                  value={digest}
                  onChange={(e) => setDigest(e.target.value)}
                  placeholder="文章摘要（120 字以内）"
                  rows={2}
                  maxLength={120}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm resize-none
                    placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  原文链接
                </label>
                <input
                  type="url"
                  value={contentSourceUrl}
                  onChange={(e) => setContentSourceUrl(e.target.value)}
                  placeholder="https://..."
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm
                    placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={needOpenComment === 1}
                    onChange={(e) => setNeedOpenComment(e.target.checked ? 1 : 0)}
                    className="rounded"
                  />
                  开启留言
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={onlyFansCanComment === 1}
                    onChange={(e) => setOnlyFansCanComment(e.target.checked ? 1 : 0)}
                    className="rounded"
                  />
                  仅粉丝可留言
                </label>
              </div>
            </div>
          </div>

          {/* 封面图 */}
          <div className="rounded-lg border bg-card p-4 space-y-3">
            <h3 className="text-sm font-semibold text-foreground">
              封面图 {isNew && <span className="text-destructive">*</span>}
            </h3>
            <div className="flex items-start gap-4">
              {/* 预览 */}
              <div className="shrink-0">
                {coverPreview ? (
                  <img
                    src={coverPreview}
                    alt="封面预览"
                    className="w-32 h-20 object-cover rounded-lg border"
                  />
                ) : (
                  <div className="w-32 h-20 rounded-lg border bg-muted flex items-center justify-center">
                    <Image size={20} className="text-muted-foreground/40" />
                  </div>
                )}
              </div>
              <div className="flex-1 space-y-2">
                <input
                  ref={coverInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleCoverUpload}
                  className="hidden"
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => coverInputRef.current?.click()}
                  disabled={coverUploading}
                >
                  {coverUploading ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Upload size={14} />
                  )}
                  上传封面图
                </Button>
                <p className="text-xs text-muted-foreground">
                  {thumbMediaId
                    ? `已上传: ${thumbMediaId.slice(0, 20)}...`
                    : '上传图片到永久素材作为封面（必填，大图建议 900×500 像素）'}
                </p>
              </div>
            </div>
          </div>

          {/* 编辑器 */}
          <div className="rounded-lg border bg-card overflow-hidden">
            <div className="flex items-center gap-1.5 px-4 py-2 border-b bg-muted/30">
              <Eye size={14} className="text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">正文内容</span>
              <span className="text-xs text-destructive ml-auto">* 必填</span>
            </div>
            <div
              className="tiptap-auto-height [&_[class*='ProseMirror']]:min-h-[300px] [&_[class*='ProseMirror']]:overflow-visible"
              style={{ overflow: 'visible' } as React.CSSProperties}
            >
              <TiptapEditor
                content={content}
                onChange={(html: string) => setContent(html)}
                editable={true}
                placeholder="开始编写文章内容..."
                contentClassName="min-h-[300px] p-4"
              />
              <style>{`
                .tiptap-auto-height [class*="ProseMirror"] {
                  overflow: visible !important;
                  height: auto !important;
                  min-height: 300px;
                }
              `}</style>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
