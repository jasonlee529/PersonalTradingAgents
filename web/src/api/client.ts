import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Portfolio
export interface TradeRecord {
  id: number
  symbol: string
  action: string
  quantity: number
  price: number
  old_quantity: number
  new_quantity: number
  reason: string
  commission: number
  tax: number
  other_fees: number
  amount: number
  raw_source_id: string
  recorded_at: string
}

export const portfolioApi = {
  list: () => api.get('/portfolio/holdings'),
  add: (data: { symbol: string; market?: string; quantity?: number; avg_cost?: number }) =>
    api.post('/portfolio/holdings', data),
  remove: (symbol: string) => api.delete(`/portfolio/holdings/${symbol}`),
  updatePosition: (symbol: string, data: { quantity: number; avg_cost: number; current_price?: number | null; unrealized_pnl?: number | null; override_reason?: string }) =>
    api.patch(`/portfolio/holdings/${encodeURIComponent(symbol)}/position`, data),
  refreshPrices: () => api.post('/portfolio/refresh-prices'),
  trades: (params?: { symbol?: string; limit?: number }) =>
    api.get('/portfolio/trades', { params }),
}

// Stocks
export const stockApi = {
  quote: (symbol: string) => api.get(`/stocks/${symbol}/quote`),
  kline: (symbol: string, period?: string, limit?: number) =>
    api.get(`/stocks/${symbol}/kline`, { params: { period, limit } }),
  fundamentals: (symbol: string) => api.get(`/stocks/${symbol}/fundamentals`),
  indicators: (symbol: string, period?: string) =>
    api.get(`/stocks/${symbol}/indicators`, { params: { period } }),
  news: (symbol: string, limit?: number) =>
    api.get(`/stocks/${symbol}/news`, { params: { limit } }),
  announcements: (symbol: string, limit?: number) =>
    api.get(`/stocks/${symbol}/announcements`, { params: { limit } }),
  researchReports: (symbol: string, limit?: number) =>
    api.get(`/stocks/${symbol}/research-reports`, { params: { limit } }),
  snapshot: (symbol: string) => api.get(`/stocks/${symbol}/snapshot`),
}

export interface AnalysisStep {
  step_id: string
  label: string
  role: string
  character: string
  module?: string
  action?: string
  artifact_key?: string
  status: 'pending' | 'running' | 'done' | 'error'
  started_at?: string
  completed_at?: string
  detail?: string
}

export interface AnalysisRequest {
  symbol: string
  output_language?: string
  analysts?: string[]
  research_depth?: string
  llm_provider?: string
  thinking_agents?: boolean
  trade_date?: string
  checkpoint_enabled?: boolean
}

export interface AnalysisStatus {
  job_id: string
  symbol: string
  status: string
  phase: string
  progress: string
  result_summary: string
  error: string
  steps: AnalysisStep[]
  created_at: string
  output_files: string[]
}

// Analysis
export const analysisApi = {
  start: (data: AnalysisRequest) => api.post('/analysis/', data),
  status: (jobId: string) => api.get(`/analysis/${jobId}/status`),
  jobs: (params?: { symbol?: string; status?: string; limit?: number }) =>
    api.get('/analysis/jobs', { params }),
  files: (jobId: string) => api.get(`/analysis/${jobId}/files`),
  flow: (jobId: string) => api.get(`/analysis/${jobId}/flow`),
  feedback: {
    post: (jobId: string, data: { step_id: string; feedback_type: 'upvote' | 'downvote'; comment?: string }) =>
      api.post(`/analysis/${jobId}/feedback`, data),
    get: (jobId: string) => api.get(`/analysis/${jobId}/feedback`),
  },
  retry: (jobId: string) => api.post(`/analysis/${jobId}/retry`),
}

export interface RawSource {
  source_id: string
  source_kind: string
  origin: string
  title: string
  content_path: string
  content_sha256: string
  symbol: string
  symbols: string[]
  trade_date: string
  published_at: string
  captured_at: string
  tags: string[]
  metadata: Record<string, unknown>
  duplicate?: boolean
  markdown?: string
  content?: string
}

export interface RawSourceCreate {
  source_kind: string
  origin: string
  title: string
  markdown: string
  metadata: Record<string, unknown>
}

export interface DailyTradeEntry {
  symbol: string
  name?: string
  action: 'buy' | 'sell' | 'add' | 'reduce' | 'clear' | 'hold' | 'watch'
  quantity?: number | null
  price?: number | null
  commission?: number
  tax?: number
  other_fees?: number
  reason?: string
  linked_analysis_run_id?: string
  linked_source_ids?: string[]
}

