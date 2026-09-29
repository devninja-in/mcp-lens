import { useState, useEffect, useRef } from 'react'
import type { ToolInfo, FullEvalReport } from '../types'
import type { ServerCapabilities, CapabilityAnalysis } from '../api'
import * as api from '../api'
import { downloadCombinedJson, downloadCombinedPdf, downloadCombinedYaml, downloadCombinedMd } from '../utils/download'
import type { ToolsDownloadOptions, EvalDownloadOptions, CombinedDownloadOptions, CapabilitiesDownloadData } from '../utils/download'
import EvaluationView from './EvaluationView'
import ComparisonView from './ComparisonView'
import DownloadModal from './DownloadModal'
import type { DownloadOption } from './DownloadModal'

interface Props {
  serverName: string
  authMode?: string | null
  initialTab?: 'tools' | 'evaluate' | 'comparison' | 'capabilities'
  onBack: () => void
  onToast: (message: string, type: 'success' | 'error' | 'info') => void
}

const LAYER_LABELS: Record<string, string> = {
  protocol: 'Protocol Compliance',
  quality: 'Tool Quality',
  security: 'Security Analysis',
  llm: 'LLM-Assisted Evaluation',
}

const LAYER_ORDER = ['protocol', 'quality', 'security', 'llm']

function CapabilitiesTab({
  serverName,
  analysis,
  analyzing,
  llmConfigs,
  selectedLlm,
  onSelectLlm,
  onRun,
}: {
  serverName: string
  analysis: CapabilityAnalysis | null
  analyzing: boolean
  llmConfigs: Record<string, api.LlmConfigInfo>
  selectedLlm: string
  onSelectLlm: (name: string) => void
  onRun: () => void
}) {
  const configEntries = Object.entries(llmConfigs)
  const hasConfigs = configEntries.length > 0
  const showLlmSelector = hasConfigs && configEntries.length > 1

  const llmSelector = showLlmSelector ? (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-xs font-medium text-gray-500">LLM:</span>
      {configEntries.map(([name, cfg]) => (
        <button
          key={name}
          onClick={() => onSelectLlm(name)}
          title={`${cfg.provider} / ${cfg.model}`}
          className={`px-2.5 py-1 text-xs font-medium rounded-lg border transition-colors ${
            selectedLlm === name
              ? 'bg-indigo-100 border-indigo-300 text-indigo-700'
              : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
          }`}
        >
          {name}
          {!cfg.has_credentials && <span className="ml-1 text-amber-500" title="Missing credentials">!</span>}
        </button>
      ))}
    </div>
  ) : null

  if (analyzing) {
    return (
      <div className="text-center py-16">
        <svg className="animate-spin h-8 w-8 mx-auto text-indigo-500" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <p className="text-sm text-gray-500 mt-3">Analyzing capabilities with LLM...</p>
      </div>
    )
  }

  if (!analysis) {
    return (
      <div className="text-center py-16">
        <div className="text-gray-400 text-lg mb-2">No capability analysis yet</div>
        <p className="text-sm text-gray-400 mb-6">
          Use LLM to categorize {serverName}'s tools into functional capability groups.
        </p>
        {llmSelector && <div className="mb-4">{llmSelector}</div>}
        <button
          onClick={onRun}
          disabled={!hasConfigs}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
        >Analyze Capabilities</button>
        {!hasConfigs && (
          <p className="text-xs text-gray-400 mt-2">No LLM configurations found. Create <code className="bg-gray-100 px-1 rounded">llm.json</code>.</p>
        )}
      </div>
    )
  }

  const categories = Object.entries(analysis.categories).sort(([a], [b]) => a.localeCompare(b))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-800">Capability Analysis</h3>
          <p className="text-sm text-gray-500">
            {analysis.tool_count} tools across {analysis.category_count} categories
            {analysis.llm_name && (
              <span className="text-gray-400"> — via {analysis.llm_name}</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {llmSelector}
          <button
            onClick={onRun}
            className="px-3 py-1.5 text-xs font-medium bg-indigo-100 text-indigo-700 rounded hover:bg-indigo-200"
          >Re-analyze</button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {categories.map(([category, catData]) => (
          <div key={category} className="bg-white border border-gray-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-sm font-semibold text-gray-800">{category}</h4>
              <span className="text-xs text-gray-400">{catData.tools.length} tools</span>
            </div>
            {catData.description && (
              <p className="text-xs text-gray-500 mb-3">{catData.description}</p>
            )}
            <div className="flex flex-wrap gap-1.5">
              {[...catData.tools].sort().map(tool => (
                <span
                  key={tool}
                  className="text-xs font-mono bg-indigo-50 text-indigo-700 px-2 py-1 rounded"
                >{tool}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ToolsViewer({ serverName, authMode, initialTab = 'tools', onBack, onToast }: Props) {
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [toolsSource, setToolsSource] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<'tools' | 'evaluate' | 'comparison' | 'capabilities'>(initialTab)
  const [evalKey, setEvalKey] = useState(0)
  const [downloadModal, setDownloadModal] = useState(false)
  const [evalReport, setEvalReport] = useState<FullEvalReport | null>(null)
  const [capabilities, setCapabilities] = useState<ServerCapabilities | null>(null)
  const [capsLoading, setCapsLoading] = useState(false)
  const [capAnalysis, setCapAnalysis] = useState<CapabilityAnalysis | null>(null)
  const [capAnalyzing, setCapAnalyzing] = useState(false)
  const [llmConfigs, setLlmConfigs] = useState<Record<string, api.LlmConfigInfo>>({})
  const [capSelectedLlm, setCapSelectedLlm] = useState('')
  const uploadInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { loadTools(); loadEvalReport(); loadCapabilities(); loadLlmConfigs(); loadCachedCapAnalysis() }, [serverName])

  async function loadTools() {
    try {
      const data = await api.getTools(serverName)
      setTools(data.tools)
      setToolsSource(data.source ?? 'fetched')
    } catch {
      setTools([])
      setToolsSource(null)
    } finally {
      setLoading(false)
    }
  }

  async function loadEvalReport() {
    try {
      const cached = await api.getEvalReport(serverName)
      setEvalReport(cached)
    } catch {
      setEvalReport(null)
    }
  }

  async function loadCapabilities() {
    setCapsLoading(true)
    try {
      const data = await api.getCapabilities(serverName)
      setCapabilities(data.success ? data : null)
    } catch {
      setCapabilities(null)
    } finally {
      setCapsLoading(false)
    }
  }

  async function loadLlmConfigs() {
    try {
      const data = await api.getLlmConfigs()
      setLlmConfigs(data.configs)
      if (data.default) setCapSelectedLlm(data.default)
    } catch { /* ignore */ }
  }

  async function loadCachedCapAnalysis() {
    try {
      const cached = await api.getCachedCapabilityAnalysis(serverName)
      if (cached) setCapAnalysis(cached)
    } catch { /* ignore */ }
  }

  async function handleRefetch() {
    setLoading(true)
    try {
      const result = await api.fetchTools(serverName) as any
      if (result.success) {
        setTools(result.tools)
        setEvalKey(k => k + 1)
        onToast(result.message, 'success')
      } else if (result.reauth) {
        if (authMode === 'oauth' || authMode === 'dcr') {
          onToast('Token expired. Opening browser for re-authentication...', 'info')
          try {
            await api.startAuth(serverName)
            onToast('Browser opened for authorization. Complete login and re-fetch.', 'info')
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

  function expandAll() {
    setExpanded(new Set(filteredTools.map(t => t.name)))
  }

  function collapseAll() {
    setExpanded(new Set())
  }

  async function handleUploadTools(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const result = await api.uploadTools(serverName, file)
      if (result.success) {
        setTools(result.tools)
        setToolsSource('uploaded')
        setEvalKey(k => k + 1)
        onToast(result.message, 'success')
        if (result.warnings.length > 0) {
          onToast(`Warnings: ${result.warnings.join('; ')}`, 'info')
        }
      }
    } catch (err) {
      onToast(`Upload failed: ${err}`, 'error')
    } finally {
      if (uploadInputRef.current) uploadInputRef.current.value = ''
    }
  }

  async function handleDeleteUploaded() {
    try {
      await api.deleteUploadedTools(serverName)
      setTools([])
      setToolsSource(null)
      onToast('Uploaded tools removed', 'success')
    } catch (err) {
      onToast(`Delete failed: ${err}`, 'error')
    }
  }

  function handleEvalReportUpdate(report: FullEvalReport | null) {
    setEvalReport(report)
  }

  function getCombinedDownloadOptions(): DownloadOption[] {
    const opts: DownloadOption[] = [
      { key: 't_overview', label: 'Tool overview table' },
      { key: 't_parameters', label: 'Parameter details' },
      { key: 't_schemas', label: 'Raw JSON schemas' },
    ]
    if (capabilities) {
      opts.push({ key: 'cap_protocol', label: 'Protocol capabilities' })
    }
    if (capAnalysis) {
      opts.push({ key: 'cap_analysis', label: 'Capability analysis (LLM)' })
    }
    if (evalReport) {
      opts.push({ key: 'e_summary', label: 'Eval: Summary & Scores' })
      for (const k of LAYER_ORDER) {
        if (k in evalReport.layers) {
          opts.push({ key: `e_${k}`, label: `Eval: ${LAYER_LABELS[k] || k}` })
        }
      }
      const fps = (evalReport.metadata?.false_positives as Record<string, string>) ?? {}
      if (Object.keys(fps).length > 0) {
        opts.push({ key: 'e_false_positives', label: 'Eval: False positive overrides' })
      }
      if (evalReport.metadata?.per_llm) {
        opts.push({ key: 'c_comparison', label: 'LLM Tool Selection Comparison' })
      }
    }
    return opts
  }

  function handleCombinedDownload(selected: Set<string>, format: string) {
    const hasToolsSelection = selected.has('t_overview') || selected.has('t_parameters') || selected.has('t_schemas')
    const hasEvalSelection = [...selected].some(k => k.startsWith('e_'))
    const hasCapsSelection = selected.has('cap_protocol') || selected.has('cap_analysis')

    const toolsOpts: ToolsDownloadOptions | null = hasToolsSelection ? {
      showOverview: selected.has('t_overview'),
      showParameters: selected.has('t_parameters'),
      showSchemas: selected.has('t_schemas'),
    } : null

    const evalOpts: EvalDownloadOptions | null = hasEvalSelection ? {
      layers: new Set(LAYER_ORDER.filter(k => selected.has(`e_${k}`))),
      showSummary: selected.has('e_summary'),
      showFalsePositives: selected.has('e_false_positives'),
    } : null

    const capsOpts: CapabilitiesDownloadData | null = hasCapsSelection ? {
      protocol: selected.has('cap_protocol') ? capabilities : null,
      analysis: selected.has('cap_analysis') ? capAnalysis : null,
    } : null

    const opts: CombinedDownloadOptions = { tools: toolsOpts, eval: evalOpts, comparison: selected.has('c_comparison'), capabilities: capsOpts }

    if (format === 'pdf') {
      downloadCombinedPdf(tools, evalReport, serverName, opts)
    } else if (format === 'yaml') {
      downloadCombinedYaml(tools, evalReport, serverName, opts)
    } else if (format === 'md') {
      downloadCombinedMd(tools, evalReport, serverName, opts)
    } else {
      downloadCombinedJson(tools, evalReport, serverName, opts)
    }
    setDownloadModal(false)
  }

  const filteredTools = search
    ? tools.filter(t =>
        t.name.toLowerCase().includes(search.toLowerCase()) ||
        (t.description?.toLowerCase().includes(search.toLowerCase()))
      )
    : tools

  if (loading) return <div className="text-center py-12 text-gray-500">Loading tools...</div>

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="text-sm text-gray-500 hover:text-gray-700"
          >&larr; Back</button>
          <h2 className="text-xl font-semibold text-gray-800">
            {serverName}
            <span className="text-sm font-normal text-gray-500 ml-2">({tools.length} tools)</span>
            {toolsSource && tools.length > 0 && (
              toolsSource === 'uploaded'
                ? <span className="ml-2 px-2 py-0.5 text-xs font-medium rounded-full bg-amber-100 text-amber-700">Uploaded by user</span>
                : <span className="ml-2 px-2 py-0.5 text-xs font-medium rounded-full bg-green-100 text-green-700">Fetched from server</span>
            )}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setDownloadModal(true)}
            disabled={tools.length === 0}
            className="px-3 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
          >Export</button>
          {tab === 'tools' && (
            <>
              <button
                onClick={() => api.downloadToolsTemplate(serverName)}
                className="px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 text-sm font-medium"
              >Template</button>
              <button
                onClick={() => uploadInputRef.current?.click()}
                className="px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
              >Upload</button>
              <input
                ref={uploadInputRef}
                type="file"
                accept=".yaml,.yml"
                className="hidden"
                onChange={handleUploadTools}
              />
              {toolsSource === 'uploaded' && (
                <button
                  onClick={handleDeleteUploaded}
                  className="px-3 py-2 text-red-600 hover:text-red-800 text-sm font-medium"
                >Remove</button>
              )}
              <button
                onClick={handleRefetch}
                disabled={loading}
                className="px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium disabled:opacity-50"
              >Re-fetch</button>
            </>
          )}
        </div>
      </div>

      {/* Capabilities */}
      {capsLoading ? (
        <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4">
          <p className="text-sm text-gray-400">Loading capabilities...</p>
        </div>
      ) : capabilities ? (
        <div className="bg-white border border-gray-200 rounded-lg p-5 mb-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-800">Protocol Capabilities</h3>
            {capabilities.serverInfo && (
              <span className="text-xs text-gray-400">
                {(capabilities.serverInfo as Record<string, string>).name}
                {(capabilities.serverInfo as Record<string, string>).version && ` v${(capabilities.serverInfo as Record<string, string>).version}`}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {(() => {
              const caps = capabilities.capabilities || {}
              const knownCaps = ['tools', 'resources', 'prompts', 'logging', 'completions', 'experimental']
              const allCaps = Array.from(new Set([...knownCaps, ...Object.keys(caps)])).sort()
              return allCaps.map(cap => {
                const supported = cap in caps
                return (
                  <span
                    key={cap}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${
                      supported
                        ? 'bg-green-50 text-green-700 border border-green-200'
                        : 'bg-gray-50 text-gray-400 border border-gray-200'
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${supported ? 'bg-green-500' : 'bg-gray-300'}`} />
                    {cap}
                  </span>
                )
              })
            })()}
          </div>
        </div>
      ) : null}

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-4">
        <button
          onClick={() => setTab('tools')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'tools'
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >Tools</button>
        <button
          onClick={() => setTab('evaluate')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'evaluate'
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >Evaluate</button>
        <button
          onClick={() => setTab('comparison')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'comparison'
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >LLM Tool Selection</button>
        <button
          onClick={() => setTab('capabilities')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'capabilities'
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >Capabilities</button>
      </div>

      {tab === 'evaluate' ? (
        <EvaluationView key={evalKey} serverName={serverName} onToast={onToast} onReportChange={handleEvalReportUpdate} />
      ) : tab === 'comparison' ? (
        <ComparisonView serverName={serverName} onToast={onToast} onReportChange={handleEvalReportUpdate} />
      ) : tab === 'capabilities' ? (
        <CapabilitiesTab
          serverName={serverName}
          analysis={capAnalysis}
          analyzing={capAnalyzing}
          llmConfigs={llmConfigs}
          selectedLlm={capSelectedLlm}
          onSelectLlm={setCapSelectedLlm}
          onRun={async () => {
            setCapAnalyzing(true)
            try {
              const llm = capSelectedLlm || undefined
              const result = await api.analyzeCapabilities(serverName, llm)
              setCapAnalysis(result)
              onToast('Capability analysis complete', 'success')
            } catch (e) {
              onToast(`Analysis failed: ${e}`, 'error')
            } finally {
              setCapAnalyzing(false)
            }
          }}
        />
      ) : (
      <>

      {tools.length > 0 && (
        <div className="flex items-center gap-3 mb-4">
          <input
            type="text"
            placeholder="Search tools..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button onClick={expandAll} className="text-xs text-gray-500 hover:text-gray-700 whitespace-nowrap">Expand All</button>
          <button onClick={collapseAll} className="text-xs text-gray-500 hover:text-gray-700 whitespace-nowrap">Collapse All</button>
        </div>
      )}

      {filteredTools.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          {tools.length === 0
            ? 'No tools found. Try fetching tools first.'
            : 'No tools match your search.'}
        </div>
      ) : (
        <div className="space-y-2">
          {filteredTools.map(tool => {
            const isExpanded = expanded.has(tool.name)
            const params = tool.inputSchema?.properties as Record<string, { type?: string; description?: string }> | undefined
            const required = (tool.inputSchema?.required as string[]) || []

            return (
              <div key={tool.name} className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <button
                  onClick={() => toggleExpand(tool.name)}
                  className="w-full text-left px-4 py-3 flex justify-between items-start hover:bg-gray-50"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-medium text-blue-700">{tool.name}</span>
                      {params && (
                        <span className="text-xs text-gray-400">{Object.keys(params).length} params</span>
                      )}
                    </div>
                    {tool.description && (
                      <p className="text-sm text-gray-500 mt-0.5 truncate">{tool.description}</p>
                    )}
                  </div>
                  <span className="text-gray-400 text-xs mt-1 ml-2">
                    {isExpanded ? '▼' : '▶'}
                  </span>
                </button>
                {isExpanded && (
                  <div className="px-4 pb-4 border-t border-gray-100">
                    {tool.description && (
                      <p className="text-sm text-gray-600 mt-3 mb-3">{tool.description}</p>
                    )}

                    {params && Object.keys(params).length > 0 && (
                      <div className="mb-3">
                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Parameters</h4>
                        <div className="bg-gray-50 rounded-lg overflow-hidden">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-gray-200">
                                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Name</th>
                                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Type</th>
                                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Required</th>
                                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Description</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(params).map(([pName, pDef]) => (
                                <tr key={pName} className="border-b border-gray-100 last:border-0">
                                  <td className="px-3 py-2 font-mono text-xs text-gray-800">{pName}</td>
                                  <td className="px-3 py-2 text-xs text-indigo-600">{pDef.type || '—'}</td>
                                  <td className="px-3 py-2 text-xs">
                                    {required.includes(pName)
                                      ? <span className="text-red-500 font-medium">yes</span>
                                      : <span className="text-gray-400">no</span>}
                                  </td>
                                  <td className="px-3 py-2 text-xs text-gray-500">{pDef.description || '—'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {tool.inputSchema && (
                      <details className="mt-2">
                        <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">Raw JSON Schema</summary>
                        <pre className="text-xs bg-gray-50 rounded p-3 overflow-x-auto mt-1 text-gray-700">
                          {JSON.stringify(tool.inputSchema, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      </>
      )}

      {downloadModal && (
        <DownloadModal
          title="Export Report"
          options={getCombinedDownloadOptions()}
          onDownload={handleCombinedDownload}
          onClose={() => setDownloadModal(false)}
        />
      )}
    </div>
  )
}
