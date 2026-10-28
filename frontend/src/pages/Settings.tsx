import { useState, useEffect, useCallback, type ReactNode } from 'react'
import {
  Save, Eye, EyeOff, ChevronDown, ChevronRight, CheckCircle, AlertCircle,
  XCircle, Loader2, RotateCw, Plus, Trash2, X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SmartSelect } from '@/components/SmartSelect'
import { getConfig, saveConfig, getConfigConstants } from '@/lib/api'
import { useConfigStore } from '@/stores/useConfigStore'
import { IMAGE_PLATFORMS, PLATFORM_KEYS } from '@/lib/constants'
import type {
  AppConfig, AccountConfig, LLMProviderConfig,
  ImageGenerationConfig, ImageProviderConfig,
  ConfigConstants,
} from '@/types/config'

// ============================================================
// 空模板
// ============================================================

function emptyAccount(): AccountConfig {
  return {
    name: '',
    app_id: '',
    app_secret: '',
    author: '',
    theme: '',
    image_style: '',
    newspic_image_style: '',
    article_structure: '',
    opening_hook: '',
    voice: '',
    genre: '',
    sync_platforms: [],
    review_enabled: false,
    review_stages: { article: [], image: [] },
  }
}

function emptyLLMProvider(): LLMProviderConfig {
  return { api_key: '', base_url: '', model: '' }
}

function emptyImageProvider(): ImageProviderConfig {
  return { platform: '', api_key: '', base_url: '', model: '', size: '' }
}

/** image_generation 是开放映射，provider 字段为字符串，取值时需先排除它 */
function imageProviderOf(
  cfg: ImageGenerationConfig | undefined,
  key: string,
): ImageProviderConfig | undefined {
  const value = cfg?.[key]
  return typeof value === 'object' ? value : undefined
}

// ============================================================
// 页面入口
// ============================================================

