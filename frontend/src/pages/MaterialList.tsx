import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Loader2,
  ChevronLeft,
  ChevronRight,
  Trash2,
  AlertTriangle,
  Image,
  Film,
  Upload,
  Download,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getMaterialList, getMaterialDetail, uploadMaterial, deleteMaterial, uploadContentImage, getApiBaseUrl } from '@/lib/api'
import type { MaterialItem, MaterialDetail } from '@/lib/api'

const PAGE_SIZE = 20
const MATERIAL_TYPES = [
  { value: 'image', label: '图片' },
  { value: 'video', label: '视频' },
  { value: 'voice', label: '语音' },
]

/** 格式化 Unix 时间戳 */
function formatTime(ts: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${h}:${min}`
}

export function MaterialList() {
  const [materialType, setMaterialType] = useState('image')
  const [items, setItems] = useState<MaterialItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 删除
  const [deleting, setDeleting] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<MaterialItem | null>(null)

  // 上传
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<string | null>(null)

  // 上传内容图片
  const contentImageRef = useRef<HTMLInputElement>(null)
  const [uploadingContent, setUploadingContent] = useState(false)
  const [contentImageUrl, setContentImageUrl] = useState<string | null>(null)
  const [contentImageMsg, setContentImageMsg] = useState<string | null>(null)

  // 预览
  const [preview, setPreview] = useState<MaterialDetail | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getMaterialList(materialType, offset, PAGE_SIZE)
      if (res.data) {
        setItems(res.data.items || [])
        setTotal(res.data.total_count || 0)
      } else {
        setError(res.message || '加载失败')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '请求失败')
    } finally {
      setLoading(false)
    }
  }, [materialType, offset])

  useEffect(() => {
    setOffset(0)
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [materialType])

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset])

  /** 删除 */
  const handleDelete = async (item: MaterialItem) => {
    setConfirmDelete(null)
    setDeleting(item.media_id)
    try {
      const res = await deleteMaterial(item.media_id)
      if (res.code === 0) {
        setItems((prev) => prev.filter((i) => i.media_id !== item.media_id))
        setTotal((prev) => Math.max(0, prev - 1))
      } else {
        alert(res.message || '删除失败')
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : '删除请求失败')
    } finally {
      setDeleting(null)
    }
  }

  /** 上传 */
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadMsg(null)
    try {
      const res = await uploadMaterial(file, materialType)
      if (res.code === 0) {
        setUploadMsg(`上传成功: ${res.data?.media_id}`)
        load() // 刷新列表
      } else {
        setUploadMsg(res.message || '上传失败')
      }
    } catch (e) {
      setUploadMsg(e instanceof Error ? e.message : '上传失败')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  /** 上传内容图片 */
  const handleContentImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadingContent(true)
    setContentImageMsg(null)
    setContentImageUrl(null)
    try {
      const res = await uploadContentImage(file)
      if (res.code === 0 && res.data?.url) {
        setContentImageUrl(res.data.url)
        setContentImageMsg('上传成功！')
      } else {
        setContentImageMsg(res.message || '上传失败')
      }
    } catch (e) {
      setContentImageMsg(e instanceof Error ? e.message : '上传失败')
    } finally {
      setUploadingContent(false)
      if (contentImageRef.current) contentImageRef.current.value = ''
    }
  }

  /** 查看详情 */
  const handlePreview = async (item: MaterialItem) => {
    setPreviewLoading(true)
    setPreview(null)
    try {
      const res = await getMaterialDetail(item.media_id)
      if (res.data) {
        setPreview(res.data as MaterialDetail)
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : '获取详情失败')
    } finally {
      setPreviewLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-page-title text-foreground">永久素材</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            管理微信公众号永久素材（上限 5000 个）
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept={materialType === 'video' ? 'video/*' : materialType === 'voice' ? 'audio/*' : 'image/*'}
            onChange={handleUpload}
            className="hidden"
          />
          <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
            {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            上传素材
          </Button>
        </div>
      </div>

      {/* 上传提示 */}
      {uploadMsg && (
        <div className="rounded-md border border-border bg-muted/30 px-4 py-3 text-sm text-foreground">
          {uploadMsg}
          <button className="ml-3 text-xs text-muted-foreground hover:text-foreground" onClick={() => setUploadMsg(null)}>关闭</button>
        </div>
      )}

      {/* 上传内容图片（不占素材配额） */}
      <div className="rounded-lg border bg-card p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-foreground">上传发表内容中的图片</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              上传图片到微信 CDN，返回 URL 可直接用于文章内容，<strong>不占用永久素材配额</strong>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              ref={contentImageRef}
              type="file"
              accept="image/*"
              onChange={handleContentImageUpload}
              className="hidden"
            />
            <Button size="sm" variant="outline" onClick={() => contentImageRef.current?.click()} disabled={uploadingContent}>
              {uploadingContent ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              选择图片
            </Button>
          </div>
        </div>
        {contentImageMsg && (
          <div className={`mt-3 rounded-md px-3 py-2 text-sm ${contentImageUrl ? 'bg-emerald-50 border border-emerald-200 dark:bg-emerald-950/20 dark:border-emerald-800' : 'bg-muted/50 border border-border'}`}>
            {contentImageMsg}
            {contentImageUrl && (
              <div className="mt-2 flex items-center gap-2">
                <input
                  type="text"
                  value={contentImageUrl}
                  readOnly
                  className="flex-1 rounded border bg-background px-2 py-1 text-xs font-mono truncate"
                  onFocus={(e) => e.target.select()}
                />
                <button
                  onClick={() => { navigator.clipboard.writeText(contentImageUrl); alert('已复制到剪贴板') }}
                  className="shrink-0 rounded bg-primary px-2 py-1 text-xs text-primary-foreground hover:opacity-90"
                >
                  复制
                </button>
                <button
                  onClick={() => { setContentImageMsg(null); setContentImageUrl(null) }}
                  className="shrink-0 text-xs text-muted-foreground hover:text-foreground"
                >
                  关闭
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 类型筛选 */}
      <div className="flex items-center gap-2">
        {MATERIAL_TYPES.map((t) => (
          <button
            key={t.value}
            onClick={() => { setMaterialType(t.value); setOffset(0) }}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
              materialType === t.value
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 删除确认弹窗 */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="mx-4 w-full max-w-md rounded-lg border bg-card p-6 shadow-lg">
            <div className="flex items-start gap-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-destructive/10">
                <AlertTriangle size={18} className="text-destructive" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-foreground">确认删除</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  确定要删除素材「{confirmDelete.name || confirmDelete.media_id}」吗？删除后不可恢复。
                </p>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirmDelete(null)}>取消</Button>
              <Button variant="destructive" size="sm" onClick={() => handleDelete(confirmDelete)}>确认删除</Button>
            </div>
          </div>
        </div>
      )}

      {/* 预览加载遮罩 */}
      {previewLoading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="flex items-center gap-2 rounded-lg bg-card px-6 py-4 shadow-lg border">
            <Loader2 size={20} className="animate-spin text-primary" />
            <span className="text-sm text-foreground">加载详情...</span>
          </div>
        </div>
      )}
      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="mx-4 w-full max-w-2xl max-h-[85vh] overflow-auto rounded-lg border bg-card p-6 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-foreground">素材详情</h3>
              <button onClick={() => setPreview(null)} className="text-muted-foreground hover:text-foreground text-sm">关闭</button>
            </div>
            {preview.material_type === 'video' ? (
              <div className="space-y-3">
                {preview.down_url ? (
                  <video
                    src={preview.down_url}
                    controls
                    className="w-full max-h-[400px] rounded-lg border bg-black"
                    preload="metadata"
                  >
                    您的浏览器不支持视频播放
                  </video>
                ) : (
                  <div className="flex items-center justify-center py-8 bg-muted/30 rounded-lg border">
                    <Film size={48} className="text-muted-foreground/40" />
                  </div>
                )}
                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">名称</span>
                    <span className="font-medium text-foreground">{preview.name || '(无标题)'}</span>
                  </div>
                  {preview.description && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">描述</span>
                      <span className="font-medium text-foreground">{preview.description}</span>
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">media_id</span>
                    <span className="font-mono text-xs text-foreground">{preview.media_id}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">更新时间</span>
                    <span>{formatTime(preview.update_time)}</span>
                  </div>
                </div>
                {preview.down_url && (
                  <a
                    href={preview.down_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground hover:opacity-90"
                  >
                    <Film size={14} />
                    在微信中查看
                  </a>
                )}
              </div>
            ) : preview.data ? (
              <div className="space-y-3">
                <img
                  src={`data:${preview.content_type || 'image/jpeg'};base64,${preview.data}`}
                  alt={preview.name}
                  className="max-w-full rounded-lg border"
                />
                <div className="flex items-center gap-2">
                  <a
                    href={`data:${preview.content_type || 'image/jpeg'};base64,${preview.data}`}
                    download={preview.name || preview.media_id}
                    className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                  >
                    <Download size={14} />
                    下载
                  </a>
                </div>
              </div>
            ) : (
              <div className="space-y-2 text-sm text-muted-foreground">
                <p>media_id: {preview.media_id}</p>
                <p>名称: {preview.name || '-'}</p>
                {preview.url && <p>URL: <a href={preview.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{preview.url}</a></p>}
                <p>更新时间: {formatTime(preview.update_time)}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 加载/错误/空状态 */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">加载中...</span>
        </div>
      )}
      {!loading && error && (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <AlertTriangle size={36} className="text-destructive/70" />
          <p className="text-sm text-muted-foreground">{error}</p>
          <Button variant="outline" size="sm" onClick={load}>重试</Button>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Image size={36} className="text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">暂无素材</p>
        </div>
      )}
      {!loading && !error && items.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground w-[80px]">缩略图</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">名称 / ID</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">更新时间</th>
                  <th className="px-4 py-3 text-center font-medium text-muted-foreground w-[180px]">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.media_id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <ThumbImage mediaId={item.media_id} name={item.name} materialType={materialType} />
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-foreground text-xs truncate max-w-[260px]" title={item.name}>{item.name || '(无名称)'}</p>
                      <p className="text-muted-foreground text-xs mt-0.5 font-mono truncate max-w-[260px]" title={item.media_id}>{item.media_id}</p>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">
                      {formatTime(item.update_time)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-center gap-1">
                        <button
                          onClick={() => handlePreview(item)}
                          className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-xs
                            text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                          title="查看详情"
                        >
                          <Download size={14} />
                          查看
                        </button>
                        <button
                          onClick={() => setConfirmDelete(item)}
                          disabled={deleting === item.media_id}
                          className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-xs
                            text-destructive/80 hover:text-destructive hover:bg-destructive/10 transition-colors
                            disabled:opacity-50"
                          title="删除素材"
                        >
                          {deleting === item.media_id ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Trash2 size={14} />
                          )}
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 分页 */}
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>共 {total} 条，第 {currentPage}/{totalPages} 页</span>
            <div className="flex items-center gap-1">
              <Button variant="outline" size="icon-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                <ChevronLeft size={16} />
              </Button>
              <Button variant="outline" size="icon-sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                <ChevronRight size={16} />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

/** 缩略图组件：图片走代理；视频直接显示视频图标 */
function ThumbImage({ mediaId, name, materialType }: { mediaId: string; name: string; materialType: string }) {
  const [failed, setFailed] = useState(false)

  // 视频素材：微信 API 不返回封面图，显示视频图标
  if (materialType === 'video') {
    return (
      <div className="w-12 h-12 rounded border bg-muted flex items-center justify-center">
        <Film size={18} className="text-muted-foreground/50" />
      </div>
    )
  }

  const proxyUrl = `${getApiBaseUrl()}/wechat/materials/${mediaId}/image`

  if (failed) {
    return (
      <div className="w-12 h-12 rounded border bg-muted flex items-center justify-center">
        <Image size={18} className="text-muted-foreground/50" />
      </div>
    )
  }

  return (
    <img
      src={proxyUrl}
      alt={name}
      className="w-12 h-12 object-cover rounded border"
      onError={() => setFailed(true)}
    />
  )
}

