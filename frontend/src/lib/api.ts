/**
 * API 客户端 —— 对接 FastAPI 后端。
 */

import type {
  ApiResponse,
  PaginatedResponse,
  TaskListParams,
  CreateTaskRequest,
  PublishRequest,
} from '@/types/api'
import type { Task, TaskDetail } from '@/types/task'
import type { AppConfig, ConfigConstants } from '@/types/config'

// ============================================================
// 配置
// ============================================================

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

/** 获取后端 API 基础 URL */
export function getApiBaseUrl(): string {
  return API_BASE_URL
}

/** 构造任务图片 URL */
export function getTaskImageUrl(taskId: number, localPath: string): string {
  // 兼容旧格式（仅文件名）和新格式（images/文件名）
  let relativePath = localPath.replace(/\\/g, '/')
  if (!relativePath.includes('/')) {
    relativePath = `images/${relativePath}`
  }
  const segments = relativePath.split('/')
  const encoded = segments.map(s => encodeURIComponent(s)).join('/')
  return `${API_BASE_URL}/tasks/${taskId}/files/${encoded}`
}

// ============================================================
// HTTP 封装
// ============================================================

async function request<T>(
  endpoint: string,
  options?: RequestInit,
): Promise<ApiResponse<T>> {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API Error: ${res.status} ${res.statusText} — ${body}`)
  }
  return res.json()
}

// ============================================================
// 任务 API
// ============================================================

/** 获取任务列表 */
export async function getTasks(
  params?: TaskListParams,
): Promise<ApiResponse<PaginatedResponse<Task>>> {
  const query = new URLSearchParams()
  if (params?.page) query.set('page', String(params.page))
  if (params?.pageSize) query.set('pageSize', String(params.pageSize))
  if (params?.status) query.set('status', String(params.status))
  if (params?.type) query.set('type', params.type)
  if (params?.account) query.set('account', params.account)
  if (params?.keyword) query.set('keyword', params.keyword)
  if (params?.created_after) query.set('created_after', String(params.created_after))
  if (params?.created_before) query.set('created_before', String(params.created_before))
  if (params?.sort_by) query.set('sort_by', params.sort_by)
  if (params?.sort_order) query.set('sort_order', params.sort_order)

  return request(`/tasks?${query.toString()}`)
}

/** 获取单个任务详情 */
export async function getTask(id: number): Promise<ApiResponse<TaskDetail>> {
  return request<TaskDetail>(`/tasks/${id}`)
}

/** 创建任务 */
export async function createTask(
  data: CreateTaskRequest,
): Promise<ApiResponse<{ task_id: number }>> {
  return request('/tasks', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** 删除任务 */
export async function deleteTask(
  id: number,
): Promise<ApiResponse<null>> {
  return request(`/tasks/${id}`, { method: 'DELETE' })
}

/** 第一步：导入 md 内容，初始化「AI去味发布」任务（task + task_image 表） */
export async function importMdTaskInit(
  formData: FormData,
): Promise<ApiResponse<{ task_id: number }>> {
  const res = await fetch(`${getApiBaseUrl()}/tasks/import`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API Error: ${res.status} — ${body}`)
  }
  return res.json()
}

