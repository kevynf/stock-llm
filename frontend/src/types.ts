import type { components } from './generated/openapi'

type ApiSchemas = components['schemas']

export type ViewId = 'selection' | 'history' | 'history-report' | 'research' | 'chats' | 'watchlist' | 'providers' | 'settings'
export type StrategyId = ApiSchemas['StrategyId']
export type CheckState = ApiSchemas['CheckState']
export type DataStatus = ApiSchemas['SourceMeta']['status']
export type DataFreshness = ApiSchemas['Evidence']['freshness']
export type DataResolution = ApiSchemas['Evidence']['resolution']

export type Strategy = ApiSchemas['StrategyDefinition']

export type Evidence = ApiSchemas['Evidence']
export type ResearchCheck = ApiSchemas['ResearchCheck']
export type Candidate = ApiSchemas['Candidate']
export type RankedChoice = ApiSchemas['RankedChoice']
export type SelectionRun = Omit<ApiSchemas['SelectionRun'], 'request'> & {
  request: Required<ApiSchemas['SelectionRun']['request']>
}
export type ChatSession = ApiSchemas['ChatSession']
export type ChatSummary = ApiSchemas['ChatSummary']
export type WatchlistItem = ApiSchemas['WatchlistItem']
export type ProviderCheck = ApiSchemas['ProviderCheck']
export type HealthStatus = ApiSchemas['HealthResponse']
export type StockSearchResult = ApiSchemas['StockSearchResult']
export type DeleteResponse = ApiSchemas['DeleteResponse']
export type BatchDeleteResponse = ApiSchemas['BatchDeleteResponse']
export type ModelConfigInput = ApiSchemas['ModelConfigInput']
export type ModelConfigView = ApiSchemas['ModelConfigView']
export type ModelTestResponse = ApiSchemas['ModelTestResponse']
export type SkillDefinition = ApiSchemas['SkillDefinition']
export type StorageScope = ApiSchemas['StorageCategory']['scope']
export type StorageStatistics = ApiSchemas['StorageStatistics']
export type LogEntry = ApiSchemas['LogEntry']
export type SystemDiagnostics = ApiSchemas['SystemDiagnostics']
export type LogLevelView = ApiSchemas['LogLevelView']

export type StockResearch = ApiSchemas['StockResearch']
