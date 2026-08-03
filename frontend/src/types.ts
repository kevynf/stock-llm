export type ViewId = 'selection' | 'history' | 'history-report' | 'research' | 'chats' | 'watchlist' | 'providers' | 'settings'
export type StrategyId = 'trend' | 'quality' | 'stability'
export type CheckState = 'pass' | 'concern' | 'fail'
export type DataStatus = 'pending' | 'live' | 'historical' | 'cached' | 'demo' | 'unavailable'
export type DataFreshness = 'latest' | 'cached'
export type DataResolution = 'primary' | 'fallback' | 'conflict'

export interface Strategy {
  id: StrategyId
  name: string
  summary: string
  checks: string[]
}

export interface Evidence {
  id: string
  title: string
  value: string
  source: string
  as_of: string
  fetched_at?: string
  freshness: DataFreshness
  resolution: DataResolution
  note?: string
}

export interface ResearchCheck {
  label: string
  state: CheckState
  reason: string
  evidence_ids: string[]
}

export interface Candidate {
  code: string
  name: string
  sector: string
  price: number
  change_pct: number
  checks: ResearchCheck[]
  evidence: Evidence[]
  passed: number
  concerns: number
  completeness: number
}

export interface RankedChoice {
  code: string
  name: string
  reason: string
  recommendation: 'follow' | 'wait' | 'avoid'
  evidence_ids: string[]
}

export interface SelectionRun {
  id: string
  created_at: string
  request: {
    risk_profile: 'conservative' | 'balanced' | 'active'
    horizon: 'short' | 'medium' | 'long'
    strategy: StrategyId
    as_of: string
    data_mode: 'demo' | 'live'
  }
  status: 'pending' | 'running' | 'complete' | 'failed'
  provider: { source: string; as_of: string; fetched_at: string; status: DataStatus }
  candidate_count: number
  excluded_count: number
  candidates: Candidate[]
  ai_selection: {
    top_three: RankedChoice[]
    preferred_code: string | null
    confidence: 'low' | 'medium' | 'high'
    watch_conditions: string[]
    invalidation_signals: string[]
    data_gaps: string[]
    summary: string
    status: 'complete' | 'unavailable' | 'invalid'
  }
  error?: string
}

export interface ChatSession {
  id: string
  run_id: string | null
  stock_code: string | null
  created_at: string
  messages: Array<{
    id: string
    role: 'user' | 'assistant'
    content: string
    created_at: string
    tool_traces: string[]
  }>
}

export interface ChatSummary {
  id: string
  run_id: string | null
  stock_code: string | null
  created_at: string
  updated_at: string
  message_count: number
  preview: string
}

export interface WatchlistItem {
  code: string
  name: string
  note: string
  created_at: string
  updated_at: string
}

export interface StockResearch {
  code: string
  name: string
  sector: string
  price: number
  change_pct: number
  ma20: number
  ma60: number
  rsi: number
  pe: number
  roe: number
  profit_growth: number
  revenue_growth: number
  debt_ratio: number
  financial_as_of?: string
  financial_published_at?: string
  price_as_of?: string
  price_fetched_at?: string
  price_note?: string
  market_as_of?: string
  market_fetched_at?: string
  evidence_sources?: Record<string, string>
  evidence_resolution?: Record<string, { freshness: DataFreshness; resolution: DataResolution; note?: string }>
  volatility_60d: number
  max_drawdown_60d: number
  history: Array<{ date: string; open: number; high: number; low: number; close: number; volume: number }>
  news: Array<{
    kind: '新闻' | '公告'
    content_level: 'summary' | 'title'
    title: string
    published_at: string
    summary: string
    publisher: string
    url: string
    source: string
    channel: string
    fetched_at: string
    freshness: DataFreshness
  }>
  content_fetched_at?: string
  content_scope?: { news: string; notices: string }
  content_errors?: string[]
  source: { source: string; as_of: string; fetched_at: string; status: DataStatus }
}
