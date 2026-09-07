import { useState, useCallback } from 'react'
import type { McpServerConfig } from './types'
import ServerList from './components/ServerList'
import Toast from './components/Toast'

type ToastState = { message: string; type: 'success' | 'error' | 'info' } | null

export default function App() {
  const [toast, setToast] = useState<ToastState>(null)
  const [refreshKey, _setRefreshKey] = useState(0)
  const [_editingServer, setEditingServer] = useState<{ name: string; config: McpServerConfig } | null>(null)
  const [_showForm, setShowForm] = useState(false)
  const [_viewingTools, setViewingTools] = useState<string | null>(null)

  const handleToast = useCallback((message: string, type: 'success' | 'error' | 'info') => {
    setToast({ message, type })
  }, [])

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

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  )
}
