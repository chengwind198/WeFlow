/** 文章/排版主题 */
export interface ThemeInfo {
  code: string
  label: string
  description: string
}

/** 配图风格 */
export interface ImageStyleInfo {
  code: string
  label: string
  keywords: string
  topics: string
  density: '低' | '中' | '高'
  isNewspic: boolean
  isNews: boolean
}

/** 文章结构 */
export interface ArticleStructureInfo {
  code: string
  label: string
  topics: string
  flow: string
}

/** 开篇钩子 */
export interface OpeningHookInfo {
  code: string
  label: string
  tip: string
  avoid: string
}

/** 文章列表项（前端视图模型） */
export interface ArticleListItem {
  id: number
  title: string
  topic: string
  status: number
  statusLabel: string
  aiVerdict: string | null
  aiScore: number | null
  theme: string
  themeLabel: string
  imageStyle: string
  wordCount: number
  author: string
  createdAt: number
  updatedAt: number
}
