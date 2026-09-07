import { useState, useEffect } from 'react'
import type { McpServerConfig, OAuthConfig } from '../types'

interface Props {
  name?: string
  config?: McpServerConfig
  onSave: (name: string, config: McpServerConfig) => void
  onCancel: () => void
}

const DEFAULT_CONFIG: McpServerConfig = {
  enabled: true,
  url: '',
  transport: 'streamable_http',
  ssl_verify: true,
  auth: false,
  description: '',
  auth_mode: null,
  oauth: null,
  timeout: 30,
}

export default function ServerForm({ name: editName, config: editConfig, onSave, onCancel }: Props) {
  const [name, setName] = useState(editName || '')
  const [config, setConfig] = useState<McpServerConfig>(editConfig || DEFAULT_CONFIG)
  const [oauth, setOauth] = useState<OAuthConfig>(editConfig?.oauth || {})
  const isEdit = !!editName

  useEffect(() => {
    if (editConfig?.oauth) setOauth(editConfig.oauth)
  }, [editConfig])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const finalConfig: McpServerConfig = {
      ...config,
      oauth: (config.auth_mode === 'oauth' || config.auth_mode === 'dcr') ? oauth : undefined,
    }
    onSave(name, finalConfig)
  }

  function updateConfig<K extends keyof McpServerConfig>(key: K, value: McpServerConfig[K]) {
    setConfig(prev => ({ ...prev, [key]: value }))
  }

  function updateOauth<K extends keyof OAuthConfig>(key: K, value: OAuthConfig[K]) {
    setOauth(prev => ({ ...prev, [key]: value }))
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <h3 className="text-lg font-semibold text-gray-900">
            {isEdit ? `Edit: ${editName}` : 'Add MCP Server'}
          </h3>

          {!isEdit && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Server Name</label>
              <input
                required
                value={name}
                onChange={e => setName(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="my-mcp-server"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
            <input
              required
              value={config.url}
              onChange={e => updateConfig('url', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="https://example.com/mcp"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <input
              value={config.description}
              onChange={e => updateConfig('description', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Transport</label>
              <select
                value={config.transport}
                onChange={e => updateConfig('transport', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              >
                <option value="streamable_http">Streamable HTTP</option>
                <option value="sse">SSE</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (s)</label>
              <input
                type="number"
                value={config.timeout}
                onChange={e => updateConfig('timeout', parseInt(e.target.value) || 30)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={config.enabled}
                onChange={e => updateConfig('enabled', e.target.checked)}
                className="rounded"
              /> Enabled
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={config.ssl_verify}
                onChange={e => updateConfig('ssl_verify', e.target.checked)}
                className="rounded"
              /> SSL Verify
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={config.auth}
                onChange={e => updateConfig('auth', e.target.checked)}
                className="rounded"
              /> Auth Required
            </label>
          </div>

          {config.auth && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Auth Mode</label>
              <select
                value={config.auth_mode || 'sso'}
                onChange={e => updateConfig('auth_mode', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              >
                <option value="sso">SSO (JWT from .env)</option>
                <option value="oauth">OAuth (Authorization Code)</option>
                <option value="dcr">DCR (Dynamic Client Registration)</option>
              </select>
            </div>
          )}

          {config.auth && config.auth_mode === 'sso' && (
            <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
              Token will be read from env variable: <code className="font-mono bg-gray-200 px-1 rounded">
                MCP_{name.toUpperCase().replace(/-/g, '_')}_TOKEN
              </code>
            </div>
          )}

          {config.auth && (config.auth_mode === 'oauth' || config.auth_mode === 'dcr') && (
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
              <h4 className="text-sm font-medium text-gray-700">OAuth Configuration</h4>

              {config.auth_mode === 'dcr' && (
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Registration Endpoint</label>
                  <input
                    value={oauth.registration_endpoint || ''}
                    onChange={e => updateOauth('registration_endpoint', e.target.value)}
                    className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                  />
                </div>
              )}

              {config.auth_mode === 'oauth' && (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Client ID</label>
                    <input
                      value={oauth.client_id || ''}
                      onChange={e => updateOauth('client_id', e.target.value)}
                      className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Client Secret Env Variable</label>
                    <input
                      value={oauth.client_secret_env || ''}
                      onChange={e => updateOauth('client_secret_env', e.target.value)}
                      className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                      placeholder="MCP_MY_SERVER_CLIENT_SECRET"
                    />
                  </div>
                </>
              )}

              <div>
                <label className="block text-xs text-gray-500 mb-1">Authorization Endpoint</label>
                <input
                  value={oauth.authorization_endpoint || ''}
                  onChange={e => updateOauth('authorization_endpoint', e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Token Endpoint</label>
                <input
                  value={oauth.token_endpoint || ''}
                  onChange={e => updateOauth('token_endpoint', e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Scopes (comma-separated)</label>
                <input
                  value={(oauth.scopes || []).join(', ')}
                  onChange={e => updateOauth('scopes', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                  placeholder="openid, profile, email"
                />
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
            >Cancel</button>
            <button
              type="submit"
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
            >Save</button>
          </div>
        </form>
      </div>
    </div>
  )
}
