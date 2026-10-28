/** 通用 API 响应包装 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 分页列表响应 */
export interface PaginatedResponse<T = unknown> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

/** 分页请求参数 */
export interface PaginationParams {
  page?: number
  pageSize?: number
}

/** 任务列表查询参数 */
export interface TaskListParams extends PaginationParams {
  status?: string        // 多选用逗号分隔，如 "10,20,40"
  type?: string
  account?: string
  keyword?: string
  created_after?: number // Unix timestamp
  created_before?: number
  sort_by?: string       // 排序字段: id/topic/type/account/status/created_at/updated_at
  sort_order?: string    // 排序方向: asc/desc
}

/** 创建任务请求 */
export interface CreateTaskRequest {
  topic: string
  account?: string
  task_type?: 'article' | 'image' | 'md'
  theme?: string
  image_style?: string
  article_structure?: string
  opening_hook?: string
  voice?: string
  genre?: string
  provider?: string
  no_images?: boolean
  user_details?: string
}

/** 发布请求 */
export interface PublishRequest {
  taskId: number
  syncPlatforms?: string[]
}