/** 第二步：上传配图并启动「AI去味发布」流程 */
export async function importMdTaskRun(
  taskId: number,
  formData: FormData,
): Promise<ApiResponse<{ task_id: number }>> {
  const res = await fetch(`${getApiBaseUrl()}/tasks/import/${taskId}/run`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API Error: ${res.status} — ${body}`)
  }
  return res.json()
}

// ============================================================
// 重试 API
// ============================================================

/** 获取任务重试信息（供确认弹窗使用） */
export async function getRetryInfo(
  taskId: number,
): Promise<ApiResponse<import('@/types/task').RetryInfo>> {
  return request(`/tasks/${taskId}/retry-info`)
}

/** 更新选题简报 */
export async function updateTaskBrief(
  taskId: number,
  content: string,
): Promise<ApiResponse<{ task_id: number; message: string }>> {
  return request(`/tasks/${taskId}/brief`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

/** 更新文章草稿（article.md） */
export async function updateTaskArticle(
  taskId: number,
  content: string,
): Promise<ApiResponse<{ task_id: number; message: string }>> {
  return request(`/tasks/${taskId}/article`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

/** 发起断点重试 */
export async function retryTask(
  taskId: number,
): Promise<ApiResponse<{ task_id: number; retry_from: number; action: string; message: string }>> {
  return request(`/tasks/${taskId}/retry`, { method: 'POST' })
}

// ============================================================
// 发布 API
// ============================================================

/** 发布任务到微信草稿箱 */
export async function publishToWechat(
  data: PublishRequest,
): Promise<ApiResponse<null>> {
  return request('/publish/wechat', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** 多平台同步 */
export async function syncToPlatforms(
  data: PublishRequest,
): Promise<ApiResponse<null>> {
  return request('/publish/sync', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// ============================================================
// 配置 API
// ============================================================

/** 获取当前配置（敏感字段脱敏） */
export async function getConfig(): Promise<ApiResponse<AppConfig>> {
  return request('/config')
}

/** 保存配置 */
export async function saveConfig(
  config: AppConfig,
): Promise<ApiResponse<AppConfig>> {
  return request('/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  })
}

/** 获取下拉框常量元数据 */
export async function getConfigConstants(): Promise<ApiResponse<ConfigConstants>> {
  return request('/config/constants')
}

/** 获取所有已配置账号 */
export async function getAccounts(): Promise<ApiResponse<string[]>> {
  return request('/accounts')
}

// ============================================================
// 公众号管理 API
// ============================================================

/** 草稿条目（列表） */
export interface DraftItem {
  media_id: string
  title: string
  author: string
  digest: string
  url: string
  thumb_url: string
  update_time: number
}

/** 草稿详情 */
export interface DraftDetail {
  media_id: string
  title: string
  author: string
  digest: string
  content: string
  content_source_url: string
  thumb_media_id: string
  show_cover_pic: number
  need_open_comment: number
  only_fans_can_comment: number
  url: string
  thumb_url: string
}

/** 新增/更新草稿请求 */
export interface DraftSaveRequest {
  title: string
  content: string
  author?: string
  digest?: string
  content_source_url?: string
  thumb_media_id?: string
  need_open_comment?: number
  only_fans_can_comment?: number
}

/** 获取微信公众号草稿列表 */
export async function getDraftList(
  offset: number = 0,
  count: number = 20,
): Promise<ApiResponse<{ items: DraftItem[]; total_count: number; item_count: number }>> {
  return request(`/wechat/drafts?offset=${offset}&count=${count}`)
}

/** 获取草稿详情 */
export async function getDraftDetail(
  mediaId: string,
): Promise<ApiResponse<DraftDetail>> {
  return request(`/wechat/drafts/${mediaId}`)
}

/** 新增草稿 */
export async function addDraft(
  data: DraftSaveRequest,
): Promise<ApiResponse<{ media_id: string }>> {
  return request('/wechat/drafts/add', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** 更新草稿 */
export async function updateDraft(
  mediaId: string,
  data: DraftSaveRequest,
): Promise<ApiResponse<Record<string, unknown>>> {
  return request('/wechat/drafts/update', {
    method: 'POST',
    body: JSON.stringify({ media_id: mediaId, index: 0, ...data }),
  })
}

/** 删除草稿 */
export async function deleteDraft(
  mediaId: string,
): Promise<ApiResponse<Record<string, unknown>>> {
  return request('/wechat/drafts/delete', {
    method: 'POST',
    body: JSON.stringify({ media_id: mediaId }),
  })
}

// ============================================================
// 永久素材 API
// ============================================================

/** 素材条目 */
export interface MaterialItem {
  media_id: string
  name: string
  url: string
  update_time: number
}

/** 素材详情 */
export interface MaterialDetail {
  media_id: string
  name: string
  url: string
  data: string
  content_type: string
  material_type: string
  down_url: string
  description: string
  update_time: number
}

/** 获取素材列表 */
export async function getMaterialList(
  materialType: string = 'image',
  offset: number = 0,
  count: number = 20,
): Promise<ApiResponse<{ items: MaterialItem[]; total_count: number; item_count: number }>> {
  return request(`/wechat/materials?material_type=${materialType}&offset=${offset}&count=${count}`)
}

/** 获取素材详情 */
export async function getMaterialDetail(
  mediaId: string,
): Promise<ApiResponse<MaterialDetail>> {
  return request(`/wechat/materials/${mediaId}`)
}

/** 上传素材 */
export async function uploadMaterial(
  file: File,
  materialType: string = 'image',
): Promise<ApiResponse<{ media_id: string; url: string }>> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('material_type', materialType)

  const res = await fetch(`${getApiBaseUrl()}/wechat/materials/upload`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API Error: ${res.status} — ${body}`)
  }
  return res.json()
}

/** 获取主题与图片风格配置 */
export async function getThemeStyles(): Promise<
  ApiResponse<{
    themes: Array<{ code: string; label: string; description: string }>
    image_styles: Array<{ code: string; label: string; keywords: string; topics: string; density: string }>
  }>
