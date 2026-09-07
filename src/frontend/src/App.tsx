import { useState, useCallback } from 'react'
import type { McpServerConfig } from './types'
import ServerList from './components/ServerList'
import ServerForm from './components/ServerForm'
import ToolsViewer from './components/ToolsViewer'
import Toast from './components/Toast'
import * as api from './api'

type ToastState = { message: string; type: 'success' | 'error' | 'info' } | null

export default function App() {
  const [toast, setToast] = useState<ToastState>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [editingServer, setEditingServer] = useState<{ name: string; config: McpServerConfig } | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [viewingTools, setViewingTools] = useState<string | null>(null)

  const handleToast = useCallback((message: string, type: 'success' | 'error' | 'info') => {
    setToast({ message, type })
  }, [])

  async function handleSave(name: string, config: McpServerConfig) {
    try {
      if (editingServer) {
        await api.updateServer(name, config)
        handleToast(`Server '${name}' updated`, 'success')
      } else {
        await api.createServer(name, config)
        handleToast(`Server '${name}' created`, 'success')
      }
      setShowForm(false)
      setEditingServer(null)
      setRefreshKey(k => k + 1)
    } catch (e) {
      handleToast(`Save failed: ${e}`, 'error')
    }
  }

  if (viewingTools) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <header className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">MCP Tools Fetch</h1>
          <p className="text-sm text-gray-500 mt-1">Manage MCP server configurations and fetch available tools</p>
        </header>
        <ToolsViewer
          serverName={viewingTools}
          onBack={() => setViewingTools(null)}
          onToast={handleToast}
        />
        {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">MCP Tools Fetch</h1>
        <p className="text-sm text-gray-500 mt-1">Manage MCP server configurations and fetch available tools</p>
      </header>

      <ServerList
        onEdit={(name, config) => { setEditingServer({ name, config }); setShowForm(true) }}
        onAdd={() => { setEditingServer(null); setShowForm(true) }}
        onViewTools={(name) => setViewingTools(name)}
        onToast={handleToast}
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
