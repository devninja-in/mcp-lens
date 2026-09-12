export interface OAuthConfig {
  grant_type?: string
  registration_endpoint?: string
  authorization_endpoint?: string
  token_endpoint?: string
  client_id?: string
  client_secret_env?: string
  scopes?: string[]
}

export interface ApiKeyConfig {
  location: string
  name: string
}

export interface McpServerConfig {
  enabled: boolean
  url: string
  transport: string
  ssl_verify: boolean
  auth: boolean
  description: string
  auth_mode?: string | null
  oauth?: OAuthConfig | null
  api_key_config?: ApiKeyConfig | null
  timeout: number
}

export interface ToolInfo {
  name: string
  description?: string
  inputSchema?: Record<string, unknown>
}

export interface AuthStatus {
  authenticated: boolean
  auth_mode: string | null
}

export interface ApiResponse {
  success: boolean
  message: string
  data?: Record<string, unknown>
}

export interface DimensionScore {
  score: number
  checks: Record<string, boolean>
}

export interface ToolEvaluation {
  name: string
  overall_score: number
  dimensions: Record<string, DimensionScore>
}

export interface ScoreDistribution {
  green: number
  yellow: number
  red: number
}

export interface ServerSummary {
  overall_score: number
  tool_count: number
  dimension_averages: Record<string, number>
  score_distribution: ScoreDistribution
}

export interface EvaluationResult {
  server_summary: ServerSummary
  tools: ToolEvaluation[]
}

export interface FullCheckResult {
  check_id: string
  status: 'pass' | 'fail' | 'warn' | 'skip'
  message: string
  severity: string
  tool_name: string
  details?: {
    location?: string
    current_value?: unknown
    suggestion?: string
    suggested_description?: string
    scenario_source?: string
    [key: string]: unknown
  }
}

export interface FullToolResult {
  tool_name: string
  score: number
  passed: boolean
  checks: FullCheckResult[]
  summary: { pass: number; fail: number; warn: number; skip: number }
}

export interface FullLayerResult {
  layer: string
  score: number
  tool_count: number
  tools: FullToolResult[]
  catalog_checks: FullCheckResult[]
}

export interface FullEvalReport {
  timestamp: string
  server_name: string
  overall_score: number
  gate_passed: boolean
  layers: Record<string, FullLayerResult>
  metadata?: {
    llm_configured?: boolean
    llm_provider?: string
    llm_model?: string
    llm_error?: string
    [key: string]: unknown
  }
}