> {
  return request('/drafts/config')
}

/** 删除素材 */
export async function deleteMaterial(
  mediaId: string,
): Promise<ApiResponse<Record<string, unknown>>> {
  return request('/wechat/materials/delete', {
    method: 'POST',
    body: JSON.stringify({ media_id: mediaId }),
  })
}

// ============================================================
// 多平台同步 API
// ============================================================

/** 同步状态 */
export type SyncStatus = 'draft' | 'pending' | 'syncing' | 'success' | 'partial' | 'failed'

/** 同步记录列表项 */
export interface SyncTaskItem {
  id: number
  task_id: number
  topic: string
  title: string
  sync_from: 'task' | 'local' | 'url'
  url?: string | null
  file_path?: string | null
  status: SyncStatus
  platforms: string
  platform_count: number
  result_count: number
  created_at: number
  updated_at: number
}

/** 单个平台同步结果 */
export interface SyncResultItem {
  id: number
  task_sync_id: number
  platform: string
  platform_label: string
  status: 'success' | 'failed'
  error_msg: string
  created_at: number
}

/** 同步详情 */
export interface SyncTaskDetail extends SyncTaskItem {
  markdown_content: string
  results: SyncResultItem[]
}

/** 创建同步请求 */
export interface SyncCreateRequest {
  id?: number | null
  task_id?: number | null
  sync_from?: 'task' | 'local' | 'url'
  url?: string | null
  file_path?: string | null
  markdown_content?: string
  platforms: string[]
}

/** 网址获取响应 */
export interface URLFetchResponse {
  markdown_content: string
  title: string
  file_path: string
  images: string[]
}

/** 本地文件上传响应 */
export interface LocalFileUploadResponse {
  markdown_content: string
  file_path: string
  file_name: string
}

/** 获取同步任务列表 */
export async function getSyncTasks(
  params?: { page?: number; pageSize?: number; status?: string; sort_by?: string; sort_order?: string },
): Promise<ApiResponse<PaginatedResponse<SyncTaskItem>>> {
  const query = new URLSearchParams()
  if (params?.page) query.set('page', String(params.page))
  if (params?.pageSize) query.set('page_size', String(params.pageSize))
  if (params?.status) query.set('status', params.status)
  if (params?.sort_by) query.set('sort_by', params.sort_by)
  if (params?.sort_order) query.set('sort_order', params.sort_order)
  return request(`/sync/tasks?${query.toString()}`)
}

/** 获取同步详情 */
export async function getSyncTask(id: number): Promise<ApiResponse<SyncTaskDetail>> {
  return request(`/sync/tasks/${id}`)
}

