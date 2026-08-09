const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000'

export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, '') ??
  DEFAULT_API_BASE_URL

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export function resolveApiErrorDetail(
  status: number,
  payload: unknown,
): string {
  if (typeof payload === 'object' && payload !== null) {
    const record = payload as Record<string, unknown>
    const detail = record.detail

    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }

    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0]
      if (typeof first === 'object' && first !== null && 'msg' in first) {
        const message = (first as { msg?: unknown }).msg
        if (typeof message === 'string' && message.trim()) {
          return message
        }
      }
    }

    const message = record.message
    if (typeof message === 'string' && message.trim()) {
      return message
    }
  }

  if (status === 401) {
    return '登录状态已失效，请重新登录'
  }
  if (status === 403) {
    return '当前账号没有权限执行此操作'
  }
  if (status === 404) {
    return '请求的资源不存在或已失效'
  }
  if (status === 422) {
    return '请求参数不符合要求，请检查后重试'
  }
  if (status === 429) {
    return '请求过于频繁或已达到使用额度，请稍后再试'
  }
  if (status >= 500) {
    return '服务端处理异常，请稍后重试'
  }

  return `请求失败：HTTP ${status}`
}

export async function requestJson<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers)

  if (!headers.has('Content-Type') && options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
    })
  } catch {
    throw new ApiError(
      0,
      '无法连接后端服务，请检查 FastAPI 服务或本机网络连接',
    )
  }

  const contentType = response.headers.get('content-type') ?? ''
  let payload: unknown = null

  if (contentType.includes('application/json')) {
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      resolveApiErrorDetail(response.status, payload),
    )
  }

  return payload as T
}