export interface PositionOverride {
  symbol: string
  final_quantity: number
  final_avg_cost: number
  final_current_price?: number | null
  override_reason?: string
}

export const rawApi = {
  list: (params?: { source_kind?: string; symbol?: string; trade_date?: string; limit?: number; offset?: number }) =>
    api.get('/raw/sources', { params }),
  create: (data: RawSourceCreate) => api.post('/raw/sources', data),
  detail: (sourceId: string) => api.get(`/raw/sources/${encodeURIComponent(sourceId)}`),
  content: (sourceId: string) => api.get(`/raw/sources/${encodeURIComponent(sourceId)}/content`),
  updateMetadata: (sourceId: string, data: { tags?: string[]; metadata?: Record<string, unknown> }) =>
    api.post(`/raw/sources/${encodeURIComponent(sourceId)}/metadata`, data),
  update: (sourceId: string, data: { title: string; markdown: string; metadata?: Record<string, unknown> }) =>
    api.put(`/raw/sources/${encodeURIComponent(sourceId)}`, data),
  verify: (sourceId: string) => api.post(`/raw/sources/${encodeURIComponent(sourceId)}/verify`),
  collectHolding: (symbol: string, limit?: number) =>
    api.post(`/raw/collect/holding/${symbol}`, null, { params: { limit } }),
  collectPortfolio: (limit_per_symbol?: number) =>
    api.post('/raw/collect/portfolio', null, { params: { limit_per_symbol } }),
  getTradeLog: (date: string) => api.get('/raw/trade-log', { params: { date } }),
  saveTradeLog: (data: {
    trade_date: string
    entries: DailyTradeEntry[]
    position_overrides?: PositionOverride[]
    notes?: string
  }) => api.post('/raw/trade-log', data),
}

// Sectors
export interface DiscoverPhase {
  phase: string
  label: string
  status: string
  duration_ms: number
  message: string
}

export interface DiscoverStatus {
  job_id: string
  status: string
  progress_pct: number
  phase: string
  message: string
  error: string
  phases: DiscoverPhase[]
  result_summary: string
  created_at: string
  completed_at?: string
}

export interface ValidationData {
  dimension: string
  status: 'strong' | 'moderate' | 'weak' | 'missing'
  score: number
  evidence: string
  concerns: string[]
}

export interface ValidationResult {
  direction_name: string
  overall_status: string
  fund_validation: ValidationData
  policy_validation: ValidationData
  sentiment_validation: ValidationData
  score_after_validation: number
  rejection_reason: string
  watch_points: string[]
}

export interface SelectedDirection {
  name: string
  rank: number
  total_score: number
  fund_score: number
  policy_score: number
  sentiment_score: number
  chain_depth_score: number
  catalyst_score: number
  selection_reason: string
  comparison_notes: string
  eliminated_peers: string[]
}

export interface ChainSegment {
  segment_name: string
  position: string
  market_perception: string
  reality_assessment: string
  expectation_gap: number
  key_players: string[]
  price_trend: string
  capacity_utilization: string
  order_backlog_trend: string
  investment_logic: string
  time_horizon: string
}

export interface ChainAnalysis {
  direction_name: string
  segments: ChainSegment[]
  top_segment: string
  diffusion_path: string
  supporting_segments: string[]
}

export interface CatalystEvent {
  event_name: string
  expected_date: string | null
  time_category: 'past' | 'imminent' | 'expected' | 'long_term'
  market_priced_in: number
  impact_assessment: string
  data_to_watch: string
}

export interface CatalystTimeline {
  direction_name: string
  events: CatalystEvent[]
  next_key_event: string
  recommended_action: string
}

export interface RiskTrigger {
  condition: string
  metric_name: string
  threshold: string
  severity: string
}

export interface RiskAssessment {
  direction_name: string
  overall_risk_level: string
  market_risks: RiskTrigger[]
  policy_risks: RiskTrigger[]
  fundamental_risks: RiskTrigger[]
  invalidation_conditions: string[]
  alternative_directions: string[]
}

export interface DeepAnalysis {
  chain: ChainAnalysis | null
  catalyst: CatalystTimeline | null
  risk: RiskAssessment | null
}

export interface DirectionReport {
  id: number
  source_id: string
  date: string
  title: string
  summary: string
  tags: string[]
  content: string
  created_at: string
  sectors: SelectedDirection[]
  validation_results: ValidationResult[]
  deep_analysis: Record<string, DeepAnalysis>
  execution_log: Array<{
    agent_name: string
    phase: string
    status: string
    duration_ms: number
    message: string
  }>
  candidate_count: number
}