export function Settings() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [constants, setConstants] = useState<ConfigConstants | null>(null)
  const [activeAccount, setActiveAccount] = useState<string>('main')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const setGlobalConfig = useConfigStore(s => s.setConfig)

  // Modal 状态
  const [addModal, setAddModal] = useState<{ type: 'account' | 'llm' | 'image'; open: boolean }>({ type: 'account', open: false })
  const [addModalKey, setAddModalKey] = useState('')
  const [addModalName, setAddModalName] = useState('')
  const [addModalError, setAddModalError] = useState('')

  // 追踪新添加的 Provider（用于默认展开）
  const [newlyAdded, setNewlyAdded] = useState<Set<string>>(new Set())

  // 加载
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [cfgRes, constRes] = await Promise.all([
        getConfig(),
        getConfigConstants(),
      ])
      if (cfgRes.data) {
        setConfig(cfgRes.data)
        setGlobalConfig(cfgRes.data)
        const defaultAccount = cfgRes.data.default || Object.keys(cfgRes.data.accounts || {})[0] || 'main'
        setActiveAccount(defaultAccount)
      }
      if (constRes.data) setConstants(constRes.data)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载配置失败')
    } finally {
      setLoading(false)
    }
  }, [setGlobalConfig])

  useEffect(() => { load() }, [load])

  // --- 更新函数 ---

  const updateConfig = useCallback(<K extends keyof AppConfig>(key: K, value: AppConfig[K]) => {
    setConfig(prev => prev ? { ...prev, [key]: value } : prev)
  }, [])

  const updateAccount = useCallback((accountKey: string, field: keyof AccountConfig, value: unknown) => {
    setConfig(prev => {
      if (!prev) return prev
      return {
        ...prev,
        accounts: {
          ...prev.accounts,
          [accountKey]: { ...prev.accounts[accountKey], [field]: value },
        },
      }
    })
  }, [])

  const updateLLMProvider = useCallback((provider: string, field: keyof LLMProviderConfig, value: string) => {
    setConfig(prev => {
      if (!prev) return prev
      return {
        ...prev,
        llm_providers: {
          ...prev.llm_providers,
          providers: {
            ...prev.llm_providers.providers,
            [provider]: { ...(prev.llm_providers.providers[provider] || emptyLLMProvider()), [field]: value },
          },
        },
      }
    })
  }, [])

  const updateImageProvider = useCallback((provider: string, field: string, value: string) => {
    setConfig(prev => {
      if (!prev) return prev
      return {
        ...prev,
        image_generation: {
          ...prev.image_generation,
          [provider]: { ...(imageProviderOf(prev.image_generation, provider) || emptyImageProvider()), [field]: value },
        } as AppConfig['image_generation'],
      }
    })
  }, [])

  const updateImageGenField = useCallback((field: string, value: string) => {
    setConfig(prev => {
      if (!prev) return prev
      return {
        ...prev,
        image_generation: { ...prev.image_generation, [field]: value },
      }
    })
  }, [])

  // --- 保存 ---
  const handleSave = useCallback(async () => {
    if (!config) return
    setSaving(true)
    setToast(null)
    try {
      await saveConfig(config)
      setGlobalConfig(config)
      const timer = setTimeout(() => setToast(null), 5000)
      setToast({ type: 'success', message: '配置已保存' })
      return () => clearTimeout(timer)
    } catch (e) {
      setToast({ type: 'error', message: e instanceof Error ? e.message : '保存失败' })
    } finally {
      setSaving(false)
    }
  }, [config, setGlobalConfig])

  // --- 账号增删 ---
  const openAddAccount = () => {
    setAddModalKey('')
    setAddModalName('')
    setAddModalError('')
    setAddModal({ type: 'account', open: true })
  }

  const confirmAddAccount = () => {
    const trimmed = addModalKey.trim()
    if (!trimmed) { setAddModalError('请输入账号标识'); return }
    if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(trimmed)) { setAddModalError('仅支持英文、数字、下划线、连字符，且以字母开头'); return }
    if (config?.accounts?.[trimmed]) { setAddModalError(`账号 "${trimmed}" 已存在`); return }
    setConfig(prev => {
      if (!prev) return prev
      const acc = emptyAccount()
      if (addModalName.trim()) acc.name = addModalName.trim()
      return { ...prev, accounts: { ...prev.accounts, [trimmed]: acc } }
    })
    setActiveAccount(trimmed)
    setAddModal({ type: 'account', open: false })
  }

  const deleteAccount = (key: string) => {
    const accountKeys = Object.keys(config?.accounts || {})
    if (accountKeys.length <= 1) {
      alert('至少保留一个账号')
      return
    }
    if (!confirm(`确定删除账号 "${key}"？此操作不可撤销。`)) return
    setConfig(prev => {
      if (!prev) return prev
      const next = { ...prev.accounts }
      delete next[key]
      const newDefault = prev.default === key ? Object.keys(next)[0] : prev.default
      return { ...prev, accounts: next, default: newDefault }
    })
    if (activeAccount === key) {
      const remaining = Object.keys(config?.accounts || {}).filter(k => k !== key)
      setActiveAccount(remaining[0] || 'main')
    }
  }

  // --- LLM Provider 增删 ---
  const openAddLLMProvider = () => {
    setAddModalKey('')
    setAddModalError('')
    setAddModal({ type: 'llm', open: true })
  }

  const confirmAddLLMProvider = () => {
    const trimmed = addModalKey.trim()
    if (!trimmed) { setAddModalError('请输入 Provider 标识'); return }
    if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(trimmed)) { setAddModalError('仅支持英文、数字、下划线、连字符，且以字母开头'); return }
    if (config?.llm_providers?.providers?.[trimmed]) { setAddModalError(`Provider "${trimmed}" 已存在`); return }
    setConfig(prev => {
      if (!prev) return prev
      return {
        ...prev,
        llm_providers: {
          ...prev.llm_providers,
          providers: { ...prev.llm_providers.providers, [trimmed]: emptyLLMProvider() },
        },
      }
    })
    setNewlyAdded(prev => new Set(prev).add(`llm:${trimmed}`))
    setAddModal({ type: 'llm', open: false })
  }

  const deleteLLMProvider = (key: string) => {
    if (!confirm(`确定删除 LLM Provider "${key}"？`)) return
    setConfig(prev => {
      if (!prev) return prev
      const next = { ...prev.llm_providers.providers }
      delete next[key]
      const newDefault = prev.llm_providers.default === key
        ? (Object.keys(next)[0] || 'deepseek')
        : prev.llm_providers.default
      return {
        ...prev,
        llm_providers: {
          default: newDefault,
          providers: next,
        },
      }
    })
  }

  // --- Image Provider 增删 ---
  const openAddImageProvider = () => {
    setAddModalKey('')
    setAddModalError('')
    setAddModal({ type: 'image', open: true })
  }

  const confirmAddImageProvider = () => {
    const trimmed = addModalKey.trim()
    if (!trimmed) { setAddModalError('请输入 Provider 标识'); return }
    if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(trimmed)) { setAddModalError('仅支持英文、数字、下划线、连字符，且以字母开头'); return }
    if (imageProviderOf(config?.image_generation, trimmed)) { setAddModalError(`Provider "${trimmed}" 已存在`); return }
    setConfig(prev => {
      if (!prev) return prev
      return {
        ...prev,
        image_generation: {
          ...prev.image_generation,
          [trimmed]: { platform: '', api_key: '', base_url: '', image_model: '', size: '' },
        } as AppConfig['image_generation'],
      }
    })
    setNewlyAdded(prev => new Set(prev).add(`img:${trimmed}`))
    setAddModal({ type: 'image', open: false })
  }

  const deleteImageProvider = (key: string) => {
    if (!confirm(`确定删除图片 Provider "${key}"？`)) return
    setConfig(prev => {
      if (!prev) return prev
      const next = { ...prev.image_generation } as Record<string, unknown>
      delete next[key]
      return { ...prev, image_generation: next as AppConfig['image_generation'] }
    })
  }

  // 图片 provider 列表（排除 provider / openai / gemini_proxy 等元字段，只保留实际provider配置对象）
  const imageProviderKeys = Object.keys(config?.image_generation || {}).filter(
    k => k !== 'provider' && typeof config?.image_generation?.[k] === 'object'
  )

  // --- 加载态 ---
  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="animate-spin text-muted-foreground" size={28} />
      </div>
    )
  }

  if (error || !config) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3">
        <XCircle size={40} className="text-destructive" />
        <p className="text-sm text-muted-foreground">{error || '无法加载配置'}</p>
        <Button variant="outline" size="sm" onClick={load}>
          <RotateCw size={14} /> 重试
        </Button>
      </div>
    )
  }

  const accounts = Object.keys(config.accounts || {})
  const account = config.accounts[activeAccount]
  const llmProviders = Object.keys(config.llm_providers?.providers || {})
  const hasConstants = constants != null

  return (
    <div className="space-y-6 pb-8">
      {/* 页头 */}
      <div>
        <h2 className="text-page-title text-foreground">配置管理</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          管理微信账号、AI大模型提供商、图片生成等配置
        </p>
      </div>

      {/* Toast —— 固定定位，始终可见 */}
      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-lg border px-4 py-3 shadow-overlay transition-all ${
          toast.type === 'success'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
            : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300'
        }`}>
          {toast.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          <span className="text-sm">{toast.message}</span>
          <button
            onClick={() => setToast(null)}
            className="ml-2 text-current opacity-50 hover:opacity-100 transition-opacity"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* ══════════════════════════════════════════════
          账号配置（默认账号 + Tabs + 基本信息 + 创作配置）
          ══════════════════════════════════════════════ */}
      <ConfigSection icon="👤" title="账号配置" onSave={handleSave} saving={saving}>
        {/* 默认账号选择 */}
        <div className="flex items-center gap-3 mb-4 rounded-lg bg-primary/5 border border-primary/20 px-4 py-3">
          <span className="text-sm font-medium text-primary">⭐ 默认账号</span>
          <select
            value={config.default || 'main'}
            onChange={e => updateConfig('default', e.target.value)}
            className="input max-w-[220px] font-medium"
          >
            {accounts.map(k => (
              <option key={k} value={k}>{config.accounts[k]?.name ? `${config.accounts[k].name} (${k})` : k}</option>
            ))}
          </select>
        </div>

        {/* 账号 Tabs */}
        <div className="flex items-end gap-1 border-b border-border mb-4">
          {accounts.map(key => (
            <div key={key} className="flex items-center">
              <button
                onClick={() => setActiveAccount(key)}
                className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors -mb-[1px] ${
                  key === activeAccount
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                {config.accounts[key]?.name ? `${config.accounts[key].name} (${key})` : key}
              </button>
              {accounts.length > 1 && (
                <button
                  onClick={() => deleteAccount(key)}
                  className="ml-0.5 mr-1 p-0.5 text-muted-foreground hover:text-destructive transition-colors"
                  title={`删除账号 ${key}`}
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          ))}
          <button
            onClick={openAddAccount}
            className="px-2 py-2 text-sm text-muted-foreground hover:text-primary transition-colors -mb-[1px]"
            title="添加账号"
          >
            <Plus size={16} />
          </button>
        </div>

        {account && (
          <>
            {/* 账号基本信息 */}
            <div className="mb-4">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">基本信息</h4>
              <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                <Field label="账号名称">
                  <input
                    type="text"
                    value={account.name || ''}
                    onChange={e => updateAccount(activeAccount, 'name', e.target.value)}
                    className="input"
                  />
                </Field>
                <Field label="标识（key）">
                  <input
                    type="text"
                    value={activeAccount}
                    readOnly
                    className="input font-mono text-muted-foreground bg-muted/50 cursor-not-allowed"
                  />
                </Field>
                <Field label="作者名称">
                  <input
                    type="text"
                    value={account.author || ''}
                    onChange={e => updateAccount(activeAccount, 'author', e.target.value)}
                    className="input"
                  />
                </Field>
                <Field label="App ID">
                  <input
                    type="text"
                    value={account.app_id || ''}
                    onChange={e => updateAccount(activeAccount, 'app_id', e.target.value)}
                    className="input font-mono"
                  />
                </Field>
                <SecretField
                  label="App Secret"
                  value={account.app_secret || ''}
                  onChange={v => updateAccount(activeAccount, 'app_secret', v)}
                />
              </div>
            </div>

            {/* 文章创作配置 */}
            <div>
              <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">创作配置</h4>
              <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                {hasConstants && (
                  <SmartSelect
                    label="排版主题"
                    value={account.theme || ''}
                    options={constants.themes.map(t => ({
                      value: t.code,
                      label: `${t.label} (${t.code})`,
                      info: `${t.description}`,
                      tooltip: `${t.description}\ncode: ${t.code}`,
                    }))}
                    placeholder="自动 (由 AI 选择)"
                    onChange={v => updateAccount(activeAccount, 'theme', v)}
                    previewType="theme"
                  />
                )}

                {hasConstants && (
                  <SmartSelect
                    label="配图风格 (文章模式)"
                    value={account.image_style || ''}
                    options={constants.image_styles
                      .filter(s => s.for_news)
                      .map(s => ({
                        value: s.code,
                        label: `${s.label} (${s.code})`,
                        info: `${s.keywords} · ${s.topics}`,
                        tooltip: `${s.keywords}\n${s.topics}\n密度: ${s.density}\ncode: ${s.code}`,
                      }))}
                    placeholder="自动 (由 AI 选择)"
                    onChange={v => updateAccount(activeAccount, 'image_style', v)}
                    previewType="image-style"
                  />
                )}

                {hasConstants && (
                  <SmartSelect
                    label="配图风格 (贴图模式)"
                    value={account.newspic_image_style || ''}
                    options={constants.image_styles
                      .filter(s => s.for_newspic)
                      .map(s => ({
                        value: s.code,
                        label: `${s.label} (${s.code})`,
                        info: `${s.keywords} · ${s.topics}`,
                        tooltip: `${s.keywords}\n${s.topics}\n密度: ${s.density}\ncode: ${s.code}`,
                      }))}
                    placeholder="自动 (由 AI 选择)"
                    onChange={v => updateAccount(activeAccount, 'newspic_image_style', v)}
                    previewType="image-style"
                  />
                )}

                {hasConstants && (
                  <SmartSelect
                    label="文章结构"
                    value={account.article_structure || ''}
                    options={constants.article_structures.map(s => ({
                      value: s.code,
                      label: `${s.label} (${s.code})`,
                      info: `${s.topics}`,
                      tooltip: `${s.label}\n适合: ${s.topics}\n${s.flow}\ncode: ${s.code}`,
                    }))}
                    placeholder="自动 (由 AI 选择)"
                    onChange={v => updateAccount(activeAccount, 'article_structure', v)}
                  />
                )}

                {hasConstants && (
                  <SmartSelect
                    label="开篇钩子"
                    value={account.opening_hook || ''}
                    options={constants.opening_hooks.map(h => ({
                      value: h.code,
                      label: `${h.label} (${h.code})`,
                      info: h.tip,
                      tooltip: `✅ ${h.tip}\n⚠️ ${h.avoid}\ncode: ${h.code}`,
                    }))}
                    placeholder="自动 (由 AI 选择)"
                    onChange={v => updateAccount(activeAccount, 'opening_hook', v)}
                  />
                )}
              </div>

              {/* 语气风格 */}
              <div className="mt-4">
                <Field label="语气风格 (voice)">
                  <textarea
                    value={account.voice || ''}
                    onChange={e => updateAccount(activeAccount, 'voice', e.target.value)}
                    className="input min-h-[80px] resize-y"
                    rows={3}
                    placeholder="描述作者的语气风格、身份、写作偏好..."
                  />
                </Field>
              </div>

              {/* 同步平台 */}
              {hasConstants && (
                <div className="mt-4">
                  <label className="block mb-2 text-sm font-medium text-foreground">
                    同步平台
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {PLATFORM_KEYS.map(p => {
                      const platforms = (account.sync_platforms || []) as string[]
                      const checked = platforms.includes(p)
                      const meta = constants.platforms.find(m => m.code === p)
                      return (
                        <label
                          key={p}
                          className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm cursor-pointer transition-colors ${
                            checked
                              ? 'border-primary/40 bg-primary/5 text-primary'
                              : 'border-border text-muted-foreground hover:border-muted-foreground/40'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => {
                              const next = checked
                                ? platforms.filter(x => x !== p)
                                : [...platforms, p]
                              updateAccount(activeAccount, 'sync_platforms', next)
                            }}
                            className="sr-only"
                          />
                          {meta?.label || p}
                        </label>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* 审核配置 */}
              <div className="mt-4 pt-4 border-t border-border">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={account.review_enabled || false}
                    onChange={() => updateAccount(activeAccount, 'review_enabled', !account.review_enabled)}
                    className="size-4 rounded"
                  />
                  <span className="text-sm font-medium text-foreground">启用审核 ( 启用后，Pipeline 在指定节点暂停，待人工审核通过后继续执行 )</span>
                </label>
                <div
                  className="grid transition-[grid-template-rows] duration-200 ease-out"
                  style={{ gridTemplateRows: account.review_enabled ? '1fr' : '0fr' }}
                >
                  <div className="overflow-hidden min-h-0">
                    <div className="mt-4 ml-7 space-y-3">
                      {/* 审核节点选择 */}
                      <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                        <Field label="图文">
                          <div className="flex gap-3">
                            {[
                              { value: 20, label: '选题简报 (需审核)' },
                              { value: 40, label: '文章草稿 (需审核)' },
                              { value: 60, label: '配图 (需审核)' },
                            ].map(stage => {
                              const reviewStages = account.review_stages || {}
                              const newsStages = reviewStages.article || []
                              const checked = newsStages.includes(stage.value)
                              return (
                                <label
                                  key={`news-${stage.value}`}
                                  className="flex items-center gap-2 cursor-pointer"
                                >
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    onChange={() => {
                                      const next = checked
                                        ? newsStages.filter((s: number) => s !== stage.value)
                                        : [...newsStages, stage.value].sort()
                                      updateAccount(activeAccount, 'review_stages', {
                                        ...reviewStages,
                                        article: next,
                                      })
                                    }}
                                    className="size-4 rounded border-input accent-amber-500"
                                  />
                                  <span className="text-sm text-muted-foreground">{stage.label}</span>
                                </label>
                              )
                            })}
                          </div>
                        </Field>
                        <Field label="贴图">
                          <div className="flex gap-3">
                            {[
                              { value: 20, label: '选题简报 (需审核)' },
                              { value: 60, label: '贴图 (需审核)' },
                            ].map(stage => {
                              const reviewStages = account.review_stages || {}
                              const newspicStages = reviewStages.image || []
                              const checked = newspicStages.includes(stage.value)
                              return (
                                <label
                                  key={`newspic-${stage.value}`}
                                  className="flex items-center gap-2 cursor-pointer"
                                >
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    onChange={() => {
                                      const next = checked
                                        ? newspicStages.filter((s: number) => s !== stage.value)
                                        : [...newspicStages, stage.value].sort()
                                      updateAccount(activeAccount, 'review_stages', {
                                        ...reviewStages,
                                        image: next,
                                      })
                                    }}
                                    className="size-4 rounded border-input accent-amber-500"
                                  />
                                  <span className="text-sm text-muted-foreground">{stage.label}</span>
                                </label>
                              )
                            })}
                          </div>
                        </Field>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </ConfigSection>

      {/* ══════════════════════════════════════════════
          AI大模型提供商
          ══════════════════════════════════════════════ */}
      <ConfigSection icon="🤖" title="AI大模型提供商" onSave={handleSave} saving={saving}>
        <div className="mb-4 rounded-lg bg-primary/5 border border-primary/20 px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-primary whitespace-nowrap">⭐ 默认 Provider</span>
            <select
              value={config.llm_providers?.default || llmProviders[0] || ''}
              onChange={e => updateConfig('llm_providers', {
                ...config.llm_providers,
                default: e.target.value,
              })}
              className="input font-medium"
            >
              {llmProviders.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="space-y-3">
          {llmProviders.map(provider => (
            <ProviderCard
              key={provider}
              name={provider}
              isDefault={config.llm_providers?.default === provider}
              defaultOpen={false}
              forceOpen={newlyAdded.has(`llm:${provider}`)}
              onDelete={llmProviders.length > 1 ? () => deleteLLMProvider(provider) : undefined}
            >
              <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                <SecretField
                  label="API Key"
                  value={config.llm_providers?.providers?.[provider]?.api_key || ''}
                  onChange={v => updateLLMProvider(provider, 'api_key', v)}
                />
                <Field label="Base URL">
                  <input
                    type="text"
                    value={config.llm_providers?.providers?.[provider]?.base_url || ''}
                    onChange={e => updateLLMProvider(provider, 'base_url', e.target.value)}
                    className="input font-mono text-xs"
                  />
                </Field>
                <Field label="Model">
                  <input
                    type="text"
                    value={config.llm_providers?.providers?.[provider]?.model || ''}
                    onChange={e => updateLLMProvider(provider, 'model', e.target.value)}
                    className="input"
                  />
                </Field>
              </div>
            </ProviderCard>
          ))}
          <button
            onClick={openAddLLMProvider}
            className="flex w-full items-center justify-center gap-1 rounded-md border border-dashed border-border py-2 text-xs text-muted-foreground hover:border-primary/50 hover:text-primary transition-colors"
          >
            <Plus size={14} /> 添加 LLM Provider
          </button>
        </div>
      </ConfigSection>

      {/* ══════════════════════════════════════════════
          图片生成配置
          ══════════════════════════════════════════════ */}
      <ConfigSection icon="🖼️" title="图片生成配置" onSave={handleSave} saving={saving}>
        <div className="mb-4 rounded-lg bg-primary/5 border border-primary/20 px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-primary whitespace-nowrap">⭐ 默认 Provider</span>
            <select
              value={config.image_generation?.provider || imageProviderKeys[0] || ''}
              onChange={e => updateImageGenField('provider', e.target.value)}
              className="input font-medium"
            >
              {imageProviderKeys.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="space-y-3">
          {imageProviderKeys.map(provider => {
            const imgCfg = imageProviderOf(config.image_generation, provider)
            const platformCode = imgCfg?.platform || ''
            const platformMeta = IMAGE_PLATFORMS.find(p => p.code === platformCode)
            return (
            <ProviderCard
              key={provider}
              name={provider}
              isDefault={config.image_generation?.provider === provider}
              defaultOpen={false}
              forceOpen={newlyAdded.has(`img:${provider}`)}
              onDelete={imageProviderKeys.length > 1 ? () => deleteImageProvider(provider) : undefined}
            >
              <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                <Field label="平台">
                  <select
                    value={imgCfg?.platform || ''}
                    onChange={e => {
                      const newPlatform = e.target.value
                      updateImageProvider(provider, 'platform', newPlatform)
                      // 自动填入平台默认 Base URL（用户已修改则保留）
                      const meta = IMAGE_PLATFORMS.find(p => p.code === newPlatform)
                      if (meta?.baseUrl) {
                        const currentBaseUrl = imgCfg?.base_url || ''
                        const isCustom = currentBaseUrl && !IMAGE_PLATFORMS.some(p => p.baseUrl === currentBaseUrl)
                        if (!isCustom) {
                          updateImageProvider(provider, 'base_url', meta.baseUrl)
                        }
                      }
                    }}
                    className="input"
                  >
                    <option value="">默认 (未指定)</option>
                    {IMAGE_PLATFORMS.map(pl => (
                      <option key={pl.code} value={pl.code}>{pl.label}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Model">
                  <input
                    type="text"
                    value={
                      imgCfg?.image_model
                      || imgCfg?.model
                      || ''
                    }
                    onChange={e => updateImageProvider(provider, 'image_model', e.target.value)}
                    className="input"
                  />
                </Field>
                <SecretField
                  label="API Key"
                  value={imgCfg?.api_key || ''}
                  onChange={v => updateImageProvider(provider, 'api_key', v)}
                />
                <Field label="Base URL">
                  <input
                    type="text"
                    value={imgCfg?.base_url || ''}
                    onChange={e => updateImageProvider(provider, 'base_url', e.target.value)}
                    className="input font-mono text-xs"
                    placeholder={platformMeta?.baseUrl || ''}
                  />
                </Field>
                <Field label="Size (可选)">
                  <input
                    type="text"
                    value={imgCfg?.size || ''}
                    onChange={e => updateImageProvider(provider, 'size', e.target.value)}
                    className="input"
                    placeholder="如 1024x1024, 2K"
                  />
                </Field>
              </div>
            </ProviderCard>
            )
          })}
          <button
            onClick={openAddImageProvider}
            className="flex w-full items-center justify-center gap-1 rounded-md border border-dashed border-border py-2 text-xs text-muted-foreground hover:border-primary/50 hover:text-primary transition-colors"
          >
            <Plus size={14} /> 添加图片 Provider
          </button>
        </div>
      </ConfigSection>

      {/* ══════════════════════════════════════════════
          其他
          ══════════════════════════════════════════════ */}
      <ConfigSection icon="⚙️" title="其他" onSave={handleSave} saving={saving}>
        <div className="grid grid-cols-2 gap-x-6 gap-y-3">
          <Field label="产物输出目录">
            <input
              type="text"
              value={config.generated_task_dir || 'generated'}
              onChange={e => updateConfig('generated_task_dir', e.target.value)}
              className="input"
            />
          </Field>
          <SecretField
            label="多平台同步 Token"
            value={config.integrations?.wechatsync_mcp_token || ''}
            onChange={v => updateConfig('integrations', {
              ...config.integrations,
              wechatsync_mcp_token: v,
            })}
          />
        </div>
      </ConfigSection>

      {/* 添加 Modal */}
      {addModal.open && (
        <Modal
          title={addModal.type === 'account' ? '添加账号' : addModal.type === 'llm' ? '添加 LLM Provider' : '添加图片 Provider'}
          onClose={() => setAddModal({ ...addModal, open: false })}
        >
          <div className="space-y-4">
            {addModal.type === 'account' && (
              <Field label="账号名称">
                <input
                  type="text"
                  value={addModalName}
                  onChange={e => setAddModalName(e.target.value)}
                  className="input"
                  placeholder="如：我的公众号"
                  autoFocus
                />
              </Field>
            )}
            <Field label={addModal.type === 'account' ? '账号标识' : 'Provider 标识'}>
              <input
                type="text"
                value={addModalKey}
                onChange={e => { setAddModalKey(e.target.value); setAddModalError('') }}
                className="input font-mono"
                autoFocus={addModal.type !== 'account'}
                placeholder={addModal.type === 'account'
                  ? '字母开头，英文/数字/下划线/连字符，如：tech'
                  : '字母开头，英文/数字/下划线/连字符，如：deepseek'}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    addModal.type === 'account' ? confirmAddAccount() :
                    addModal.type === 'llm' ? confirmAddLLMProvider() : confirmAddImageProvider()
                  }
                }}
              />
            </Field>
            {addModalError && (
              <p className="text-sm text-destructive bg-destructive/5 rounded-md px-3 py-2">{addModalError}</p>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setAddModal({ ...addModal, open: false })}>
                取消
              </Button>
              <Button onClick={
                addModal.type === 'account' ? confirmAddAccount :
                addModal.type === 'llm' ? confirmAddLLMProvider : confirmAddImageProvider
              }>
                确认添加
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ============================================================
// 内部组件
// ============================================================

/** 通用 Modal 弹窗 */
function Modal({
  title, children, onClose,
}: {
  title: string; children: ReactNode; onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-overlay">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-semibold text-foreground">{title}</h3>
          <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors">
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

function ConfigSection({
  icon, title, children, defaultOpen = true, onSave, saving = false,
}: {
  icon: string; title: string; children: ReactNode; defaultOpen?: boolean
  onSave?: () => void; saving?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="rounded-lg border border-border bg-card">
      <div className="flex items-center gap-2 px-4 py-3">
        <button
          onClick={() => setOpen(!open)}
          className="flex flex-1 items-center gap-2 text-sm font-medium text-foreground hover:text-primary transition-colors"
        >
          <span>{icon}</span>
          <span>{title}</span>
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
        {onSave && (
          <Button size="sm" onClick={onSave} disabled={saving}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            <span className="ml-1.5">{saving ? '保存中...' : '保存'}</span>
          </Button>
        )}
      </div>
      {open && <div className="px-4 pb-4">{children}</div>}
    </section>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex items-center gap-3">
      <span className="text-xs font-medium text-muted-foreground w-24 shrink-0">{label}</span>
      <div className="flex-1">{children}</div>
    </label>
  )
}

function SecretField({
  label, value, onChange,
}: {
  label: string; value: string; onChange: (v: string) => void
}) {
  const [visible, setVisible] = useState(false)
  return (
    <Field label={label}>
      <div className="relative">
        <input
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={e => onChange(e.target.value)}
          className="input pr-10 font-mono"
        />
        <button
          type="button"
          onClick={() => setVisible(!visible)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          title={visible ? '隐藏' : '显示'}
        >
          {visible ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
    </Field>
  )
}

function ProviderCard({
  name, isDefault, children, defaultOpen = false, onDelete, forceOpen = false,
}: {
  name: string; isDefault: boolean; children: ReactNode; defaultOpen?: boolean
  onDelete?: () => void; forceOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen || forceOpen)
  return (
    <div className="rounded-md border border-border">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-foreground hover:bg-muted/50 transition-colors rounded-t-md"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="flex-1 text-left">{name}</span>
        {isDefault && (
          <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded">
            默认
          </span>
        )}
      </button>
      {open && (
        <div className="px-3 pb-3">
          {children}
          {onDelete && (
            <button
              onClick={e => { e.stopPropagation(); onDelete() }}
              className="mt-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-destructive transition-colors"
            >
              <Trash2 size={12} /> 删除此 Provider
            </button>
          )}
        </div>
      )}
    </div>
  )
}
