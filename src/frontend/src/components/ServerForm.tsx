import { useState, useEffect } from 'react'
import type { McpServerConfig, OAuthConfig, ApiKeyConfig } from '../types'
import { discoverOAuthEndpoints } from '../api'

interface Props {
  name?: string
  config?: McpServerConfig
  onSave: (name: string, config: McpServerConfig, secretValue?: string) => void
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
  const [apiKeyConfig, setApiKeyConfig] = useState<ApiKeyConfig>(editConfig?.api_key_config || { location: 'header', name: 'X-API-Key' })
  const [secretValue, setSecretValue] = useState('')
  const [discovering, setDiscovering] = useState(false)
  const [discoveryError, setDiscoveryError] = useState<string | null>(null)
  const [discoverySuccess, setDiscoverySuccess] = useState(false)
  const isEdit = !!editName

  useEffect(() => {
    if (editConfig?.oauth) setOauth(editConfig.oauth)
  }, [editConfig])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const finalConfig: McpServerConfig = {
      ...config,
      oauth: (config.auth_mode === 'oauth' || config.auth_mode === 'dcr') ? oauth : undefined,
      api_key_config: config.auth_mode === 'api_key' ? apiKeyConfig : undefined,
    }
    const secret = config.auth && (config.auth_mode === 'bearer_token' || config.auth_mode === 'api_key') && secretValue.trim()
      ? secretValue.trim() : undefined
    onSave(name, finalConfig, secret)
  }

  function updateConfig<K extends keyof McpServerConfig>(key: K, value: McpServerConfig[K]) {
    setConfig(prev => ({ ...prev, [key]: value }))
  }

  function updateOauth<K extends keyof OAuthConfig>(key: K, value: OAuthConfig[K]) {
    setOauth(prev => ({ ...prev, [key]: value }))
  }

  async function handleDiscover() {
    const targetUrl = config.url?.trim()
    if (!targetUrl) {
      setDiscoveryError('Enter a server URL first')
      return
    }
    setDiscovering(true)
    setDiscoveryError(null)
    setDiscoverySuccess(false)
    try {
      const result = await discoverOAuthEndpoints(targetUrl, config.ssl_verify)
      setOauth(prev => ({
        ...prev,
        authorization_endpoint: result.authorization_endpoint || prev.authorization_endpoint,
        token_endpoint: result.token_endpoint || prev.token_endpoint,
        registration_endpoint: result.registration_endpoint || prev.registration_endpoint,
        scopes: result.scopes_supported?.length ? result.scopes_supported : prev.scopes,
      }))
      setDiscoverySuccess(true)
    } catch (err: any) {
      setDiscoveryError(err.message || 'Discovery failed')
    } finally {
      setDiscovering(false)
    }
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
            <textarea
              value={config.description}
              onChange={e => updateConfig('description', e.target.value)}
              rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="e.g. Atlassian MCP server providing Confluence and Jira tools for content management and issue tracking"
            />
            <p className="text-xs text-gray-400 mt-1">Used as context during LLM evaluation to improve tool selection accuracy.</p>
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
                value={config.auth_mode || 'bearer_token'}
                onChange={e => { updateConfig('auth_mode', e.target.value); setDiscoveryError(null); setDiscoverySuccess(false) }}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              >
                <option value="bearer_token">Bearer Token</option>
                <option value="api_key">API Key</option>
                <option value="oauth">OAuth (Authorization Code)</option>
                <option value="dcr">DCR (Dynamic Client Registration)</option>
              </select>
            </div>
          )}

          {config.auth && config.auth_mode === 'bearer_token' && (
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
              <h4 className="text-sm font-medium text-gray-700">Bearer Token</h4>
              <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
                Also checked from env variable: <code className="font-mono bg-gray-200 px-1 rounded">
                  MCP_{name.toUpperCase().replace(/-/g, '_')}_TOKEN
                </code>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Token</label>
                <textarea
                  value={secretValue}
                  onChange={e => setSecretValue(e.target.value)}
                  rows={3}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Paste your bearer token here..."
                />
                <p className="text-xs text-gray-400 mt-1">Token will be saved when you click Save.</p>
              </div>
            </div>
          )}

          {config.auth && config.auth_mode === 'api_key' && (
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
              <h4 className="text-sm font-medium text-gray-700">API Key Configuration</h4>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Send In</label>
                  <select
                    value={apiKeyConfig.location}
                    onChange={e => setApiKeyConfig(prev => ({ ...prev, location: e.target.value }))}
                    className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                  >
                    <option value="header">Header (Recommended)</option>
                    <option value="query">Query Parameter</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">
                    {apiKeyConfig.location === 'header' ? 'Header Name' : 'Query Param Name'}
                  </label>
                  <input
                    value={apiKeyConfig.name}
                    onChange={e => setApiKeyConfig(prev => ({ ...prev, name: e.target.value }))}
                    className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                    placeholder={apiKeyConfig.location === 'header' ? 'X-API-Key' : 'api_key'}
                  />
                </div>
              </div>
              {apiKeyConfig.location === 'query' && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-700">
                  Warning: Query parameter auth exposes the API key in URLs and server logs. Use header-based auth unless the target API requires query parameters.
                </div>
              )}
              <div>
                <label className="block text-xs text-gray-500 mb-1">API Key Value</label>
                <input
                  type="password"
                  value={secretValue}
                  onChange={e => setSecretValue(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Enter your API key..."
                />
                <p className="text-xs text-gray-400 mt-1">Key will be saved when you click Save.</p>
              </div>
            </div>
          )}

          {config.auth && (config.auth_mode === 'oauth' || config.auth_mode === 'dcr') && (
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
              <h4 className="text-sm font-medium text-gray-700">OAuth Configuration</h4>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleDiscover}
                  disabled={discovering || !config.url?.trim()}
                  className="px-3 py-1.5 text-xs bg-indigo-50 text-indigo-700 rounded-lg hover:bg-indigo-100 border border-indigo-200 font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                >
                  {discovering ? (
                    <>
                      <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      Discovering...
                    </>
                  ) : (
                    'Auto-Discover Endpoints'
                  )}
                </button>
                <span className="text-xs text-gray-400">from .well-known metadata</span>
              </div>

              {discoveryError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-2.5 text-xs text-red-700">
                  Discovery failed: {discoveryError}. You can enter endpoints manually below.
                </div>
              )}

              {discoverySuccess && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-2.5 text-xs text-green-700">
                  Endpoints discovered and auto-filled. Review and adjust as needed.
                </div>
              )}

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
