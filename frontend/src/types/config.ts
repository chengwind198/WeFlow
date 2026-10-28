/** 账号配置 */
export interface AccountConfig {
  name: string
  app_id: string
  app_secret: string
  author: string
  theme: string
  image_style: string
  newspic_image_style: string
  article_structure: string
  opening_hook: string
  voice: string
  genre: string
  sync_platforms: string[]
  review_enabled: boolean
  review_stages: Record<string, number[]>
}

/** LLM Provider 配置 */
export interface LLMProviderConfig {
  api_key: string
  base_url: string
  model: string
}

/** 图片 Provider 配置 */
export interface ImageProviderConfig {
  platform: string
  api_key: string
  base_url: string
  image_model?: string
  model?: string
  size?: string
  negative_prompt?: string
}

/** 图片生成配置：provider 为当前默认 Provider 标识，其余键为用户在设置页自行增删的 Provider */
export interface ImageGenerationConfig {
  provider: string
  [providerKey: string]: ImageProviderConfig | string
}

/** AI大模型提供商集合配置 */
export interface LLMProvidersConfig {
  default: string
  providers: Record<string, LLMProviderConfig>
}

/** 集成配置 */
export interface IntegrationsConfig {
  wechatsync_mcp_token: string
}

/** 应用配置（对应 config.yaml） */
export interface AppConfig {
  default: string
  accounts: Record<string, AccountConfig>
  llm_providers: LLMProvidersConfig
  image_generation: ImageGenerationConfig
  generated_task_dir: string
  integrations: IntegrationsConfig
}

// ============================================================
// 常量元数据类型（来自 GET /config/constants）
// ============================================================

export interface ThemeMeta {
  code: string
  label: string
  description: string
}

export interface ImageStyleMeta {
  code: string
  label: string
  keywords: string
  topics: string
  density: string
  for_news: boolean
  for_newspic: boolean
}

export interface ArticleStructureMeta {
  code: string
  label: string
  topics: string
  flow: string
}

export interface OpeningHookMeta {
  code: string
  label: string
  tip: string
  avoid: string
}

export interface GenreMeta {
  code: string
  label: string
  purpose: string
  features: string
}

export interface PlatformMeta {
  code: string
  label: string
}

export interface ProviderMeta {
  code: string
  label: string
}

export interface ConfigConstants {
  themes: ThemeMeta[]
  image_styles: ImageStyleMeta[]
  article_structures: ArticleStructureMeta[]
  opening_hooks: OpeningHookMeta[]
  genres: GenreMeta[]
  platforms: PlatformMeta[]
  llm_providers: ProviderMeta[]
  image_providers: ProviderMeta[]
}
