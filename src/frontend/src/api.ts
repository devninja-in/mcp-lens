import type { McpServerConfig, AuthStatus, ToolInfo, EvaluationResult, FullEvalReport, FullLayerResult } from './types'

const BASE = '/api'

async function fetchJson<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export async function listServers(): Promise<Record<string, McpServerConfig>> {
  const data = await fetchJson<{ servers: Record<string, McpServerConfig> }>('/servers')
  return data.servers
}

export async function getServer(name: string): Promise<{ name: string; config: McpServerConfig }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}`)
}

export async function createServer(name: string, config: McpServerConfig): Promise<void> {
  await fetchJson(`/servers?name=${encodeURIComponent(name)}`, {
    method: 'POST',
    body: JSON.stringify(config),
  })
}

export async function updateServer(name: string, config: McpServerConfig): Promise<void> {
  await fetchJson(`/servers/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify(config),
  })
}

export async function deleteServer(name: string): Promise<void> {
  await fetchJson(`/servers/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export async function testConnection(name: string): Promise<{ success: boolean; message: string; server_info?: Record<string, unknown> }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/test`, { method: 'POST' })
}

export async function fetchTools(name: string): Promise<{ success: boolean; message: string; tools: ToolInfo[]; count: number }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/fetch-tools`, { method: 'POST' })
}

export async function getTools(name: string): Promise<{ server: string; tools: ToolInfo[]; count: number; source?: string }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/tools`)
}

export async function getAuthStatus(name: string): Promise<AuthStatus> {
  return fetchJson(`/auth/status/${encodeURIComponent(name)}`)
}

export async function startAuth(name: string): Promise<{ auth_url: string; message: string }> {
  return fetchJson(`/auth/start/${encodeURIComponent(name)}`, { method: 'POST' })
}

export async function saveBearerToken(name: string, token: string): Promise<{ success: boolean; message: string }> {
  return fetchJson(`/auth/bearer-token/${encodeURIComponent(name)}`, {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

export async function saveApiKey(name: string, key: string): Promise<{ success: boolean; message: string }> {
  return fetchJson(`/auth/api-key/${encodeURIComponent(name)}`, {
    method: 'POST',
    body: JSON.stringify({ key }),
  })
}

export interface DiscoveryResult {
  issuer?: string
  authorization_endpoint?: string
  token_endpoint?: string
  registration_endpoint?: string
  scopes_supported?: string[]
  grant_types_supported?: string[]
  response_types_supported?: string[]
  discovery_url?: string
}

export async function evaluateTools(name: string): Promise<EvaluationResult> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/evaluate`)
}

export async function getEvalReport(name: string): Promise<FullEvalReport | null> {
  try {
    return await fetchJson(`/servers/${encodeURIComponent(name)}/evaluate/report`)
  } catch {
    return null
  }
}

export async function evaluateToolsFull(name: string): Promise<FullEvalReport> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/evaluate/full`)
}

export interface LlmEvalResult {
  layer?: FullLayerResult
  overall_score?: number
  gate_passed?: boolean
  error?: string
  metadata: {
    llm_provider: string
    llm_model: string
    llm_error?: string
    ground_truth_loaded?: boolean
  }
  per_llm?: Record<string, {
    layer?: FullLayerResult
    error?: string
    metadata: { llm_provider: string; llm_model: string; llm_error?: string }
  }>
}

export async function evaluateLlm(name: string, llms?: string[]): Promise<LlmEvalResult> {
  const params = llms?.length ? `?llms=${llms.join(',')}` : ''
  return fetchJson(`/servers/${encodeURIComponent(name)}/evaluate/llm${params}`)
}

export interface LlmConfigInfo {
  provider: string
  model: string
  has_credentials: boolean
  source?: string
}

export async function getLlmConfigs(): Promise<{ configs: Record<string, LlmConfigInfo>; default: string | null }> {
  return fetchJson('/llm-configs')
}

export interface GroundTruthData {
  server_name: string
  test_cases: Array<{
    expected_tool_selection: string[]
    prompts: string[]
    expected_args?: Record<string, unknown>
  }>
  test_case_count: number
  prompt_count: number
}

export async function getGroundTruth(name: string): Promise<GroundTruthData | null> {
  try {
    return await fetchJson(`/servers/${encodeURIComponent(name)}/ground-truth`)
  } catch {
    return null
  }
}

export async function uploadGroundTruth(name: string, file: File): Promise<{ success: boolean; test_case_count: number; prompt_count: number; warnings: string[] }> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${BASE}/servers/${encodeURIComponent(name)}/ground-truth`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export async function deleteGroundTruth(name: string): Promise<{ success: boolean }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/ground-truth`, { method: 'DELETE' })
}

export function downloadGroundTruthTemplate(name: string): void {
  window.open(`${BASE}/servers/${encodeURIComponent(name)}/ground-truth/template`, '_blank')
}

export async function markFalsePositive(
  name: string,
  checkKey: string,
  justification: string | null,
): Promise<{ success: boolean; false_positives: Record<string, string> }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/evaluate/false-positive`, {
    method: 'POST',
    body: JSON.stringify({ check_key: checkKey, justification }),
  })
}

export async function discoverOAuthEndpoints(url: string, sslVerify: boolean = true): Promise<DiscoveryResult> {
  return fetchJson('/auth/discover', {
    method: 'POST',
    body: JSON.stringify({ url, ssl_verify: sslVerify }),
  })
}

export async function uploadTools(name: string, file: File): Promise<{ success: boolean; message: string; tools: ToolInfo[]; count: number; warnings: string[] }> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${BASE}/servers/${encodeURIComponent(name)}/tools/upload`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export function downloadToolsTemplate(name: string): void {
  window.open(`${BASE}/servers/${encodeURIComponent(name)}/tools/template`, '_blank')
}

export async function deleteUploadedTools(name: string): Promise<{ success: boolean }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/tools/uploaded`, { method: 'DELETE' })
}

// --- Rules API ---

export interface RuleParamSchema {
  type: string
  default: unknown
  description: string
}

export interface RuleInfo {
  rule_id: string
  layer: string
  description: string
  default_severity: string
  default_enabled: boolean
  params_schema: Record<string, RuleParamSchema>
  enabled: boolean
  severity_override: string | null
  params: Record<string, unknown>
}

export async function getRules(): Promise<{ rules: RuleInfo[]; total: number }> {
  return fetchJson('/rules')
}

export async function updateRule(
  ruleId: string,
  update: { enabled?: boolean; severity_override?: string | null; params?: Record<string, unknown> },
): Promise<{ success: boolean }> {
  return fetchJson(`/rules/${encodeURIComponent(ruleId)}`, {
    method: 'PUT',
    body: JSON.stringify(update),
  })
}

export async function resetRules(): Promise<{ success: boolean; reset_count: number }> {
  return fetchJson('/rules/reset', { method: 'POST' })
}

export async function exportRules(): Promise<{ version: string; exported_at: string; rules: unknown[] }> {
  return fetchJson('/rules/export')
}

export async function importRules(data: { version: string; rules: unknown[] }): Promise<{ success: boolean; imported_count: number; warnings: string[] }> {
  return fetchJson('/rules/import', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
