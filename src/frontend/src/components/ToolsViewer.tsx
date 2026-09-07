import { useState, useEffect } from 'react'
import type { ToolInfo } from '../types'
import * as api from '../api'

interface Props {
  serverName: string
  onBack: () => void
  onToast: (message: string, type: 'success' | 'error' | 'info') => void
}

export default function ToolsViewer({ serverName, onBack, onToast }: Props) {
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => { loadTools() }, [serverName])

  async function loadTools() {
    try {
      const data = await api.getTools(serverName)
      setTools(data.tools)
    } catch {
      setTools([])
    } finally {
      setLoading(false)
    }
  }

  async function handleRefetch() {
    setLoading(true)
    try {
      const result = await api.fetchTools(serverName)
      if (result.success) {
        setTools(result.tools)
        onToast(result.message, 'success')
      } else {
        onToast(result.message, 'error')
      }
    } catch (e) {
      onToast(`Fetch failed: ${e}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  function toggleExpand(name: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

  if (loading) return <div className="text-center py-12 text-gray-500">Loading tools...</div>

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="text-sm text-gray-500 hover:text-gray-700"
          >&larr; Back</button>
          <h2 className="text-xl font-semibold text-gray-800">
            Tools: {serverName}
            <span className="text-sm font-normal text-gray-500 ml-2">({tools.length} tools)</span>
          </h2>
        </div>
        <button
          onClick={handleRefetch}
          disabled={loading}
          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium disabled:opacity-50"
        >Re-fetch</button>
      </div>

      {tools.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          No tools found. Try fetching tools first.
        </div>
      ) : (
        <div className="space-y-2">
          {tools.map(tool => (
            <div key={tool.name} className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <button
                onClick={() => toggleExpand(tool.name)}
                className="w-full text-left px-4 py-3 flex justify-between items-start hover:bg-gray-50"
              >
                <div>
                  <span className="font-mono text-sm font-medium text-gray-900">{tool.name}</span>
                  {tool.description && (
                    <p className="text-sm text-gray-500 mt-0.5">{tool.description}</p>
                  )}
                </div>
                <span className="text-gray-400 text-xs mt-1">
                  {expanded.has(tool.name) ? '▼' : '▶'}
                </span>
              </button>
              {expanded.has(tool.name) && tool.inputSchema && (
                <div className="px-4 pb-3 border-t border-gray-100">
                  <pre className="text-xs bg-gray-50 rounded p-3 overflow-x-auto mt-2 text-gray-700">
                    {JSON.stringify(tool.inputSchema, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