export const sectorsApi = {
  today: (date?: string, limit?: number) =>
    api.get('/sectors/today', { params: { ...(date ? { date } : {}), ...(limit ? { limit } : {}), _t: Date.now() } }),
  discover: (data?: { board_code?: string }) =>
    api.post('/sectors/discover', data || {}),
  discoverStatus: (jobId: string) =>
    api.get(`/sectors/discover/status/${jobId}`),
  analyze: (stock: string) =>
    api.post(`/sectors/${stock}/analyze`),
}

export interface ScheduledTask {
  id: string
  name: string
  description: string
  enabled: boolean
  cron: string
}

export interface LLMProviderInfo {
  id: string
  label: string
  region: string
  api_key_field: string
  api_key_env: string | null
  default_base_url: string
  default_quick_model: string
  default_deep_model: string
  requires_api_key: boolean
  supports_custom_model: boolean
}

export interface LLMProvidersResponse {
  providers: LLMProviderInfo[]
}

export interface LLMProviderSettings {
  quick_model: string
  deep_model: string
  api_key: string
}

export interface SettingsResponse {
  llm_provider_configs?: Record<string, LLMProviderSettings>
  [key: string]: unknown
}

// Settings
export const settingsApi = {
  get: () => api.get<SettingsResponse>('/settings'),
  update: (data: Record<string, unknown>) => api.patch('/settings', data),
  llmProviders: () => api.get<LLMProvidersResponse>('/settings/llm-providers'),
}

export const schedulerApi = {
  tasks: () => api.get('/settings/tasks'),
  updateTask: (taskId: string, data: { enabled?: boolean; cron?: string }) =>
    api.patch(`/settings/tasks/${taskId}`, data),
  runTask: (taskId: string) => api.post(`/settings/tasks/${taskId}/run`),
}

export const configApi = {
  analysts: () => api.get('/settings/analysts'),
}

// Wiki
export interface WikiPage {
  page_id: string
  page_type: string
  title: string
  slug: string
  content_path: string
  content_sha256: string
  symbol: string
  topic: string
  trade_date: string
  tags: string[]
  source_ids: string[]
  claim_ids: string[]
  status: string
  review_status: string
  revision: number
  created_at: string
  updated_at: string
  markdown?: string
  content?: string
  frontmatter?: Record<string, unknown>
}

export interface WikiIngestRun {
  run_id: string
  trigger_type: string
  source_id: string
  status: string
  mode: string
  started_at: string
  completed_at: string
}

export interface WikiUpdatePlan {
  source_ids: string[]
  title: string
  summary: string
  pages_to_create: WikiPage[]
  page_patches: Array<{ page_id: string; section_id: string; markdown: string; mode: string }>
  claims: Array<{ claim_id: string; statement: string; source_ids: string[] }>
  contradictions: Array<unknown>
  log_entry: string
  warnings: string[]
}

export const wikiApi = {
  pages: (params?: { page_type?: string; symbol?: string; topic?: string; trade_date?: string; q?: string; limit?: number; offset?: number }) =>
    api.get('/wiki/pages', { params }),
  detail: (pageId: string) => api.get(`/wiki/pages/${encodeURIComponent(pageId)}`),
  content: (pageId: string) => api.get(`/wiki/pages/${encodeURIComponent(pageId)}/content`),
  bySlug: (slug: string) => api.get(`/wiki/pages/by-slug/${encodeURIComponent(slug)}`),
  verify: (pageId: string) => api.post(`/wiki/pages/${encodeURIComponent(pageId)}/verify`),
  pendingSources: (params?: { limit?: number }) => api.get('/wiki/sources/pending', { params }),
  ingestSource: (sourceId: string, data: { force?: boolean }) =>
    api.post(`/wiki/ingest/source/${encodeURIComponent(sourceId)}`, data),
  ingestAnalysisRun: (runId: string, data: { force?: boolean }) =>
    api.post(`/wiki/ingest/analysis-run/${encodeURIComponent(runId)}`, data),
  ingestBatch: (data: { source_ids: string[] }) =>
    api.post('/wiki/ingest/batch', data),
  ingestRuns: (params?: { limit?: number }) => api.get('/wiki/ingest/runs', { params }),
  ingestRun: (runId: string) => api.get(`/wiki/ingest/runs/${encodeURIComponent(runId)}`),
  claims: (params?: { subject_type?: string; subject_id?: string; claim_type?: string; status?: string; limit?: number }) =>
    api.get('/wiki/claims', { params }),
  claim: (claimId: string) => api.get(`/wiki/claims/${encodeURIComponent(claimId)}`),
  rebuildIndex: () => api.post('/wiki/rebuild-index'),
  runLint: () => api.post('/wiki/lint'),
  latestLint: () => api.get('/wiki/lint/latest'),
}
