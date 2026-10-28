import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Loader2, Search, Check, X, Eye, Edit3, Send, ArrowLeft,
  FileText, Globe, AlertCircle, Save, Upload, Link,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TiptapEditor } from 'shadcn-tiptap-editor'
import { getTasks, getTask, getSyncTask, createSyncTask, saveSyncTask, fetchUrlContent, uploadLocalFile, getConfig } from '@/lib/api'
import { PLATFORM_KEYS, PLATFORM_LABELS, STATUS_LABELS, PLATFORM_CATEGORIES } from '@/lib/constants'
import type { Task, TaskDetail } from '@/types/task'

// ============================================================
// 类型定义
// ============================================================

type EditMode = 'visual' | 'source'
type SyncSource = 'task' | 'local' | 'url'

// ============================================================
// 子组件：任务搜索下拉
// ============================================================

function TaskSearch({ onSelect }: { onSelect: (task: Task) => void }) {
  const [open, setOpen] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const search = useCallback(async (kw: string) => {
    setKeyword(kw)
    if (!kw.trim()) { setTasks([]); return }
    setLoading(true)
    try {
      const res = await getTasks({ keyword: kw, status: '60,70,80,85,88,90', pageSize: 8 })
      if (res.data) setTasks(res.data.items as Task[])
    } catch { setTasks([]) }
    finally { setLoading(false) }
  }, [])

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={keyword}
          onChange={e => { search(e.target.value); setOpen(true) }}
          onFocus={() => { if (tasks.length > 0) setOpen(true) }}
          placeholder="输入关键词搜索任务（仅显示状态 60-90）..."
          className="w-full h-10 pl-9 pr-8 rounded-lg border border-border bg-background text-sm
                     focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50
                     placeholder:text-muted-foreground/60"
        />
        {keyword && (
          <button onClick={() => { setKeyword(''); setTasks([]) }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            <X size={14} />
          </button>
        )}
      </div>

      {open && tasks.length > 0 && (
        <div className="absolute top-full mt-1.5 z-20 w-full bg-card border border-border rounded-lg
                        shadow-lg max-h-72 overflow-y-auto py-1">
          {tasks.map(task => (
            <button
              key={task.id}
              onClick={() => { onSelect(task); setOpen(false); setKeyword(task.topic) }}
              className="w-full text-left px-4 py-2.5 text-sm hover:bg-muted/60 transition-colors
                         flex items-center gap-3"
            >
              <span className="text-xs text-muted-foreground font-mono shrink-0">#{task.id}</span>
              <span className="font-medium text-foreground truncate flex-1">{task.topic}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full shrink-0 ${
                task.status >= 80
                  ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400'
                  : 'bg-muted text-muted-foreground'
              }`}>
                {STATUS_LABELS[task.status] || task.status}
              </span>
            </button>
          ))}
        </div>
      )}
      {open && loading && (
        <div className="absolute top-full mt-1.5 z-20 w-full bg-card border border-border
                        rounded-lg shadow-lg p-6 text-center">
          <Loader2 size={18} className="animate-spin mx-auto text-muted-foreground" />
          <p className="text-xs text-muted-foreground mt-2">搜索中...</p>
        </div>
      )}
    </div>
  )
}


// ============================================================
// 主页面组件
// ============================================================

export function SyncCreate() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const syncId = searchParams.get('syncId')
  const taskId = searchParams.get('taskId')

  // —— 任务 ——
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)
  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null)
  const [loadingTask, setLoadingTask] = useState(false)

  // —— 内容编辑 ——
  const [markdownContent, setMarkdownContent] = useState('')
  const [editMode, setEditMode] = useState<EditMode>('source')

  // —— 平台选择 ——
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([])
  const [platformSearch, setPlatformSearch] = useState('')

  // —— 保存状态 ——
  const [saving, setSaving] = useState(false)

  // —— 同步状态 ——
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // —— 来源选择 ——
  const [syncSource, setSyncSource] = useState<SyncSource>('task')
  const [urlInput, setUrlInput] = useState('')
  const [fetchingUrl, setFetchingUrl] = useState(false)
  const [localFileName, setLocalFileName] = useState('')
  const [fetchTitle, setFetchTitle] = useState('')
  const [syncFilePath, setSyncFilePath] = useState<string | null>(null)
  const [savedSyncId, setSavedSyncId] = useState<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 是否已持久化（URL 带 syncId 或已点击保存），来源类型锁定
  const isLocked = !!(syncId || savedSyncId)

  // ============================================================
  // 从已有 syncId 加载同步数据（draft 状态跳转来的）
  // ============================================================

  useEffect(() => {
    if (!syncId) return
    ;(async () => {
      setLoadingTask(true)
      setError(null)
      try {
        const res = await getSyncTask(Number(syncId))
        if (res.code === 0 && res.data) {
          const sync = res.data
          // 根据 sync_from 设置来源模式
          const from = (sync.sync_from as SyncSource) || 'task'
          setSyncSource(from)
          // 恢复来源相关状态
          setSyncFilePath(sync.file_path || null)
          if (from === 'url' && sync.url) {
            setUrlInput(sync.url)
          }
          if (from === 'local' && sync.file_path) {
            setLocalFileName(sync.file_path.split('/').pop() || sync.file_path.split('\\').pop() || '')
          }
          // 加载关联的任务详情（仅 task 来源）
          if (from === 'task' && sync.task_id) {
            const taskRes = await getTask(sync.task_id)
            if (taskRes.data) {
              setTaskDetail(taskRes.data)
            }
            // 构造简化的 Task 对象用于显示
            setSelectedTask({
              id: sync.task_id,
              topic: sync.topic || '',
              status: taskRes.data?.status || 0,
              type: taskRes.data?.type || '',
              account: taskRes.data?.account || '',
              created_at: sync.created_at,
              updated_at: sync.updated_at,
            } as Task)
          }
          setMarkdownContent(sync.markdown_content || '')
          // 解析 platforms
          try {
            const platforms = JSON.parse(
              typeof sync.platforms === 'string' ? sync.platforms : '[]',
            )
            if (Array.isArray(platforms) && platforms.length > 0) {
              setSelectedPlatforms(platforms)
            }
          } catch { /* ignore */ }
        } else {
          setError('加载同步记录失败: ' + (res.message || '未知错误'))
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : '加载同步记录失败')
      } finally {
        setLoadingTask(false)
      }
    })()
  }, [syncId])

  // ============================================================
  // 从 taskId 参数自动加载任务（syncId 优先）
  // ============================================================

  useEffect(() => {
    if (!taskId || syncId) return
    ;(async () => {
      setLoadingTask(true)
      setError(null)
      try {
        const taskRes = await getTask(Number(taskId))
        if (taskRes.data) {
          const task = taskRes.data
          setTaskDetail(task)
          setSelectedTask({
            id: task.id,
            topic: task.topic || '',
            status: task.status || 0,
            type: task.type || '',
            account: task.account || '',
            created_at: task.created_at,
            updated_at: task.updated_at,
          } as Task)
          setMarkdownContent(task.brief || '')
          // 从任务配置读取同步平台
          if (task.sync_platforms) {
            try {
              const platforms = JSON.parse(task.sync_platforms)
              if (Array.isArray(platforms) && platforms.length > 0) {
                setSelectedPlatforms(platforms)
              }
            } catch { /* ignore */ }
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : '加载任务失败')
      } finally {
        setLoadingTask(false)
      }
    })()
  }, [taskId, syncId])

  // ============================================================
  // 加载用户默认同步平台（仅新建时，无 syncId）
  // ============================================================

  useEffect(() => {
    if (syncId) return
    ;(async () => {
      try {
        const res = await getConfig()
        if (res.code === 0 && res.data) {
          const defaultAccount = res.data.default || Object.keys(res.data.accounts || {})[0]
          const account = res.data.accounts?.[defaultAccount]
          const platforms = account?.sync_platforms || []
          if (platforms.length > 0) {
            setSelectedPlatforms(platforms)
          }
        }
      } catch { /* 加载默认平台失败不影响使用 */ }
    })()
  }, [syncId])

  // ============================================================
  // 选择任务 → 加载详情
  // ============================================================

  const handleTaskSelect = async (task: Task) => {
    setSelectedTask(task)
    setLoadingTask(true)
    setError(null)
    try {
      const res = await getTask(task.id)
      if (res.data) {
        setTaskDetail(res.data)
        setMarkdownContent(res.data.brief || '')
        // 从任务配置读取同步平台
        if (res.data.sync_platforms) {
          try {
            const platforms = JSON.parse(res.data.sync_platforms)
            if (Array.isArray(platforms) && platforms.length > 0) {
              setSelectedPlatforms(platforms)
            }
          } catch { /* ignore */ }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载任务详情失败')
    } finally {
      setLoadingTask(false)
    }
  }

  // ============================================================
  // 本地文件选择
  // ============================================================

  const handleLocalFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError(null)
    setLocalFileName(file.name)
    try {
      const res = await uploadLocalFile(file)
      if (res.code === 0 && res.data) {
        setMarkdownContent(res.data.markdown_content)
        setSyncFilePath(res.data.file_path)
      } else {
        setError(res.message || '上传失败')
        setLocalFileName('')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传失败')
      setLocalFileName('')
    }
  }

  // ============================================================
  // 网址获取
  // ============================================================

  const handleFetchUrl = async () => {
    if (!urlInput.trim()) return
    setFetchingUrl(true)
    setError(null)
    try {
      const res = await fetchUrlContent(urlInput.trim())
      if (res.code === 0 && res.data) {
        setMarkdownContent(res.data.markdown_content)
        setSyncFilePath(res.data.file_path)
        setFetchTitle(res.data.title || '')
        setLocalFileName('')
      } else {
        setError(res.message || '获取失败')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取失败')
    } finally {
      setFetchingUrl(false)
    }
  }

  // ============================================================
  // 平台操作
  // ============================================================

  const togglePlatform = (code: string) => {
    setSelectedPlatforms(prev =>
      prev.includes(code) ? prev.filter(p => p !== code) : [...prev, code],
    )
  }

  const toggleAll = () => {
    if (selectedPlatforms.length >= PLATFORM_KEYS.length) {
      setSelectedPlatforms([])
    } else {
      setSelectedPlatforms([...PLATFORM_KEYS])
    }
  }

  const filteredPlatforms = platformSearch
    ? PLATFORM_KEYS.filter(code => {
        const label = PLATFORM_LABELS[code] || code
        return label.includes(platformSearch) || code.includes(platformSearch)
      })
    : PLATFORM_KEYS

  // ============================================================
  // 保存内容
  // ============================================================

  const handleSave = async () => {
    if (syncSource === 'task' && !selectedTask) {
      setError('请先选择一个任务')
      return
    }
    if (syncSource !== 'task' && !syncFilePath) {
      setError(syncSource === 'url' ? '请先获取网址内容' : '请先上传本地文件')
      return
    }
    if (selectedPlatforms.length === 0) {
      setError('请至少选择一个目标平台')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const res = await saveSyncTask({
        id: savedSyncId || (syncId ? Number(syncId) : undefined),
        task_id: syncSource === 'task' ? selectedTask?.id : undefined,
        sync_from: syncSource,
        url: syncSource === 'url' ? urlInput : undefined,
        file_path: syncFilePath || undefined,
        platforms: selectedPlatforms,
        markdown_content: markdownContent,
      } as unknown as Parameters<typeof saveSyncTask>[0])
      if (res.code === 0) {
        setError(null)
        if (res.data?.id) setSavedSyncId(res.data.id)
      } else {
        setError(res.message || '保存失败')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  // ============================================================
  // 执行同步
  // ============================================================

  const handleSync = async () => {
    if (syncSource === 'task' && !selectedTask) {
      setError('请先选择一个任务')
      return
    }
    if (syncSource !== 'task' && !syncFilePath) {
      setError(syncSource === 'url' ? '请先获取网址内容' : '请先上传本地文件')
      return
    }
    if (selectedPlatforms.length === 0) {
      setError('请至少选择一个目标平台')
      return
    }
    setSyncing(true)
    setError(null)

    try {
      const res = await createSyncTask({
        id: savedSyncId || (syncId ? Number(syncId) : undefined),
        task_id: syncSource === 'task' ? selectedTask?.id : undefined,
        sync_from: syncSource,
        url: syncSource === 'url' ? urlInput : undefined,
        file_path: syncFilePath || undefined,
        platforms: selectedPlatforms,
        markdown_content: markdownContent,
      } as unknown as Parameters<typeof createSyncTask>[0])

      if (res.code === 0 && res.data) {
        // 同步请求成功 → 直接跳转详情页（无论个别平台是否失败）
        navigate(`/sync/${res.data.id}`)
      } else {
        // API 返回错误 → 留在当前页显示错误
        setError(res.message || '同步失败')
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : '同步请求失败'
      setError(msg)
    } finally {
      setSyncing(false)
    }
  }

  // ============================================================
  // 渲染
  // ============================================================

  return (
    <div className="max-w-5xl mx-auto space-y-5 pb-12">
      {/* ========== 页头 ========== */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/sync')}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground
                     transition-colors shrink-0"
        >
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          <h2 className="text-xl font-bold text-foreground tracking-tight">
            {syncId ? '编辑同步' : taskId ? '同步文章' : '新增同步'}
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            {syncId
              ? '继续编辑内容并同步到多个平台'
              : taskId
                ? '将已完成的文章同步到多个平台'
                : '选择已完成的文章，编辑内容并同步到多个平台'}
          </p>
        </div>
      </div>

      {/* ========== 错误提示 ========== */}
      {error && (
        <div className="flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/5
                        px-4 py-3 text-sm text-destructive">
          <AlertCircle size={16} className="shrink-0 mt-0.5" />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError(null)}
            className="shrink-0 text-destructive/60 hover:text-destructive">
            <X size={14} />
          </button>
        </div>
      )}

      {/* ========== ① 选择源文章 ========== */}
      <section className="rounded-xl border border-border bg-card shadow-sm">
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border bg-gradient-to-r from-muted/50 via-muted/30 to-transparent rounded-t-xl">
          <span className="flex items-center justify-center size-7 rounded-lg bg-primary/10
                          text-primary text-xs font-bold shadow-sm shadow-primary/10">1</span>
          <FileText size={17} className="text-primary/70" />
          <h3 className="text-sm font-semibold text-foreground">选择源文章</h3>
          <span className="text-[11px] text-muted-foreground ml-auto">
            选择文章的来源方式
          </span>
        </div>
        <div className="p-6 space-y-5">
          {/* 来源类型 Tab */}
          {!isLocked ? (
            <div className="grid grid-cols-3 gap-2">
              {[
                { key: 'task' as SyncSource, label: '从任务选择', icon: FileText },
                { key: 'local' as SyncSource, label: '上传本地文件', icon: Upload },
                { key: 'url' as SyncSource, label: '网址获取', icon: Globe },
              ].map(tab => {
                const Icon = tab.icon
                const active = syncSource === tab.key
                return (
                  <button
                    key={tab.key}
                    onClick={() => {
                      setSyncSource(tab.key)
                      setMarkdownContent('')
                      setSyncFilePath(null)
                      setFetchTitle('')
                      if (tab.key === 'task') {
                        setLocalFileName('')
                        setUrlInput('')
                      } else if (tab.key === 'local') {
                        setSelectedTask(null)
                        setTaskDetail(null)
                        setUrlInput('')
                        // 直接弹出文件选择窗口
                        setTimeout(() => fileInputRef.current?.click(), 0)
                      } else if (tab.key === 'url') {
                        setSelectedTask(null)
                        setTaskDetail(null)
                        setLocalFileName('')
                      }
                    }}
                    className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border
                                transition-all duration-150 text-sm font-medium ${
                      active
                        ? 'border-primary/50 bg-primary/5 text-primary shadow-sm'
                        : 'border-border text-muted-foreground hover:border-primary/20 hover:text-foreground hover:bg-muted/30'
                    }`}
                  >
                    <Icon size={15} />
                    <span>{tab.label}</span>
                  </button>
                )
              })}
            </div>
          ) : (
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-muted/50 border border-border">
              <span className="text-xs text-muted-foreground">来源类型：</span>
              <span className="text-xs font-semibold text-foreground">
                {syncSource === 'task' ? '从任务选择' : syncSource === 'local' ? '上传本地文件' : '抓取网址'}
              </span>
            </div>
          )}

          {/* === task 模式：任务搜索 === */}
          {syncSource === 'task' && (
            <div>
              <TaskSearch onSelect={handleTaskSelect} />

              {/* 加载中 */}
              {loadingTask && (
                <div className="flex items-center gap-2.5 mt-4 px-1 text-sm text-muted-foreground">
                  <Loader2 size={15} className="animate-spin" />
                  正在加载文章内容...
                </div>
              )}

              {/* 已选择任务信息 */}
              {selectedTask && taskDetail && (
                <div className="mt-4 flex flex-wrap items-center gap-2.5 px-1">
                  <span className="text-xs text-muted-foreground">已选择</span>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md
                                  bg-primary/10 text-primary text-xs font-mono font-medium">
                    #{selectedTask.id}
                  </span>
                  <span className="text-sm font-medium text-foreground truncate max-w-[300px]">
                    {selectedTask.topic}
                  </span>
                  {taskDetail.title && (
                    <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                      — {taskDetail.title}
                    </span>
                  )}
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                    selectedTask.status >= 80
                      ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400'
                      : 'bg-muted text-muted-foreground'
                  }`}>
                    {STATUS_LABELS[selectedTask.status] || selectedTask.status}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    字数 {taskDetail.word_count?.toLocaleString() || 0}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* === local 模式：隐藏文件选择器 === */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".md"
            onChange={handleLocalFile}
            className="hidden"
          />
          {syncSource === 'local' && (
            localFileName ? (
              <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <FileText size={14} className="text-emerald-500" />
                <span>{localFileName}</span>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                从本地的 .md 文件获取文章内容，点击上方「上传本地文件」重新选择
              </p>
            )
          )}

          {/* === url 模式：网址输入 === */}
          {syncSource === 'url' && (
            <div>
              <div className="flex items-center gap-2">
                <div className="relative flex-1 max-w-lg">
                  <Link size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="url"
                    value={urlInput}
                    onChange={e => setUrlInput(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') handleFetchUrl() }}
                    placeholder="输入目标文章网址 https://..."
                    className="w-full h-10 pl-9 pr-3 rounded-lg border border-border bg-background text-sm
                               focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50
                               placeholder:text-muted-foreground/60"
                  />
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleFetchUrl}
                  disabled={fetchingUrl || !urlInput.trim()}
                  className="gap-1.5 shrink-0"
                >
                  {fetchingUrl ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Globe size={14} />
                  )}
                  获取
                </Button>
              </div>
              {fetchTitle && (
                <p className="text-sm text-muted-foreground mt-2 flex items-center gap-1.5">
                  <FileText size={14} className="text-emerald-500" />
                  已获取：{fetchTitle}
                </p>
              )}
              <p className="text-xs text-muted-foreground mt-2">
                输入文章网址，系统将自动获取并转为 Markdown 格式加载到编辑器中。
              </p>
            </div>
          )}
        </div>
      </section>

      {/* ========== ② 编辑内容 ========== */}
      {(syncSource === 'task' ? taskDetail : markdownContent) && (
        <section className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-border bg-muted/30">
            <div className="flex items-center gap-2.5">
              <span className="flex items-center justify-center size-6 rounded-full bg-primary/10
                              text-primary text-xs font-bold">2</span>
              <Edit3 size={16} className="text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">编辑文章内容</h3>
            </div>
            {/* 保存 + 模式切换 */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium
                           bg-primary/10 text-primary hover:bg-primary/20 transition-all
                           disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Save size={13} />
                )}
                保存
              </button>
              <div className="flex items-center gap-1 bg-muted rounded-lg p-0.5">
              <button
                onClick={() => setEditMode('visual')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  editMode === 'visual'
                    ? 'bg-card text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <Eye size={13} />
                可视化编辑
              </button>
              <button
                onClick={() => setEditMode('source')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  editMode === 'source'
                    ? 'bg-card text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <FileText size={13} />
                Markdown 源码
              </button>
            </div>
          </div>
          </div>

          <div className="p-5">
            {editMode === 'visual' ? (
              <div className="rounded-lg border border-border overflow-hidden">
                <div className="tiptap-auto-height [&_[class*='ProseMirror']]:min-h-[400px]
                                [&_[class*='ProseMirror']]:overflow-visible"
                     style={{ overflow: 'visible' }}>
                  <TiptapEditor
                    content={markdownContent}
                    onChange={(html: string) => setMarkdownContent(html)}
                    editable={true}
                    placeholder="开始编辑文章内容..."
                    contentClassName="min-h-[400px] p-5"
                  />
                  <style>{`
                    .tiptap-auto-height [class*="ProseMirror"] {
                      overflow: visible !important;
                      height: auto !important;
                      min-height: 400px;
                    }
                  `}</style>
                </div>
              </div>
            ) : (
              <textarea
                value={markdownContent}
                onChange={e => setMarkdownContent(e.target.value)}
                className="w-full min-h-[420px] rounded-lg border border-border bg-background
                           p-4 font-mono text-sm leading-relaxed resize-y
                           focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50
                           placeholder:text-muted-foreground/50"
                placeholder="# 文章标题

开始编写 Markdown 内容..."
              />
            )}
          </div>
        </section>
      )}

      {/* ========== ③ 选择平台 ========== */}
      {(syncSource === 'task' ? taskDetail : markdownContent) && (
        <section className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-border bg-muted/30">
            <div className="flex items-center gap-2.5">
              <span className="flex items-center justify-center size-6 rounded-full bg-primary/10
                              text-primary text-xs font-bold">3</span>
              <Globe size={16} className="text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">选择目标平台</h3>
              <span className="text-xs text-muted-foreground">
                （已选 {selectedPlatforms.length}/{PLATFORM_KEYS.length}）
              </span>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={platformSearch}
                onChange={e => setPlatformSearch(e.target.value)}
                placeholder="筛选平台..."
                className="w-28 h-7 rounded-md border border-border bg-background px-2.5 text-xs
                           focus:outline-none focus:ring-1 focus:ring-primary/30"
              />
              <button onClick={toggleAll}
                className="text-xs text-primary hover:underline shrink-0">
                {selectedPlatforms.length >= PLATFORM_KEYS.length ? '取消全选' : '全选所有'}
              </button>
            </div>
          </div>

          <div className="p-5 space-y-5">
            {platformSearch ? (
              // 搜索模式：平铺显示
              <div className="flex flex-wrap gap-2">
                {filteredPlatforms.map(code => {
                  const selected = selectedPlatforms.includes(code)
                  return (
                    <button
                      key={code}
                      onClick={() => togglePlatform(code)}
                      className={`group inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-2
                                  text-sm font-medium transition-all duration-150
                                  ${selected
                                    ? 'border-primary/40 bg-primary/5 text-primary shadow-sm shadow-primary/5'
                                    : 'border-border bg-background text-muted-foreground hover:border-primary/20 hover:text-foreground hover:bg-muted/30'
                                  }`}
                    >
                      <span className={`flex items-center justify-center size-4 rounded border
                                       transition-all duration-150 ${
                        selected
                          ? 'bg-primary border-primary text-primary-foreground scale-105'
                          : 'border-muted-foreground/30 group-hover:border-muted-foreground/50'
                      }`}>
                        {selected && <Check size={10} strokeWidth={3} />}
                      </span>
                      {PLATFORM_LABELS[code] || code}
                    </button>
                  )
                })}
              </div>
            ) : (
              // 分类模式：按类别分组
              PLATFORM_CATEGORIES.map(cat => {
                const visiblePlatforms = cat.platforms.filter(p => PLATFORM_KEYS.includes(p as typeof PLATFORM_KEYS[number]))
                if (visiblePlatforms.length === 0) return null
                const catSelected = visiblePlatforms.filter(p => selectedPlatforms.includes(p)).length
                return (
                  <div key={cat.name} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        {cat.name}
                      </h4>
                      <span className="text-[10px] text-muted-foreground/60">
                        {catSelected}/{visiblePlatforms.length}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2 pl-0">
                      {visiblePlatforms.map(code => {
                        const selected = selectedPlatforms.includes(code)
                        return (
                          <button
                            key={code}
                            onClick={() => togglePlatform(code)}
                            className={`group inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5
                                        text-[13px] font-medium transition-all duration-150
                                        ${selected
                                          ? 'border-primary/40 bg-primary/5 text-primary shadow-sm shadow-primary/5'
                                          : 'border-border bg-background text-muted-foreground hover:border-primary/20 hover:text-foreground hover:bg-muted/30'
                                        }`}
                          >
                            <span className={`flex items-center justify-center size-3.5 rounded border
                                             transition-all duration-150 ${
                              selected
                                ? 'bg-primary border-primary text-primary-foreground scale-105'
                                : 'border-muted-foreground/30 group-hover:border-muted-foreground/50'
                            }`}>
                              {selected && <Check size={9} strokeWidth={3} />}
                            </span>
                            {PLATFORM_LABELS[code] || code}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )
              })
            )}
            {platformSearch && filteredPlatforms.length === 0 && (
              <p className="text-sm text-muted-foreground py-8 w-full text-center">
                未找到匹配的平台
              </p>
            )}
          </div>
        </section>
      )}

      {/* ========== ④ 同步中 ========== */}
      {syncing && (
        <section className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
          <div className="flex items-center justify-center gap-3 px-5 py-8">
            <Loader2 size={20} className="animate-spin text-primary" />
            <span className="text-sm text-muted-foreground">正在同步到 {selectedPlatforms.length} 个平台...</span>
          </div>
        </section>
      )}

      {/* ========== 底部操作栏 ========== */}
      {(syncSource === 'task' ? taskDetail : markdownContent) && (
        <div className="flex items-center justify-between pt-2">
          <p className="text-xs text-muted-foreground">
            {selectedPlatforms.length > 0
              ? `将对文章同步到 ${selectedPlatforms.length} 个平台`
              : '请至少选择一个目标平台'}
          </p>
          <Button
            onClick={handleSync}
            disabled={syncing || selectedPlatforms.length === 0}
            size="lg"
            className="gap-2 px-6"
          >
            {syncing ? (
              <>
                <Loader2 size={17} className="animate-spin" />
                同步中...
              </>
            ) : (
              <>
                <Send size={17} />
                开始同步（{selectedPlatforms.length} 个平台）
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  )
}
