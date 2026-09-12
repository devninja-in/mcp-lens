import { useState, useEffect } from 'react'
import type { McpServerConfig, AuthStatus } from '../types'
import * as api from '../api'

interface Props {
  onEdit: (name: string, config: McpServerConfig) => void
  onAdd: () => void
  onViewTools: (name: string) => void
  onViewEval: (name: string) => void
  onToast: (message: string, type: 'success' | 'error' | 'info') => void
  onServersLoaded?: (servers: Record<string, McpServerConfig>) => void
  refreshKey: number
}

export default function ServerList({ onEdit, onAdd, onViewTools, onViewEval, onToast, onServersLoaded, refreshKey }: Props) {
  const [servers, setServers] = useState<Record<string, McpServerConfig>>({})
  const [authStatuses, setAuthStatuses] = useState<Record<string, AuthStatus>>({})
  const [evalScores, setEvalScores] = useState<Record<string, number | null>>({})
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<Record<string, string>>({})

  useEffect(() => {
    loadServers()
  }, [refreshKey])

  async function loadServers() {
    try {
      const data = await api.listServers()
      setServers(data)
      onServersLoaded?.(data)
      const statuses: Record<string, AuthStatus> = {}
      for (const name of Object.keys(data)) {
        try {
          statuses[name] = await api.getAuthStatus(name)
        } catch {
          statuses[name] = { authenticated: false, auth_mode: null }
        }
      }
      setAuthStatuses(statuses)
      const scores: Record<string, number | null> = {}
      await Promise.all(
        Object.keys(data).map(async (name) => {
          try {
            const result = await api.evaluateTools(name)
            scores[name] = result.server_summary.overall_score
          } catch {
            scores[name] = null
          }
        })
      )
      setEvalScores(scores)
    } catch (e) {
      onToast(`Failed to load servers: ${e}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  async function handleReauth(name: string) {
    const authMode = servers[name]?.auth_mode
    if (authMode === 'oauth' || authMode === 'dcr') {
      onToast('Token expired. Opening browser for re-authentication...', 'info')
      try {
        await api.startAuth(name)
        onToast('Browser opened for authorization. Complete login and try again.', 'info')
      } catch (authErr) {
        onToast(`Re-auth failed: ${authErr}`, 'error')
      }
    } else if (authMode === 'bearer_token' || !authMode) {
      onToast('Bearer token expired or invalid. Edit the server to update your token.', 'error')
    } else if (authMode === 'api_key') {
      onToast('API key is invalid. Edit the server to update your key.', 'error')
    } else {
      onToast('Authentication failed. Edit the server to reconfigure credentials.', 'error')
    }
  }

  async function handleConnect(name: string) {
    const status = authStatuses[name]
    if (status && !status.authenticated && servers[name]?.auth) {
      const authMode = servers[name].auth_mode
      if (authMode === 'oauth' || authMode === 'dcr') {
        try {
          await api.startAuth(name)
          onToast('Browser opened for authorization. Complete login and try again.', 'info')
          return
        } catch (e) {
          onToast(`Auth failed: ${e}`, 'error')
          return
        }
      }
      if (authMode === 'bearer_token' || !authMode) {
        onToast('Server requires a Bearer token. Edit the server to configure it.', 'error')
      } else if (authMode === 'api_key') {
        onToast('Server requires an API key. Edit the server to configure it.', 'error')
      } else {
        onToast('Server requires authentication. Edit the server to configure it.', 'error')
      }
      return
    }

    setActionLoading(prev => ({ ...prev, [name]: 'connecting' }))
    try {
      const testResult = await api.testConnection(name) as any
      if (!testResult.success) {
        if (testResult.reauth) {
          await handleReauth(name)
          return
        }
        onToast(`Connection failed: ${testResult.message}`, 'error')
        return
      }
      const result = await api.fetchTools(name) as any
      if (result.success) {
        onToast(`Connected! Loaded ${result.count} tools.`, 'success')
        onViewTools(name)
      } else {
        if (result.reauth) {
          await handleReauth(name)
        } else {
          onToast(result.message, 'error')
        }
      }
    } catch (e) {
      onToast(`Connect failed: ${e}`, 'error')
    } finally {
      setActionLoading(prev => { const n = { ...prev }; delete n[name]; return n })
    }
  }

  async function handleDelete(name: string) {
    if (!confirm(`Delete server "${name}"?`)) return
    try {
      await api.deleteServer(name)
      onToast(`Server '${name}' deleted`, 'success')
      loadServers()
    } catch (e) {
      onToast(`Delete failed: ${e}`, 'error')
    }
  }

  if (loading) return <div className="text-center py-12 text-gray-500">Loading servers...</div>

  const entries = Object.entries(servers)

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-semibold text-gray-800">Servers</h2>
        <button
          onClick={onAdd}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
        >
          + Add Server
        </button>
      </div>

      {entries.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          No servers configured. Add one to get started.
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map(([name, config]) => {
            const status = authStatuses[name]
            const isAuth = status?.authenticated ?? false
            const action = actionLoading[name]
            const score = evalScores[name]

            return (
              <div key={name} className="bg-white border border-gray-200 rounded-lg px-5 py-4 hover:shadow-sm transition-shadow">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                      !config.auth ? 'bg-gray-400' : isAuth ? 'bg-green-500' : 'bg-red-400'
                    }`} title={isAuth ? 'Authenticated' : 'Not authenticated'} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-gray-900">{name}</span>
                        {!config.enabled && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-400 uppercase tracking-wide">disabled</span>
                        )}
                      </div>
                      <p className="text-xs text-gray-400 truncate">{config.url}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 shrink-0">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                      {config.auth_mode || (config.auth ? 'bearer_token' : 'none')}
                    </span>

                    {score != null ? (
                      <button
                        onClick={() => onViewEval(name)}
                        className={`text-sm px-2.5 py-1 rounded-full font-bold cursor-pointer hover:opacity-80 transition-opacity ${
                          score >= 80 ? 'bg-green-100 text-green-800' :
                          score >= 60 ? 'bg-yellow-100 text-yellow-800' :
                          'bg-red-100 text-red-800'
                        }`}
                        title="View evaluation details"
                      >
                        {score.toFixed(0)}
                      </button>
                    ) : (
                      <span className="text-sm text-gray-300 w-8 text-center">—</span>
                    )}

                    <div className="flex items-center gap-1 border-l border-gray-100 pl-3">
                      <button
                        onClick={() => handleConnect(name)}
                        disabled={!!action}
                        className="text-xs px-2.5 py-1.5 text-green-700 bg-green-50 hover:bg-green-100 rounded font-medium disabled:opacity-50 transition-colors"
                      >{action === 'connecting' ? 'Connecting...' : 'Connect'}</button>
                      <button
                        onClick={() => onViewTools(name)}
                        className="text-xs px-2.5 py-1.5 text-blue-700 bg-blue-50 hover:bg-blue-100 rounded font-medium transition-colors"
                      >Tools</button>
                      <button
                        onClick={() => onEdit(name, config)}
                        className="text-xs px-2.5 py-1.5 text-gray-600 hover:bg-gray-100 rounded transition-colors"
                      >Edit</button>
                      <button
                        onClick={() => handleDelete(name)}
                        className="text-xs px-2.5 py-1.5 text-red-500 hover:bg-red-50 rounded transition-colors"
                      >Delete</button>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
