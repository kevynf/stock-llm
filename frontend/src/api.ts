import type {
  BatchDeleteResponse,
  ChatSession,
  ChatSummary,
  DeleteResponse,
  HealthStatus,
  LogEntry,
  LogLevelView,
  ModelConfigInput,
  ModelConfigView,
  ModelTestResponse,
  ProviderCheck,
  SelectionRun,
  SkillDefinition,
  StorageScope,
  StorageStatistics,
  StockResearch,
  StockSearchResult,
  Strategy,
  SystemDiagnostics,
  WatchlistItem,
} from './types'

type RuntimeConfig = {
  mode: 'browser' | 'desktop'
  api_origin: string
  token: string | null
}

let runtime: RuntimeConfig = { mode: 'browser', api_origin: '', token: null }
let runtimeInitialization: Promise<RuntimeConfig> | null = null

const API_PROTOCOL_VERSION = 1
const REQUIRED_CAPABILITIES = ['desktop-session-token', 'selection-events', 'system-diagnostics'] as const
const DEFAULT_TIMEOUT_MS = 30_000

export function initializeRuntime() {
  if (!('__TAURI_INTERNALS__' in window)) return Promise.resolve(runtime)
  if (!runtimeInitialization) {
    runtimeInitialization = (async () => {
      const { invoke } = await import('@tauri-apps/api/core')
      runtime = await invoke<RuntimeConfig>('runtime_config')
      return runtime
    })().catch((error) => {
      runtimeInitialization = null
      throw error
    })
  }
  return runtimeInitialization
}

export async function restartBackend() {
  if (runtime.mode !== 'desktop') return
  const { invoke } = await import('@tauri-apps/api/core')
  await invoke('restart_backend')
}

function requestUrl(path: string) {
  const normalizedPath = `/${path.replace(/^\/+/, '')}`
  const origin = runtime.api_origin.trim().replace(/\/+$/, '')
  return origin ? `${origin}${normalizedPath}` : normalizedPath
}

function runtimeHeaders(headers?: HeadersInit) {
  const result = new Headers(headers)
  if (!result.has('Content-Type')) result.set('Content-Type', 'application/json')
  if (runtime.token) result.set('X-StockLLM-Token', runtime.token)
  return result
}

export function eventUrl(path: string) {
  const url = new URL(requestUrl(path), window.location.origin)
  if (runtime.token) url.searchParams.set('desktop_token', runtime.token)
  return url.toString()
}

export async function openDataDirectory() {
  if (runtime.mode !== 'desktop') throw new Error('此操作仅在桌面应用中可用。')
  const { invoke } = await import('@tauri-apps/api/core')
  await invoke('open_data_directory')
}

const httpErrorMessages: Record<number, string> = {
  400: '请求内容有误，请检查后重试。',
  401: '身份验证失败，请检查设置。',
  403: '当前操作没有权限。',
  404: '没有找到请求的内容。',
  409: '当前请求与已有内容冲突。',
  422: '输入内容有误，请检查后重试。',
  429: '请求过于频繁，请稍后再试。',
  500: '服务暂时出错，请稍后重试。',
  502: '服务暂时不可用，请稍后重试。',
  503: '服务暂时不可用，请稍后重试。',
  504: '服务响应超时，请稍后重试。',
}

const genericHttpDetails = new Set([
  'Bad Gateway',
  'Gateway Timeout',
  'Internal Server Error',
  'Not Found',
  'Service Unavailable',
])

