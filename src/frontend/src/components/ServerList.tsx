import { useState, useEffect } from 'react'
import type { McpServerConfig, AuthStatus } from '../types'
import * as api from '../api'

interface Props {
  onEdit: (name: string, config: McpServerConfig) => void
  onAdd: () => void
  onViewTools: (name: string) => void
  onToast: (message: string, type: 'success' | 'error' | 'info') => void
  refreshKey: number
}

export default function ServerList({ onEdit, onAdd, onViewTools, onToast, refreshKey }: Props) {
  const [servers, setServers] = useState<Record<string, McpServerConfig>>({})
  const [authStatuses, setAuthStatuses] = useState<Record<string, AuthStatus>>({})
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<Record<string, string>>({})

  useEffect(() => {
    loadServers()
  }, [refreshKey])

  async function loadServers() {
    try {
      const data = await api.listServers()
      setServers(data)
      const statuses: Record<string, AuthStatus> = {}
      for (const name of Object.keys(data)) {
        try {
          statuses[name] = await api.getAuthStatus(name)
        } catch {
          statuses[name] = { authenticated: false, auth_mode: null }
        }
      }
      setAuthStatuses(statuses)
    } catch (e) {
      onToast(`Failed to load servers: ${e}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  async function handleTest(name: string) {
    setActionLoading(prev => ({ ...prev, [name]: 'testing' }))
    try {
      const result = await api.testConnection(name)
      onToast(result.message, result.success ? 'success' : 'error')
    } catch (e) {
      onToast(`Test failed: ${e}`, 'error')
    } finally {
      setActionLoading(prev => { const n = { ...prev }; delete n[name]; return n })
    }
  }

  async function handleFetch(name: string) {
    const status = authStatuses[name]
    if (status && !status.authenticated && servers[name]?.auth) {
      if (servers[name].auth_mode === 'oauth' || servers[name].auth_mode === 'dcr') {
        try {
          await api.startAuth(name)
          onToast('Browser opened for authorization. Complete login and try again.', 'info')
          return
        } catch (e) {
          onToast(`Auth failed: ${e}`, 'error')
          return
        }
      }
      onToast('Server requires authentication. Check your .env token.', 'error')
      return
    }

    setActionLoading(prev => ({ ...prev, [name]: 'fetching' }))
    try {
      const result = await api.fetchTools(name)
      if (result.success) {
        onToast(result.message, 'success')
        onViewTools(name)
      } else {
        onToast(result.message, 'error')
      }
    } catch (e) {
      onToast(`Fetch failed: ${e}`, 'error')
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
        <h2 className="text-xl font-semibold text-gray-800">MCP Servers</h2>
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
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">URL</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Auth</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Enabled</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([name, config]) => {
                const status = authStatuses[name]
                const isAuth = status?.authenticated ?? false
                const action = actionLoading[name]

                return (
                  <tr key={name} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <span className={`inline-block w-2.5 h-2.5 rounded-full ${
                        !config.auth ? 'bg-gray-400' : isAuth ? 'bg-green-500' : 'bg-red-400'
                      }`} title={isAuth ? 'Authenticated' : 'Not authenticated'} />
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900">{name}</td>
                    <td className="px-4 py-3 text-gray-500 truncate max-w-xs" title={config.url}>{config.url}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                        {config.auth_mode || (config.auth ? 'sso' : 'none')}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs ${config.enabled ? 'text-green-600' : 'text-gray-400'}`}>
                        {config.enabled ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      <button
                        onClick={() => onEdit(name, config)}
                        className="text-xs px-2 py-1 text-blue-600 hover:bg-blue-50 rounded"
                      >Edit</button>
                      <button
                        onClick={() => handleTest(name)}
                        disabled={!!action}
                        className="text-xs px-2 py-1 text-amber-600 hover:bg-amber-50 rounded disabled:opacity-50"
                      >{action === 'testing' ? 'Testing...' : 'Test'}</button>
                      <button
                        onClick={() => handleFetch(name)}
                        disabled={!!action}
                        className="text-xs px-2 py-1 text-green-600 hover:bg-green-50 rounded disabled:opacity-50"
                      >{action === 'fetching' ? 'Fetching...' : 'Fetch Tools'}</button>
                      <button
                        onClick={() => handleDelete(name)}
                        className="text-xs px-2 py-1 text-red-500 hover:bg-red-50 rounded"
                      >Delete</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
