import type { McpServerConfig, AuthStatus, ToolInfo } from './types'

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

export async function getTools(name: string): Promise<{ server: string; tools: ToolInfo[]; count: number }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/tools`)
}

export async function getAuthStatus(name: string): Promise<AuthStatus> {
  return fetchJson(`/auth/status/${encodeURIComponent(name)}`)
}

export async function startAuth(name: string): Promise<{ auth_url: string; message: string }> {
  return fetchJson(`/auth/start/${encodeURIComponent(name)}`, { method: 'POST' })
}