async function errorMessage(response: Response) {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null
  const detail = typeof body?.detail === 'string' ? body.detail.trim() : ''
  const fallback = httpErrorMessages[response.status] ?? `请求失败（${response.status}）`
  if (!detail || genericHttpDetails.has(detail)) return fallback
  if (response.status >= 500 && !/[\u3400-\u9fff]/u.test(detail)) return fallback
  return detail
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  let response: Response
  const controller = new AbortController()
  if (init?.signal?.aborted) controller.abort()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  const abort = () => controller.abort()
  init?.signal?.addEventListener('abort', abort, { once: true })
  try {
    response = await fetch(requestUrl(path), {
      ...init,
      signal: controller.signal,
      headers: runtimeHeaders(init?.headers),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (init?.signal?.aborted) throw error
      throw new Error('本地服务响应超时，请重试。')
    }
    throw new Error('无法连接到本地服务，请确认服务已启动。')
  } finally {
    window.clearTimeout(timeout)
    init?.signal?.removeEventListener('abort', abort)
  }
  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function download(path: string, body: unknown, timeoutMs = 120_000): Promise<{ blob: Blob; filename: string }> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(requestUrl(path), {
      method: 'POST',
      signal: controller.signal,
      headers: runtimeHeaders(),
      body: JSON.stringify(body),
    })
    if (!response.ok) throw new Error(await errorMessage(response))
    const disposition = response.headers.get('content-disposition') ?? ''
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'stockllm-diagnostics.zip'
    return { blob: await response.blob(), filename }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('诊断包生成超时，请重试。')
    }
    if (error instanceof TypeError) throw new Error('无法连接到本地服务，请确认服务已启动。')
    throw error
  } finally {
    window.clearTimeout(timeout)
  }
}

export class HealthContractError extends Error {}

export function validateHealth(health: HealthStatus) {
  if (health.status !== 'ok') throw new Error('本地服务尚未就绪。')
  if (health.protocol_version !== API_PROTOCOL_VERSION) {
    throw new HealthContractError(`本地服务协议不匹配（需要 ${API_PROTOCOL_VERSION}，实际 ${health.protocol_version ?? '未知'}）。`)
  }
  const missing = REQUIRED_CAPABILITIES.filter((capability) => !health.capabilities?.includes(capability))
  if (missing.length) throw new HealthContractError(`本地服务缺少必要能力：${missing.join('、')}。`)
}

