export interface OAuthConfig {
  grant_type?: string
  registration_endpoint?: string
  authorization_endpoint?: string
  token_endpoint?: string
  client_id?: string
  client_secret_env?: string
  scopes?: string[]
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
