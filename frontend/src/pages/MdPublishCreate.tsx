import { useState, useMemo, useEffect, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FileUp, Send, Loader2, ChevronDown, ChevronRight, XCircle, CheckCircle2, FileText, ImageIcon, X, Plus,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SmartSelect } from '@/components/SmartSelect'
import { getConfigConstants, importMdTaskInit, importMdTaskRun } from '@/lib/api'
import { useConfigStore } from '@/stores/useConfigStore'
import type { ConfigConstants } from '@/types/config'

// webkitdirectory 为浏览器非标准属性（选择目录），React 类型未收录，扩展声明
declare module 'react' {
  interface InputHTMLAttributes<T> {
    webkitdirectory?: string
  }
}

/** 图片锚点正则：![alt](url) */
const ANCHOR_RE = /!\[([^\]]*)\]\(([^)]+)\)/g

/** 锚点引用：文件名 basename + 锚点描述（![] 内文字） + 原始相对路径 */
interface AnchorRef {
  name: string
  alt: string
  url: string
}

/** 从 md 内容中提取本地图片引用（http 引用忽略） */
function extractAnchorRefs(md: string): AnchorRef[] {
  const refs: AnchorRef[] = []
  for (const m of md.matchAll(ANCHOR_RE)) {
    const url = m[2].trim()
    if (/^https?:\/\//i.test(url)) continue
    const name = url.split(/[\\/]/).pop()
    if (name) refs.push({ name, alt: m[1].trim(), url })
  }
  return refs
}

/** 锚点匹配结果：md 引用的图片在所选目录下是否存在 */
interface AnchorItem {
  name: string
  alt: string
  exists: boolean
  file?: File
  /** 页面内新增的图片（非 md 原有锚点），可删除 */
  added?: boolean
}

/** 生成不与现有锚点重名的图片文件名（如 a.png → a-2.png） */
function uniqueAnchorName(name: string, existing: string[]): string {
  const dot = name.lastIndexOf('.')
  const base = dot > 0 ? name.slice(0, dot) : name
  const ext = dot > 0 ? name.slice(dot) : ''
  let candidate = name
  let n = 2
  while (existing.includes(candidate)) {
    candidate = `${base}-${n}${ext}`
    n++
  }
  return candidate
}

/** 解析锚点 URL 为相对路径 segments（过滤 http、绝对路径、.. 越级） */
function parseRelSegments(url: string): string[] | null {
  const t = url.trim().replace(/\\/g, '/')
  if (/^https?:\/\//i.test(t)) return null
  const clean = t.replace(/^(\.\/)+/, '').replace(/^\/+/, '')
  if (!clean || clean.includes('..')) return null
  return clean.split('/').filter(Boolean)
}

/** 从所选目录文件列表中匹配锚点图片（优先按相对路径前缀，回退 images/ 子目录） */
function matchAnchorFile(files: File[], ref: AnchorRef): File | undefined {
  const segs = parseRelSegments(ref.url)
  return files.find(f => {
    const rel = f.webkitRelativePath || ''
    const parts = rel.replace(/\\/g, '/').split('/').filter(Boolean)
    const fileName = parts[parts.length - 1]
    if (fileName !== ref.name) return false
    // 锚点带目录前缀（如 images/xx.png）→ 目录段需全部出现在文件相对路径中
    if (segs && segs.length > 1) {
      const dirSegs = segs.slice(0, -1)
      if (dirSegs.every(d => parts.includes(d))) return true
    }
    // 回退：图片统一放在 images/ 子目录（锚点只写文件名）
    return parts.includes('images')
  })
}

export function MdPublishCreate() {
  const navigate = useNavigate()
  const config = useConfigStore(s => s.config)

  const [constants, setConstants] = useState<ConfigConstants | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 当前账号
  const defaultKey = config?.default || 'main'
  const account = config?.accounts?.[defaultKey]

  // 表单字段（发布账号与 LLM Provider 固定用默认值，不可修改）
  const [mdFile, setMdFile] = useState<File | null>(null)
  const [mdContent, setMdContent] = useState('')        // 用于锚点解析
  const [anchorItems, setAnchorItems] = useState<AnchorItem[]>([])  // 锚点 → images/ 匹配结果
  const [topic, setTopic] = useState('')
  const [theme, setTheme] = useState('')
  const [author, setAuthor] = useState('')
  const [voice, setVoice] = useState('')

  // 任务在「提交并开始发布」时统一初始化 task / task_image 表

  // 加载常量元数据（排版主题列表等）
  useEffect(() => {
    getConfigConstants()
      .then(res => { if (res.data) setConstants(res.data) })
      .catch(() => {})
  }, [])

  // 从账号配置加载默认值（仅填充空字段，不覆盖用户已修改的值）
  useEffect(() => {
    if (!account) return
    setTheme(t => t || account.theme || '')
    setAuthor(a => a || account.author || '')
    setVoice(v => v || account.voice || '')
  }, [account])

  // 缺图校验：锚点引用的图片在所选目录 images/ 下缺失的
  const missingImages = useMemo(
    () => anchorItems.filter(i => !i.exists),
    [anchorItems],
  )

  // 无锚点（封面自动生成）或锚点图片全部就位 → 可提交
  const allImagesReady = missingImages.length === 0

  /** 已匹配的配图文件列表 */
  const matchedImageFiles = useMemo(
    () => anchorItems.filter(i => i.file).map(i => i.file as File),
    [anchorItems],
  )

  /** 锚点图片预览（objectURL，按锚点文件名索引；组件内新生成的 URL 会清理旧的） */
  const previewUrls = useMemo(() => {
    const urls: Record<string, string> = {}
    anchorItems.forEach(i => { if (i.file) urls[i.name] = URL.createObjectURL(i.file) })
    return urls
  }, [anchorItems])
  useEffect(() => {
    return () => { Object.values(previewUrls).forEach(u => URL.revokeObjectURL(u)) }
  }, [previewUrls])

  /** 主路径：选择文章所在目录（webkitdirectory，浏览器显式授权整个目录，无权限问题），
   *  自动定位 .md、按锚点匹配 images/ 配图，提交时才初始化任务 */
  const handleDirSelect = async (fileList: FileList | null) => {
    const files = Array.from(fileList ?? [])
    if (files.length === 0) {
      setMdFile(null)
      setMdContent('')
      setAnchorItems([])
      return
    }
    // 1. 定位 .md 文章文件（取目录中第一个）
    const md = files.find(f => /\.md$/i.test(f.name))
    if (!md) {
      setMdFile(null)
      setMdContent('')
      setAnchorItems([])
      setError('所选目录中未找到 .md 文章文件')
      return
    }
    setMdFile(md)
    setError(null)
    try {
      const text = await md.text()
      setMdContent(text)
      // 2. 提取首个 # 标题作为话题默认值
      const m = text.match(/^#\s+(.+)$/m)
      const detected = m ? m[1].trim() : ''
      if (detected) setTopic(detected)
      // 3. 锚点 → 目录文件匹配（相对路径前缀优先，回退 images/ 子目录）
      const items: AnchorItem[] = extractAnchorRefs(text).map(ref => {
        const file = matchAnchorFile(files, ref)
        return { name: ref.name, alt: ref.alt, exists: !!file, file }
      })
      setAnchorItems(items)
    } catch {
      setMdContent('')
      setAnchorItems([])
      setError('读取 md 文件失败')
    }
  }

  /** 缺失图片手动替换：选择本地图片文件直接替换锚点 */
  const handleReplaceImage = (name: string, files: FileList | null) => {
    const f = files?.[0]
    if (!f) return
    setAnchorItems(items => items.map(i => (i.name === name ? { ...i, exists: true, file: f } : i)))
  }

  /** 新增图片：以锚点追加到文章内容末尾（锚点形如 ![文件名](images/xxx.png)） */
  const handleAddImages = (files: FileList | null) => {
    const list = Array.from(files ?? []).filter(f => f.type.startsWith('image/'))
    if (list.length === 0) return
    const existing = anchorItems.map(i => i.name)
    const added: AnchorItem[] = []
    let appended = ''
    for (const f of list) {
      const name = uniqueAnchorName(f.name, [...existing, ...added.map(a => a.name)])
      const alt = (f.name.replace(/\.[^.]+$/, '') || f.name)
      added.push({ name, alt, exists: true, file: f, added: true })
      appended += `\n![${alt}](images/${name})\n`
    }
    setAnchorItems(items => [...items, ...added])
    setMdContent(prev => (prev.endsWith('\n') ? prev : `${prev}\n`) + appended)
  }

  /** 删除新增图片：从锚点列表移除，并同步删除文章内容末尾对应的锚点行 */
  const handleRemoveAddedImage = (name: string) => {
    setAnchorItems(items => items.filter(i => i.name !== name))
    setMdContent(prev =>
      prev.split('\n')
        .filter(line => !line.includes(`](images/${name})`))
        .join('\n'),
    )
  }

  /** 提交：先初始化 task / task_image 表（md + 已就位配图），再上传配图并启动去味流程 */
  const handleSubmit = async () => {
    if (!mdFile) {
      setError('请先选择文章所在文件夹')
      return
    }
    if (!allImagesReady) {
      setError(`还有 ${missingImages.length} 张配图缺失（${missingImages.map(i => i.name).join('、')}），请选择图片替换或补齐到 images/ 目录后重新选择文件夹`)
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      // 第一步：初始化任务（修改后的 md 内容 + 已就位配图 → 创建 task 记录与图片锚点）
      const initForm = new FormData()
      // 文章内容已在页面可编辑：以修改后的内容重新构造文件上传（文件名保持不变）
      const contentFile = new File([mdContent], mdFile.name, { type: 'text/markdown' })
      initForm.append('file', contentFile)
      matchedImageFiles.forEach(img => initForm.append('images', img))
      initForm.append('account', defaultKey)
      if (topic.trim()) initForm.append('topic', topic.trim())
      const initRes = await importMdTaskInit(initForm)
      if (initRes.code && initRes.code !== 200) {
        throw new Error(initRes.message || '初始化任务失败')
      }
      const id = initRes.data ? initRes.data.task_id : null
      if (!id) throw new Error('初始化成功但未获取到任务 ID')

      // 第二步：提交配图并启动去味发布流程（已就位图片后端幂等保留）
      const runForm = new FormData()
      matchedImageFiles.forEach(img => runForm.append('images', img))
      if (theme) runForm.append('theme', theme)
      if (voice.trim()) runForm.append('voice', voice.trim())
      if (author.trim()) runForm.append('author', author.trim())
      if (topic.trim()) runForm.append('topic', topic.trim())
      const runRes = await importMdTaskRun(id, runForm)
      if (runRes.code && runRes.code !== 200) {
        throw new Error(runRes.message || '提交失败')
      }
      navigate(`/md/${id}`)
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
          <FileUp size={24} className="text-primary" />
          AI 去味发布
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          选择文章所在文件夹，自动定位 .md 与 images/ 配图，AI 去味改写后发布到微信草稿箱
        </p>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="flex items-center gap-3 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <XCircle size={16} />
          <span className="flex-1">{error}</span>
        </div>
      )}

      {/* 核心输入区 */}
      <div className="rounded-lg border-2 border-primary/20 bg-card p-6 space-y-6">
        {/* 文章 md 选择：label 与选择框同行 */}
        <div>
          <div className="flex items-center gap-2">
            <label className="shrink-0 text-xs font-medium text-muted-foreground">
              文章文件 (markdown) <span className="text-destructive">*</span>
            </label>
            <label className="flex flex-1 items-center gap-3 rounded-lg border border-dashed border-border px-4 py-3 cursor-pointer hover:border-primary/40 transition-colors">
              <FileText size={18} className="text-muted-foreground shrink-0" />
              <span className="text-sm flex-1 truncate">
                {mdFile ? `${mdFile.name}（已定位，点击可重新选择）` : '选择文章所在文件夹（自动定位 .md 与 images/ 配图）'}
              </span>
              <input
                type="file"
                webkitdirectory=""
                className="hidden"
                onChange={e => handleDirSelect(e.target.files)}
              />
            </label>
          </div>
        </div>

        {/* 选择后：标题独占一行，下方左=文章内容，右=图片锚点列表（一行两张） */}
        {mdFile && (
          <>
          {/* 标题 / 话题：label 与输入框同行 */}
          <div className="flex items-center gap-2">
            <label className="shrink-0 text-xs font-medium text-muted-foreground">标题 / 话题</label>
            <input
              type="text"
              value={topic}
              onChange={e => setTopic(e.target.value)}
              className="input flex-1"
              placeholder="自动从文章标题提取，可修改"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* 左下：md 文章内容 */}
            <div className="lg:col-span-2">
              <div className="rounded-md border border-border/70 overflow-hidden shadow-sm">
                {/* 编辑器头部：标题 + 实时统计 */}
                <div className="flex items-center justify-between gap-2 border-b border-border/60 bg-muted/40 px-3 py-2">
                  <span className="text-[11px] font-medium text-muted-foreground">
                    文章内容（.md 原文，可修改，提交时以修改后为准）
                  </span>
                  <span className="text-[11px] tabular-nums text-muted-foreground/70">
                    {mdContent.length} 字符 · {mdContent.split('\n').length} 行
                  </span>
                </div>
                <textarea
                  value={mdContent}
                  onChange={e => setMdContent(e.target.value)}
                  spellCheck={false}
                  className="w-full min-h-[480px] max-h-[640px] resize-y bg-transparent px-3.5 py-3 text-[13px] leading-relaxed font-mono text-foreground placeholder:text-muted-foreground/60 outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="文章内容（.md 原文）"
                />
              </div>
            </div>

            {/* 右：图片锚点列表（一行两张） */}
            <div>
              <div className="flex items-center justify-between gap-2 mb-2">
                <label className="text-xs font-medium text-muted-foreground">
                  图片锚点 <span className="text-muted-foreground/80">（{anchorItems.length} 张{missingImages.length > 0 ? `，${missingImages.length} 缺失` : ''}）</span>
                </label>
                {/* 新增图片：锚点追加到文章末尾 */}
                <label className="inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/5 px-2 py-1 text-[11px] font-medium text-primary cursor-pointer hover:bg-primary/10 transition-colors">
                  <Plus size={12} />
                  新增图片
                  <input
                    type="file"
                    accept="image/*"
                    multiple
                    className="hidden"
                    onChange={e => handleAddImages(e.target.files)}
                  />
                </label>
              </div>
              {mdContent.trim() && anchorItems.length > 0 && (
                <div className="grid grid-cols-2 gap-2">
                  {anchorItems.map(item => (
                    <div key={item.name} className="rounded-md border border-border/70 bg-muted/20 p-1.5">
                      <div className="relative rounded overflow-hidden">
                        {/* 预览：已就位显示图片缩略图，缺失显示默认占位图 */}
                        {item.file && previewUrls[item.name] ? (
                          <img
                            src={previewUrls[item.name]}
                            alt={item.alt || item.name}
                            className="w-full aspect-square object-cover"
                          />
                        ) : (
                          <div className="w-full aspect-square bg-muted/50 flex items-center justify-center">
                            <ImageIcon size={22} className="text-muted-foreground/60" />
                          </div>
                        )}
                        {/* 新增图片：可删除（删除锚点列表与文章末尾锚点行） */}
                        {item.added && (
                          <button
                            type="button"
                            onClick={() => handleRemoveAddedImage(item.name)}
                            title="删除新增图片"
                            className="absolute top-1 left-1 z-10 rounded-full bg-black/60 p-1 text-white hover:bg-destructive transition-colors"
                          >
                            <X size={12} />
                          </button>
                        )}
                        <span className={`absolute top-1 right-1 text-[10px] font-medium px-1.5 py-0.5 rounded ${item.added ? 'bg-primary/90 text-white' : item.exists ? 'bg-emerald-500/90 text-white' : 'bg-destructive/90 text-white'}`}>
                          {item.added ? '新增' : item.exists ? '已就位' : '缺失'}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] text-foreground truncate" title={item.name}>{item.name}</p>
                      <p className="text-[10px] text-muted-foreground truncate" title={item.alt}>{item.alt || '（无描述）'}</p>
                      {/* 已就位可更换，缺失可替换 */}
                      <label className="mt-0.5 inline-block text-[10px] font-medium text-primary cursor-pointer hover:underline">
                        {item.exists ? '更换' : '选择图片替换'}
                        <input
                          type="file"
                          accept="image/*"
                          className="hidden"
                          onChange={e => handleReplaceImage(item.name, e.target.files)}
                        />
                      </label>
                    </div>
                  ))}
                </div>
              )}
              {mdContent.trim() && anchorItems.length === 0 && (
                <p className="text-xs text-muted-foreground">文章未引用本地图片（封面将自动生成）</p>
              )}

              {/* 缺图提示 */}
              {mdContent.trim() && missingImages.length > 0 && (
                <div className="mt-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2.5 text-[11px] text-destructive">
                  <p className="font-medium mb-0.5">
                    以下 {missingImages.length} 张配图缺失（点击「选择图片替换」补齐，或放到 md 同级的 images/ 后重新选文件夹）：
                  </p>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {missingImages.map(i => (
                      <li key={i.name}>{i.name}</li>
                    ))}
                  </ul>
                </div>
              )}
              {mdContent.trim() && anchorItems.length > 0 && allImagesReady && (
                <p className="mt-2 text-[11px] text-emerald-600 flex items-center gap-1">
                  <CheckCircle2 size={14} />
                  文章引用的 {anchorItems.length} 张本地图片均已就位
                </p>
              )}
            </div>
          </div>
          </>
        )}
      </div>

      {/* 发布配置 —— 参考 AI一言发文：作者 / 排版主题 / 语气风格，其余用默认 */}
      <CollapsibleSection title="发布配置 (可修改)" defaultOpen={true}>
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
                placeholder="作者名称（留空用账号默认）"
              />
            </label>

            {/* 排版主题 —— 与 AI一言发文同款 SmartSelect 下拉（hover 预览 iframe） */}
            <label className="block">
              <span className="text-xs font-medium text-muted-foreground mb-1 block">排版主题</span>
              {hasConstants ? (
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
              ) : (
                <input
                  type="text"
                  value={theme}
                  onChange={e => setTheme(e.target.value)}
                  className="input"
                  placeholder="自动 (由 AI 选择)"
                />
              )}
            </label>

          </div>

          {/* 语气风格 */}
          <label className="block">
            <span className="text-xs font-medium text-muted-foreground mb-1 block">语气风格 (voice)</span>
            <textarea
              value={voice}
              onChange={e => setVoice(e.target.value)}
              className="input min-h-[60px] resize-y text-sm"
              rows={2}
              placeholder="描述作者的语气风格、身份、写作偏好，改写时按此调整..."
            />
          </label>
        </div>
      </CollapsibleSection>

      {/* 提交 */}
      <div className="flex justify-end">
        <Button
          onClick={handleSubmit}
          disabled={submitting || !mdFile || !allImagesReady}
          size="lg"
        >
          {submitting ? (
            <Loader2 size={18} className="animate-spin" />
          ) : (
            <Send size={18} />
          )}
          {submitting ? '正在提交并去味改写...' : '提交并开始发布'}
        </Button>
      </div>
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
