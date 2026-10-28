import { create } from 'zustand'

interface ArticleState {
  /** 当前编辑的文章 ID（null = 新建） */
  currentArticleId: number | null
  /** 文章标题 */
  title: string
  /** 文章主题 */
  theme: string
  /** 配图风格 */
  imageStyle: string
  /** 文章结构 */
  articleStructure: string
  /** 开篇钩子 */
  openingHook: string
  /** Markdown 内容 */
  markdown: string
  /** 是否已修改（未保存） */
  isDirty: boolean

  setArticle: (data: Partial<ArticleState>) => void
  setTitle: (title: string) => void
  setTheme: (theme: string) => void
  setImageStyle: (style: string) => void
  setMarkdown: (markdown: string) => void
  reset: () => void
}

const DEFAULT_STATE = {
  currentArticleId: null,
  title: '',
  theme: 'refined-blue',
  imageStyle: 'warm-handdrawn',
  articleStructure: 'teardown',
  openingHook: 'sharp-question',
  markdown: '',
  isDirty: false,
}

export const useArticleStore = create<ArticleState>((set) => ({
  ...DEFAULT_STATE,

  setArticle: (data) => set({ ...data, isDirty: true }),
  setTitle: (title) => set({ title, isDirty: true }),
  setTheme: (theme) => set({ theme, isDirty: true }),
  setImageStyle: (imageStyle) => set({ imageStyle, isDirty: true }),
  setMarkdown: (markdown) => set({ markdown, isDirty: true }),
  reset: () => set(DEFAULT_STATE),
}))