export const api = {
  health: (timeoutMs = 5_000) => request<HealthStatus>('/api/v1/health', undefined, timeoutMs),
  strategies: (signal?: AbortSignal) => request<Strategy[]>('/api/v1/strategies', signal ? { signal } : undefined),
  runs: (signal?: AbortSignal) => request<SelectionRun[]>('/api/v1/selection-runs', signal ? { signal } : undefined),
  run: (id: string, signal?: AbortSignal) => request<SelectionRun>(`/api/v1/selection-runs/${id}`, signal ? { signal } : undefined),
  deleteRun: (id: string) => request<DeleteResponse>(`/api/v1/selection-runs/${id}`, {
    method: 'DELETE',
  }),
  deleteRuns: (ids: string[]) => request<BatchDeleteResponse>('/api/v1/selection-runs/batch-delete', {
    method: 'POST', body: JSON.stringify({ ids }),
  }),
  createRun: (input: SelectionRun['request']) => request<SelectionRun>('/api/v1/selection-runs', {
    method: 'POST', body: JSON.stringify(input),
  }),
  stock: (code: string, asOf?: string, dataMode: 'demo' | 'live' = 'live') => request<StockResearch>(
    `/api/v1/stocks/${encodeURIComponent(code.trim())}/research?${new URLSearchParams({ data_mode: dataMode, ...(asOf ? { as_of: asOf } : {}) })}`,
    undefined,
    120_000,
  ),
  searchStocks: (query: string, dataMode: 'demo' | 'live' = 'live') => request<StockSearchResult[]>(
    `/api/v1/stocks/search?${new URLSearchParams({ q: query.trim(), data_mode: dataMode })}`,
  ),
  providers: () => request<ProviderCheck[]>('/api/v1/providers/status'),
  checkProviders: () => request<ProviderCheck[]>('/api/v1/providers/status/check', { method: 'POST' }, 120_000),
  watchlist: () => request<WatchlistItem[]>('/api/v1/watchlist'),
  addWatchlist: (code: string, note = '', dataMode: 'demo' | 'live' = 'live') => request<WatchlistItem>('/api/v1/watchlist', {
    method: 'POST', body: JSON.stringify({ code, note, data_mode: dataMode }),
  }),
  importWatchlist: (items: Array<Pick<WatchlistItem, 'code' | 'name' | 'note'>>) => request<WatchlistItem[]>('/api/v1/watchlist/import', {
    method: 'POST', body: JSON.stringify(items),
  }),
  updateWatchlist: (code: string, note: string) => request<WatchlistItem>(`/api/v1/watchlist/${code}`, {
    method: 'PUT', body: JSON.stringify({ note }),
  }),
  deleteWatchlist: (code: string) => request<DeleteResponse>(`/api/v1/watchlist/${code}`, { method: 'DELETE' }),
  deleteWatchlistItems: (ids: string[]) => request<BatchDeleteResponse>('/api/v1/watchlist/batch-delete', {
    method: 'POST', body: JSON.stringify({ ids }),
  }),
  modelConfig: () => request<ModelConfigView>('/api/v1/models/config'),
  saveModelConfig: (input: ModelConfigInput) => request<ModelConfigView>('/api/v1/models/config', {
    method: 'POST', body: JSON.stringify(input),
  }),
  testModel: () => request<ModelTestResponse>('/api/v1/models/test', { method: 'POST' }, 120_000),
  storage: () => request<StorageStatistics>('/api/v1/system/storage'),
  clearStorage: (scopes: StorageScope[]) => request<StorageStatistics>('/api/v1/system/storage/clear', {
    method: 'POST', body: JSON.stringify({ scopes }),
  }),
  diagnostics: () => request<SystemDiagnostics>('/api/v1/system/diagnostics'),
  logs: (level?: string) => {
    const query = new URLSearchParams({ limit: '200' })
    if (level) query.set('level', level)
    return request<LogEntry[]>(`/api/v1/system/logs?${query}`)
  },
  reportClientLog: (input: { level: 'info' | 'warning' | 'error'; event: string; message: string; location?: string }) =>
    request<void>('/api/v1/system/logs/client', { method: 'POST', body: JSON.stringify(input) }),
  setLogLevel: (level: 'normal' | 'detailed') => request<LogLevelView>('/api/v1/system/log-level', {
    method: 'POST', body: JSON.stringify({ level }),
  }),
  exportDiagnostics: (detail: 'basic' | 'detailed') => download('/api/v1/system/diagnostics/export', { detail }),
  skills: () => request<SkillDefinition[]>('/api/v1/skills'),
  chats: () => request<ChatSummary[]>('/api/v1/chats?limit=500'),
  chat: (chatId: string) => request<ChatSession>(`/api/v1/chats/${chatId}`),
  latestChat: (runId?: string, stockCode?: string) => {
    const query = new URLSearchParams()
    if (runId) query.set('run_id', runId)
    if (stockCode) query.set('stock_code', stockCode)
    const suffix = query.toString()
    return request<ChatSession | null>(`/api/v1/chats/latest${suffix ? `?${suffix}` : ''}`)
  },
  createChat: (runId?: string, stockCode?: string) => request<ChatSession>('/api/v1/chats', {
    method: 'POST', body: JSON.stringify({ run_id: runId, stock_code: stockCode }),
  }),
  sendMessage: (chatId: string, content: string, skill: string) => request<ChatSession>(`/api/v1/chats/${chatId}/messages`, {
    method: 'POST', body: JSON.stringify({ content, skill }),
  }, 180_000),
  deleteChat: (chatId: string) => request<void>(`/api/v1/chats/${chatId}`, { method: 'DELETE' }),
  deleteChats: (ids: string[]) => request<BatchDeleteResponse>('/api/v1/chats/batch-delete', {
    method: 'POST', body: JSON.stringify({ ids }),
  }),
}
