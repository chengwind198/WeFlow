/** 任务状态码映射 */
export const STATUS_LABELS: Record<number, string> = {
  0: '出错了',
  10: '已创建',
  20: '选题已就绪',
  30: '调研完成',
  35: '贴图已规划',
  40: '文章已写好',
  50: '人味化完成',
  60: '配图已生成',
  70: 'HTML 已转换',
  80: 'AI 味通过',
  85: 'AI 味未过',
  88: '发布失败',
  90: '已发布',
}

/** 任务类型 */
export const TASK_TYPES = {
  NEWS: 'article',
  NEWSPIC: 'image',
  MD: 'md',
} as const

/** AI 检测结论 */
export const AI_VERDICT = {
  PASS: 'PASS',
  WARN: 'WARN',
  FAIL: 'FAIL',
} as const

/** AI 检测阈值 */
export const AI_SCORE = {
  PASS_MAX: 35,
  WARN_MAX: 55,
  FAIL_THRESHOLD: 45,
} as const

/** 侧边栏宽度 */
export const SIDEBAR = {
  EXPANDED: 240,
  COLLAPSED: 64,
} as const

/** 导航项配置（支持嵌套子菜单） */
export interface NavItem {
  id: string
  label: string
  icon: string
  path: string
  children?: NavItem[]
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: '仪表盘', icon: 'LayoutDashboard', path: '/' },
  { id: 'articles', label: 'AI一言发文', icon: 'PenLine', path: '/articles/new' },
  { id: 'newspic', label: 'AI一言贴图', icon: 'Image', path: '/newspic/new' },
  { id: 'md-publish', label: 'AI去味发布', icon: 'FileUp', path: '/md/new' },
  { id: 'tasks', label: '任务列表', icon: 'ClipboardCheck', path: '/tasks' },
  { id: 'review', label: '人工审核', icon: 'Eye', path: '/review' },
  { id: 'sync', label: '多平台同步', icon: 'RefreshCw', path: '/sync' },
  { id: 'themes', label: '主题 & 风格', icon: 'Palette', path: '/themes' },
  {
    id: 'wechat-mgmt', label: '公众号管理', icon: 'LayoutDashboard', path: '',
    children: [
      { id: 'wechat-messages', label: '草稿管理', icon: 'ClipboardCheck', path: '/wechat/drafts' },
      { id: 'wechat-materials', label: '永久素材', icon: 'Image', path: '/wechat/materials' },
    ],
  },
  { id: 'settings', label: '配置管理', icon: 'Settings', path: '/settings' },
]

/** 配置页 LLM provider 列表 */
export const LLM_PROVIDER_KEYS = ['deepseek', 'openai', 'zhipu', 'doubao', 'minimax'] as const

/** 配置页图片 provider 列表 */
export const IMAGE_PROVIDER_KEYS = [
  'openai', 'gemini_proxy', 'z_image', 'krea_2_turbo',
  'qwen_image', 'z_image_turbo_bailian', 'wan_image_bailian',
] as const

/** 图片生成平台选项 */
/** 图片平台元数据；baseUrl 缺省表示由用户自行填写 */
export interface ImagePlatformMeta {
  code: string
  label: string
  baseUrl?: string
  providers: string[]
}

export const IMAGE_PLATFORMS: ImagePlatformMeta[] = [
  { code: 'dashscope', label: 'DashScope (百炼)', baseUrl: 'https://dashscope.aliyuncs.com/api/v1', providers: ['qwen_image', 'z_image_turbo_bailian', 'wan_image_bailian'] },
  { code: 'modelscope', label: 'ModelScope', baseUrl: 'https://api-inference.modelscope.cn/', providers: ['z_image', 'krea_2_turbo'] },
  { code: 'gemini_proxy', label: 'Gemini Proxy', providers: ['gemini_proxy'] },
  { code: 'openai', label: 'OpenAI', providers: ['openai'] },
]

/** 同步平台选项 */
export const PLATFORM_KEYS = [
  'zhihu', 'bilibili', 'weixin', 'zip-download', 'x', 'xiaohongshu',
  'juejin', 'weibo', 'baijiahao', 'csdn', 'yuque', 'douban',
  'sohu', 'xueqiu', 'woshipm', '51cto', 'imooc', 'oschina',
  'segmentfault', 'cnblogs', 'eastmoney', 'dayu', 'douyin',
  'jianshu', 'netease', 'smzdm', 'sohufocus', 'toutiao', 'yidian',
] as const

/** 平台分类 */
export const PLATFORM_CATEGORIES: { name: string; platforms: string[] }[] = [
  {
    name: '技术开发者',
    platforms: ['csdn', 'juejin', '51cto', 'oschina', 'segmentfault', 'cnblogs', 'imooc', 'woshipm', 'yuque'],
  },
  {
    name: '自媒体资讯',
    platforms: ['baijiahao', 'sohu', 'dayu', 'netease', 'toutiao', 'yidian'],
  },
  {
    name: '社交互动',
    platforms: ['zhihu', 'weibo', 'douban', 'x', 'xiaohongshu', 'jianshu', 'weixin'],
  },
  {
    name: '视频与图文',
    platforms: ['bilibili', 'douyin'],
  },
  {
    name: '垂直行业',
    platforms: ['xueqiu', 'eastmoney', 'smzdm', 'sohufocus'],
  },
]

/** 平台代码 → 中文标签 */
export const PLATFORM_LABELS: Record<string, string> = {
  zhihu: '知乎',
  bilibili: '哔哩哔哩',
  weixin: '微信公众号',
  'zip-download': 'Markdown 压缩包',
  x: 'X (Twitter)',
  xiaohongshu: '小红书',
  juejin: '掘金',
  weibo: '微博',
  baijiahao: '百家号',
  csdn: 'CSDN',
  yuque: '语雀',
  douban: '豆瓣',
  sohu: '搜狐号',
  xueqiu: '雪球',
  woshipm: '人人都是产品经理',
  '51cto': '51CTO',
  imooc: '慕课手记',
  oschina: '开源中国',
  segmentfault: '思否',
  cnblogs: '博客园',
  eastmoney: '东方财富',
  dayu: '大鱼号',
  douyin: '抖音图文',
  jianshu: '简书',
  netease: '网易号',
  smzdm: '什么值得买',
  sohufocus: '搜狐焦点',
  toutiao: '头条',
  yidian: '一点号',
}
