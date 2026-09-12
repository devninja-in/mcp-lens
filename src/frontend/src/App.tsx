import { useState, useCallback, useEffect } from 'react'
import type { McpServerConfig } from './types'
import ServerList from './components/ServerList'
import ServerForm from './components/ServerForm'
import ToolsViewer from './components/ToolsViewer'
import AboutPage from './components/AboutPage'
import Toast from './components/Toast'
import * as api from './api'

type ToastState = { message: string; type: 'success' | 'error' | 'info' } | null

export default function App() {
  const [toast, setToast] = useState<ToastState>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [editingServer, setEditingServer] = useState<{ name: string; config: McpServerConfig } | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [viewingTools, setViewingTools] = useState<string | null>(null)
  const [initialTab, setInitialTab] = useState<'tools' | 'evaluate'>('tools')
  const [serversCache, setServersCache] = useState<Record<string, McpServerConfig>>({})
  const [page, setPage] = useState<'servers' | 'about'>('servers')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authServer = params.get('auth_success')
    if (authServer) {
      window.history.replaceState({}, '', window.location.pathname)
      handleToast(`Authenticated! Connecting to ${authServer}...`, 'success')
      setRefreshKey(k => k + 1)
      api.testConnection(authServer).then(testResult => {
        if (!testResult.success) {
          handleToast(`Connection failed: ${testResult.message}`, 'error')
          return
        }
        return api.fetchTools(authServer)
      }).then(result => {
        if (result && result.success) {
          handleToast(`Connected! Loaded ${result.count} tools.`, 'success')
          setViewingTools(authServer)
        } else if (result) {
          handleToast(result.message, 'error')
        }
      }).catch(e => handleToast(`Connect failed: ${e}`, 'error'))
    }
  }, [])

  const handleToast = useCallback((message: string, type: 'success' | 'error' | 'info') => {
    setToast({ message, type })
  }, [])

  function handleViewTools(name: string) {
    setInitialTab('tools')
    setViewingTools(name)
  }

  function handleViewEval(name: string) {
    setInitialTab('evaluate')
    setViewingTools(name)
  }

  async function handleSave(name: string, config: McpServerConfig, secretValue?: string) {
    try {
      if (editingServer) {
        await api.updateServer(name, config)
        handleToast(`Server '${name}' updated`, 'success')
      } else {
        await api.createServer(name, config)
        handleToast(`Server '${name}' created`, 'success')
      }
      if (secretValue && config.auth_mode === 'bearer_token') {
        await api.saveBearerToken(name, secretValue)
        handleToast('Bearer token saved', 'success')
      } else if (secretValue && config.auth_mode === 'api_key') {
        await api.saveApiKey(name, secretValue)
        handleToast('API key saved', 'success')
      }
      setShowForm(false)
      setEditingServer(null)
      setRefreshKey(k => k + 1)
    } catch (e) {
      handleToast(`Save failed: ${e}`, 'error')
    }
  }

  const activePage = viewingTools ? 'servers' : page

  const nav = (
    <header className="mb-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">MCP Lens</h1>
          <p className="text-sm text-gray-500 mt-1">Inspect, evaluate, and manage your MCP server tools</p>
        </div>
        <nav className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
          <button
            onClick={() => { setPage('servers'); setViewingTools(null) }}
            className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              activePage === 'servers'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Servers
          </button>
          <button
            onClick={() => { setPage('about'); setViewingTools(null) }}
            className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              activePage === 'about'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            About
          </button>
        </nav>
      </div>
    </header>
  )

  if (viewingTools) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        {nav}
        <ToolsViewer
          serverName={viewingTools}
          authMode={serversCache[viewingTools]?.auth_mode}
          initialTab={initialTab}
          onBack={() => setViewingTools(null)}
          onToast={handleToast}
        />
        {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      </div>
    )
  }

  if (page === 'about') {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        {nav}
        <AboutPage />
        {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {nav}

      <ServerList
        onEdit={(name, config) => { setEditingServer({ name, config }); setShowForm(true) }}
        onAdd={() => { setEditingServer(null); setShowForm(true) }}
        onViewTools={handleViewTools}
        onViewEval={handleViewEval}
        onToast={handleToast}
        onServersLoaded={(s) => setServersCache(s)}
        refreshKey={refreshKey}
      />

      {showForm && (
        <ServerForm
          name={editingServer?.name}
          config={editingServer?.config}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditingServer(null) }}
        />
      )}

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  )
}