/** 仅保存同步内容（不执行同步） */
export async function saveSyncTask(
  data: SyncCreateRequest,
): Promise<ApiResponse<SyncTaskDetail>> {
  return request('/sync/tasks/save', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** 创建/执行同步 */
export async function createSyncTask(
  data: SyncCreateRequest,
): Promise<ApiResponse<SyncTaskDetail>> {
  return request('/sync/tasks', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** 重试同步（整体或单个平台） */
export async function retrySyncTask(
  syncId: number,
  platforms?: string[],
): Promise<ApiResponse<SyncTaskDetail>> {
  const query = platforms && platforms.length > 0
    ? `?platforms=${platforms.join(',')}`
    : ''
  return request(`/sync/tasks/${syncId}/retry${query}`, { method: 'POST' })
}

/** 从网址获取内容，转为 Markdown */
export async function fetchUrlContent(
  url: string,
): Promise<ApiResponse<URLFetchResponse>> {
  return request('/sync/fetch-url', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

/** 上传本地 .md 文件到同步目录 */
export async function uploadLocalFile(
  file: File,
): Promise<ApiResponse<LocalFileUploadResponse>> {
  const formData = new FormData()
  formData.append('file', file)

  const res = await fetch(`${getApiBaseUrl()}/sync/upload-local-file`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API Error: ${res.status} — ${body}`)
  }
  return res.json()
}

/** 上传发表内容中的图片（返回 CDN URL，不占素材配额） */
export async function uploadContentImage(
  file: File,
): Promise<ApiResponse<{ url: string }>> {
  const formData = new FormData()
  formData.append('file', file)

  const res = await fetch(`${getApiBaseUrl()}/wechat/materials/upload-content-image`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API Error: ${res.status} — ${body}`)
  }
  return res.json()
}

// ============================================================
// 审核 API
// ============================================================

import type { ReviewListItem, ReviewDetail, ReviewActionRequest, ReviewActionResponse } from '@/types/task'

/** 审核队列查询参数 */
export interface ReviewQueueParams {
  page?: number
  page_size?: number
  status?: string
  task_type?: string
  stage?: number
  sort_by?: string
  sort_order?: string
  date_from?: string
  date_to?: string
}

/** 获取审核队列 */
export async function getReviewQueue(
  params?: ReviewQueueParams,
): Promise<ApiResponse<PaginatedResponse<ReviewListItem>>> {
  const query = new URLSearchParams()
  if (params?.page) query.set('page', String(params.page))
  if (params?.page_size) query.set('page_size', String(params.page_size))
  if (params?.status) query.set('status', params.status)
  if (params?.task_type) query.set('task_type', params.task_type)
  if (params?.stage) query.set('stage', String(params.stage))
  if (params?.sort_by) query.set('sort_by', params.sort_by)
  if (params?.sort_order) query.set('sort_order', params.sort_order)
  if (params?.date_from) query.set('date_from', params.date_from)
  if (params?.date_to) query.set('date_to', params.date_to)
  return request(`/review/queue?${query.toString()}`)
}

/** 获取审核详情 */
export async function getReviewDetail(
  reviewId: number,
): Promise<ApiResponse<ReviewDetail>> {
  return request(`/review/${reviewId}`)
}

/** 通过审核 */
export async function approveReview(
  reviewId: number,
  data: ReviewActionRequest,
): Promise<ApiResponse<ReviewActionResponse>> {
  return request(`/review/${reviewId}/approve`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** 驳回审核 */
export async function rejectReview(
  reviewId: number,
  data: ReviewActionRequest,
): Promise<ApiResponse<ReviewActionResponse>> {
  return request(`/review/${reviewId}/reject`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// ============================================================
// 图片管理 API（审核阶段 stage=60）
// ============================================================

/** 删除任务图片 */
export async function deleteTaskImage(
  taskId: number,
  imageId: number,
): Promise<ApiResponse<{ task_id: number; image_id: number; action: string }>> {
  return request(`/tasks/${taskId}/images/${imageId}`, { method: 'DELETE' })
}

/** 本地上传替换任务图片 */
export async function replaceTaskImage(
  taskId: number,
  imageId: number,
  file: File,
): Promise<ApiResponse<{ task_id: number; image_id: number; action: string; size: number; width: number; height: number }>> {
  const formData = new FormData()
  formData.append('file', file)

  const res = await fetch(`${getApiBaseUrl()}/tasks/${taskId}/images/${imageId}/replace`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API Error: ${res.status} — ${body}`)
  }
  return res.json()
}

/** 更新图片元数据（描述、提示词、风格） */
export async function updateTaskImage(
  taskId: number,
  imageId: number,
  data: { description?: string; prompt?: string; image_style?: string },
): Promise<ApiResponse<{ task_id: number; image_id: number; action: string; fields: string[] }>> {
  return request(`/tasks/${taskId}/images/${imageId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

/** 用新 prompt 重新 AI 生成图片 */
export async function regenerateTaskImage(
  taskId: number,
  imageId: number,
  prompt: string,
): Promise<ApiResponse<{ task_id: number; image_id: number; action: string; size: number; width: number; height: number; provider: string; model: string; duration_ms: number }>> {
  const formData = new FormData()
  formData.append('prompt', prompt)

  const res = await fetch(`${getApiBaseUrl()}/tasks/${taskId}/images/${imageId}/regenerate`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API Error: ${res.status} — ${body}`)
  }
  return res.json()
}

/** 新增图片（审核阶段）：上传到任务 images/ 目录，锚点追加到文章末尾 */
export async function appendTaskImages(
  taskId: number,
  files: File[],
): Promise<ApiResponse<{ task_id: number; added: Array<{ image_id: number; seq: number; local_path: string; description: string; width: number; height: number }> }>> {
  const formData = new FormData()
  files.forEach(f => formData.append('files', f))

  const res = await fetch(`${getApiBaseUrl()}/tasks/${taskId}/images/append`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API Error: ${res.status} — ${body}`)
  }
  return res.json()
}

/** 保存 newspic stage 20 审核编辑（task 字段 + 卡片描述） */
export async function saveNewspicReview(
  taskId: number,
  data: {
    title?: string
    short_text?: string
    image_style?: string
    cards?: Array<{ id: number; description: string }>
  },
): Promise<ApiResponse<{ task_id: number; message: string }>> {
  return request(`/tasks/${taskId}/newspic-review`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}
