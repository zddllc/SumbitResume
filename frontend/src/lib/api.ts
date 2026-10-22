let csrfToken = ''
let unauthorized: (() => void) | null = null

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}
export function setCsrfToken(value: string) { csrfToken = value }
export function onUnauthorized(handler: () => void) { unauthorized = handler }
export function apiUrl(path: string): string {
  return `${import.meta.env.BASE_URL}api/${path.replace(/^\/+/, '')}`
}
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
export async function api<T>(path: string, method = 'GET', body?: object | FormData): Promise<T> {
  const headers: Record<string, string> = { 'X-CSRF-Token': csrfToken }
  let data: BodyInit | undefined
  if (body instanceof FormData) data = body
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; data = JSON.stringify(body) }
  const response = await fetch(apiUrl(path), { method, headers, body: data, credentials: 'same-origin' })
  if (!response.headers.get('content-type')?.includes('application/json')) {
    throw new ApiError(`后端未返回 JSON（${response.status}），请检查 Nginx/API 路径配置`, response.status)
  }
  const result: unknown = await response.json()
  if (!response.ok) {
    if (response.status === 401 && path !== 'auth/login') unauthorized?.()
    const message = record(result) && typeof result.error === 'string' ? result.error : `请求失败 (${response.status})`
    const details = record(result) && Array.isArray(result.details) ? result.details.filter((item): item is string => typeof item === 'string') : []
    throw new ApiError([message, ...details].join('；'), response.status)
  }
  return result as T
}
