/**
 * 任务相关 TypeScript 类型定义。
 * 与后端 constants.py / db/models.py 保持一致。
 */

/** 任务类型 */
export type TaskType = 'article' | 'image' | 'md'

/** 任务状态 */
export type TaskStatus =
  | 0   // 出错了
  | 10  // 已创建
  | 20  // 选题已就绪
  | 30  // 调研完成
  | 35  // 贴图已规划
  | 40  // 文章已写好
  | 50  // 人味化完成
  | 60  // 配图已生成
  | 70  // HTML 已转换
  | 80  // AI 味通过
  | 85  // AI 味未过
  | 88  // 发布失败
  | 90  // 已发布

/** AI 检测结论 */
export type AIVerdict = 'PASS' | 'WARN' | 'FAIL'

/** Pipeline 阶段标识 */
export type Stage =
  | 'understand_requirements'
  | 'search_and_research'
  | 'write_draft'
  | 'generate'
  | 'humanize'
  | 'html_convert'
  | 'ai_score'
  | 'publish'
  | 'sync'

/** 对话消息角色 */
export type MessageRole = 'system' | 'user' | 'assistant' | 'tool'

/** 发布平台 */
export type Platform = 'wechat' | 'zhihu' | 'juejin' | 'csdn' | 'toutiao'

/** 任务记录（列表项） */
export interface Task {
  id: number
  topic: string
  title: string
  account: string
  type: TaskType
  status: TaskStatus
  status_label?: string
  task_path?: string
  author?: string
  theme: string
  image_style: string
  article_structure?: string
  opening_hook?: string
  voice?: string
  genre?: string
  short_text?: string
  user_details?: string
  need_images?: number
  word_count: number
  ai_score: number | null
  ai_verdict: AIVerdict | null
  created_at: number
  updated_at: number
}

/** 任务详情（GET /tasks/:id 完整响应） */
export interface TaskDetail extends Task {
  account_name: string
  author: string
  voice: string
  brief: string
  markdown: string
  html: string
  images: TaskImage[]
  messages: TaskMessage[]
  status_history: TaskStatusHistory[]
  sync_platforms?: string
  publish_records?: PublishRecord[]
  review_records?: TaskReview[]
}

/** 任务状态历史 */
export interface TaskStatusHistory {
  id: number
  task_id: number
  to_status: TaskStatus
  to_label: string
  business_key: string
  to_info: string
  remark: string
  operator: string
  duration_s: number
  created_at: number
}

/** 对话消息 */
export interface TaskMessage {
  id: number
  task_id: number
  stage: Stage
  role: MessageRole
  content: string
  seq: number
  created_at: number
}

/** LLM 调用日志 */
export interface LLMCallLog {
  id: number
  task_id: number
  stage: Stage
  provider: string
  model: string
  call_type: 'text' | 'image'
  input_tokens: number
  output_tokens: number
  latency_ms: number
  created_at: number
}

/** 图片记录 */
export interface TaskImage {
  id: number
  task_id: number
  message_id: number
  seq: number
  anchor: string
  description: string
  prompt: string
  provider: string
  model: string
  image_style: string
  size: string
  local_path: string
  local_size: number
  width: number
  height: number
  format: string
  upload_status: 'pending' | 'generated' | 'generate_failed' | 'uploading' | 'uploaded' | 'failed' | 'skipped'
  upload_cdn_url: string
  upload_media_id: string
  is_cover: number
  created_at: number
}

/** 发布记录 */
export interface PublishRecord {
  id: number
  task_id: number
  platform: Platform
  publish_type: 'draft' | 'publish'
  status: 'pending' | 'submitted' | 'success' | 'failed'
  media_id: string
  url: string
  error_msg: string
  created_at: number
}

/** 审核记录 */
export interface TaskReview {
  id: number
  task_id: number
  stage: number
  status: 'pending' | 'approved' | 'rejected'
  reviewer: string
  comment: string
  created_at: number
  updated_at: number
}

/** 审核队列列表项（含关联任务信息） */
export interface ReviewListItem extends TaskReview {
  topic: string
  type: TaskType
  account: string
}

/** 审核详情（含任务路径信息） */
export interface ReviewDetail extends ReviewListItem {
  task_status: TaskStatus
  task_path: string
  images?: TaskImage[]
  /** newspic stage 20 结构化审核字段 */
  task_title?: string
  short_text?: string
  image_style?: string
  cards?: Array<{
    id: number
    seq: number
    description: string
    image_style?: string
    prompt?: string
  }>
}

/** 审核操作请求 */
export interface ReviewActionRequest {
  reviewer: string
  comment: string
}

/** 审核操作响应 */
export interface ReviewActionResponse {
  review_id: number
  task_id: number
  action: 'approved' | 'rejected'
  message: string
}

/** 任务重试信息 */
export interface RetryInfo {
  retryable: boolean
  current_status: TaskStatus
  current_status_label: string
  action: string
  action_label: string
  description: string
  cost_hint: string
  retry_from: number
  retry_from_label: string
}
