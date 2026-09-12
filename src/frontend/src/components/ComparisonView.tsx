import { useState, useEffect } from 'react'
import * as api from '../api'
import type { LlmConfigInfo, LlmEvalResult } from '../api'
import type { FullEvalReport, FullLayerResult } from '../types'
import LlmEvalModal from './LlmEvalModal'

interface Props {
  serverName: string
  onToast: (message: string, type: 'success' | 'error' | 'info') => void
  onReportChange?: (report: FullEvalReport | null) => void
}

interface ToolSelectionCell {
  expected: string
  selected: string
  status: string
  scenario: string
  scenarioSource: string
  arguments?: Record<string, unknown>
  suggestion?: string
  prerequisiteReason?: string
  message?: string
}

type ComparisonData = {
  tools: string[]
  llms: string[]
  llmMeta: Record<string, { provider: string; model: string }>
  grid: Record<string, Record<string, ToolSelectionCell>>
  scores: Record<string, { pass: number; total: number }>
}

function Spinner({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function extractCellFromCheck(check: { status: string; message: string; details?: Record<string, unknown> }, toolName: string): ToolSelectionCell {
  const d = check.details ?? {}
  return {
    expected: (d.expected as string) ?? toolName,
    selected: (d.selected as string) ?? '—',
    status: check.status,
    scenario: (d.scenario as string) ?? '',
    scenarioSource: (d.scenario_source as string) ?? 'auto_generated',
    arguments: (d.arguments as Record<string, unknown>) ?? undefined,
    suggestion: (d.suggestion as string) ?? undefined,
    prerequisiteReason: (d.prerequisite_reason as string) ?? undefined,
    message: check.message,
  }
}

function computeScores(grid: Record<string, Record<string, ToolSelectionCell>>, llms: string[]): Record<string, { pass: number; total: number }> {
  const scores: Record<string, { pass: number; total: number }> = {}
  for (const llm of llms) {
    let pass = 0, total = 0
    for (const cells of Object.values(grid)) {
      const cell = cells[llm]
      if (!cell || cell.status === 'skip') continue
      total++
      if (cell.status === 'pass') pass++
    }
    scores[llm] = { pass, total }
  }
  return scores
}

function extractComparison(result: LlmEvalResult): ComparisonData | null {
  const grid: Record<string, Record<string, ToolSelectionCell>> = {}
  const llmMeta: Record<string, { provider: string; model: string }> = {}
  const toolSet = new Set<string>()
  const llmList: string[] = []

  function extractFromLayer(layer: FullLayerResult, llmName: string) {
    for (const tool of layer.tools) {
      const selectionChecks = tool.checks.filter(c => c.check_id === 'llm.tool_selection')
      if (selectionChecks.length === 0) continue
      toolSet.add(tool.tool_name)
      if (!grid[tool.tool_name]) grid[tool.tool_name] = {}
      grid[tool.tool_name][llmName] = extractCellFromCheck(selectionChecks[0], tool.tool_name)
    }
  }

  if (result.per_llm && Object.keys(result.per_llm).length > 0) {
    for (const [llmName, data] of Object.entries(result.per_llm)) {
      if (data.layer) {
        llmList.push(llmName)
        llmMeta[llmName] = { provider: data.metadata.llm_provider, model: data.metadata.llm_model }
        extractFromLayer(data.layer, llmName)
      }
    }
  } else if (result.layer) {
    const llmName = result.metadata.llm_model || result.metadata.llm_provider || 'default'
    llmList.push(llmName)
    llmMeta[llmName] = { provider: result.metadata.llm_provider, model: result.metadata.llm_model || '' }
    extractFromLayer(result.layer, llmName)
  }

  if (llmList.length === 0) return null
  const tools = Array.from(toolSet).sort()
  return { tools, llms: llmList, llmMeta, grid, scores: computeScores(grid, llmList) }
}

function extractComparisonFromReport(report: FullEvalReport): ComparisonData | null {
  const perLlm = report.metadata?.per_llm as Record<string, {
    layer?: FullLayerResult
    error?: string
    metadata: { llm_provider: string; llm_model: string }
  }> | undefined
  if (!perLlm || Object.keys(perLlm).length === 0) return null

  const grid: Record<string, Record<string, ToolSelectionCell>> = {}
  const llmMeta: Record<string, { provider: string; model: string }> = {}
  const toolSet = new Set<string>()
  const llmList: string[] = []

  for (const [llmName, data] of Object.entries(perLlm)) {
    if (!data.layer) continue
    llmList.push(llmName)
    llmMeta[llmName] = { provider: data.metadata.llm_provider, model: data.metadata.llm_model }
    for (const tool of data.layer.tools) {
      const selectionChecks = tool.checks.filter(c => c.check_id === 'llm.tool_selection')
      if (selectionChecks.length === 0) continue
      toolSet.add(tool.tool_name)
      if (!grid[tool.tool_name]) grid[tool.tool_name] = {}
      grid[tool.tool_name][llmName] = extractCellFromCheck(selectionChecks[0], tool.tool_name)
    }
  }

  if (llmList.length === 0) return null
  const tools = Array.from(toolSet).sort()
  return { tools, llms: llmList, llmMeta, grid, scores: computeScores(grid, llmList) }
}

function statusStyle(status: string): { icon: string; bg: string; text: string } {
  switch (status) {
    case 'pass': return { icon: '✓', bg: 'bg-green-50', text: 'text-green-700' }
    case 'fail': return { icon: '✗', bg: 'bg-red-50', text: 'text-red-700' }
    case 'warn': return { icon: '!', bg: 'bg-yellow-50', text: 'text-yellow-700' }
    default: return { icon: '—', bg: 'bg-gray-50', text: 'text-gray-400' }
  }
}

function LlmCell({ cell, toolName }: { cell: ToolSelectionCell; toolName: string }) {
  const [expanded, setExpanded] = useState(false)
  const style = statusStyle(cell.status)
  const args = cell.arguments
  const hasArgs = args && Object.keys(args).length > 0
  const hasDetail = hasArgs || (cell.status === 'fail' && cell.suggestion) || (cell.status === 'warn' && cell.prerequisiteReason) || (cell.status === 'skip' && cell.message)

  return (
    <td className={`px-3 py-2.5 ${style.bg} align-top`}>
      {/* Status + selected tool */}
      <div className="flex items-center justify-center gap-1.5">
        <span className={`text-sm font-bold ${style.text}`}>{style.icon}</span>
        <span className={`text-xs font-mono ${style.text}`}>{cell.selected}</span>
      </div>

      {/* Expand toggle */}
      {hasDetail && (
        <div className="text-center mt-1">
          <button
            onClick={e => { e.stopPropagation(); setExpanded(!expanded) }}
            className="text-[10px] text-gray-400 hover:text-gray-600"
          >{expanded ? '▲ less' : '▼ details'}</button>
        </div>
      )}

      {expanded && (
        <div className="mt-1.5 text-left space-y-1">
          {/* Arguments */}
          {hasArgs && (
            <div className="bg-white/80 rounded border border-gray-200 p-1.5">
              <div className="text-[10px] font-medium text-gray-500 mb-0.5">Parameters</div>
              {Object.entries(args).map(([k, v]) => (
                <div key={k} className="text-[10px] leading-relaxed">
                  <span className="font-mono text-indigo-600">{k}</span>
                  <span className="text-gray-400">: </span>
                  <span className="text-gray-600 break-all">{typeof v === 'string' ? v : JSON.stringify(v)}</span>
                </div>
              ))}
            </div>
          )}

          {/* Fail info */}
          {cell.status === 'fail' && cell.selected !== toolName && (
            <div className="text-[10px] text-red-600">
              <span className="font-medium">Expected:</span> <span className="font-mono">{toolName}</span>
              {cell.suggestion && <div className="mt-0.5 italic text-red-500">{cell.suggestion}</div>}
            </div>
          )}

          {/* Warn info */}
          {cell.status === 'warn' && cell.prerequisiteReason && (
            <div className="text-[10px] text-yellow-600 italic">{cell.prerequisiteReason}</div>
          )}

          {/* Skip info */}
          {cell.status === 'skip' && cell.message && (
            <div className="text-[10px] text-gray-500 italic">{cell.message}</div>
          )}
        </div>
      )}
    </td>
  )
}

export default function ComparisonView({ serverName, onToast, onReportChange }: Props) {
  const [llmConfigs, setLlmConfigs] = useState<Record<string, LlmConfigInfo>>({})
  const [selectedLlms, setSelectedLlms] = useState<string[]>([])
  const [groundTruthCount, setGroundTruthCount] = useState<number | null>(null)
  const [groundTruthPromptCount, setGroundTruthPromptCount] = useState<number>(0)
  const [showModal, setShowModal] = useState(false)
  const [loading, setLoading] = useState(false)
  const [comparison, setComparison] = useState<ComparisonData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedScenarios, setExpandedScenarios] = useState<Set<string>>(new Set())

  useEffect(() => {
    loadConfigs()
    loadGroundTruth()
    loadCachedComparison()
  }, [serverName])

  async function loadCachedComparison() {
    try {
      const report = await api.getEvalReport(serverName)
      if (report?.metadata?.per_llm) {
        const data = extractComparisonFromReport(report)
        if (data) setComparison(data)
      }
    } catch { /* no cached report */ }
  }

  async function loadConfigs() {
    try {
      const data = await api.getLlmConfigs()
      setLlmConfigs(data.configs)
    } catch { /* ignore */ }
  }

  async function loadGroundTruth() {
    const gt = await api.getGroundTruth(serverName)
    setGroundTruthCount(gt ? gt.test_case_count : null)
    setGroundTruthPromptCount(gt ? gt.prompt_count : 0)
  }

  function toggleLlm(name: string) {
    setSelectedLlms(prev => prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name])
  }

  async function handleUploadGroundTruth(file: File) {
    try {
      const result = await api.uploadGroundTruth(serverName, file)
      setGroundTruthCount(result.test_case_count)
      setGroundTruthPromptCount(result.prompt_count)
      onToast(`Uploaded ${result.test_case_count} test cases (${result.prompt_count} prompts)`, 'success')
    } catch (e) {
      onToast(`Upload failed: ${e}`, 'error')
    }
  }

  async function handleDeleteGroundTruth() {
    try {
      await api.deleteGroundTruth(serverName)
      setGroundTruthCount(null)
      setGroundTruthPromptCount(0)
      onToast('Ground truth deleted', 'success')
    } catch (e) {
      onToast(`Delete failed: ${e}`, 'error')
    }
  }

  function handleDownloadTemplate() {
    api.downloadGroundTruthTemplate(serverName)
  }

  async function runComparison() {
    setShowModal(false)
    setLoading(true)
    setError(null)
    setComparison(null)
    try {
      const llmsToUse = selectedLlms.length > 0 ? selectedLlms : undefined
      const result = await api.evaluateLlm(serverName, llmsToUse)
      if (result.error) {
        setError(result.error)
      } else {
        const data = extractComparison(result)
        if (data) {
          setComparison(data)
        } else {
          setError('No tool selection results returned.')
        }
      }
      // Refresh the cached report so Export picks up per_llm
      try {
        const updated = await api.getEvalReport(serverName)
        onReportChange?.(updated)
      } catch { /* ignore */ }
    } catch (e) {
      setError(`${e}`)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="text-center py-16">
        <Spinner className="h-8 w-8 mx-auto text-indigo-500" />
        <p className="text-sm text-gray-500 mt-3">Running LLM tool selection across models...</p>
      </div>
    )
  }

  if (!comparison) {
    return (
      <div className="text-center py-16">
        <div className="text-gray-400 text-lg mb-2">No comparison data yet</div>
        <p className="text-sm text-gray-400 mb-6">Select LLMs and run a tool selection comparison to see how different models choose tools.</p>
        {error && (
          <div className="max-w-md mx-auto mb-4 px-4 py-2.5 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {error}
          </div>
        )}
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"
        >Run LLM Comparison</button>
        {showModal && (
          <LlmEvalModal
            configs={llmConfigs}
            selectedLlms={selectedLlms}
            onToggleLlm={toggleLlm}
            groundTruthCount={groundTruthCount}
            groundTruthPromptCount={groundTruthPromptCount}
            onUploadGroundTruth={handleUploadGroundTruth}
            onDeleteGroundTruth={handleDeleteGroundTruth}
            onDownloadTemplate={handleDownloadTemplate}
            onRun={runComparison}
            onClose={() => setShowModal(false)}
            loading={loading}
            title="LLM Tool Selection Comparison"
            runLabel="Run Comparison"
          />
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-800">Tool Selection Comparison</h3>
          <p className="text-sm text-gray-500">
            {comparison.tools.length} tools across {comparison.llms.length} LLMs
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-3 py-1.5 text-xs font-medium bg-indigo-100 text-indigo-700 rounded hover:bg-indigo-200"
        >Re-run</button>
      </div>

      {error && (
        <div className="px-4 py-2.5 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
          {error}
        </div>
      )}

      {/* Comparison Table */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="text-left px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide sticky left-0 bg-gray-50 z-10 min-w-[160px]">Tool</th>
                {comparison.llms.map(llm => (
                  <th key={llm} className="text-center px-3 py-3 min-w-[180px]">
                    <div className="text-xs font-medium text-gray-800">{llm}</div>
                    <div className="text-[10px] text-gray-400 mt-0.5">
                      {comparison.llmMeta[llm]?.provider} / {comparison.llmMeta[llm]?.model}
                    </div>
                  </th>
                ))}
                <th className="text-left px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide min-w-[120px]">Scenario</th>
              </tr>
            </thead>
            <tbody>
              {comparison.tools.map(toolName => {
                const firstLlm = comparison.llms[0]
                const firstCell = comparison.grid[toolName]?.[firstLlm]
                const scenario = firstCell?.scenario ?? ''
                const isScenarioExpanded = expandedScenarios.has(toolName)

                return (
                  <tr key={toolName} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2.5 font-mono text-xs text-gray-800 sticky left-0 bg-white z-10 align-top">
                      {toolName}
                    </td>
                    {comparison.llms.map(llm => {
                      const cell = comparison.grid[toolName]?.[llm]
                      if (!cell) {
                        return <td key={llm} className="px-3 py-2.5 text-center text-gray-300 align-top">—</td>
                      }
                      return <LlmCell key={llm} cell={cell} toolName={toolName} />
                    })}
                    <td className="px-3 py-2.5 align-top">
                      {scenario && (
                        <button
                          onClick={() => setExpandedScenarios(prev => {
                            const next = new Set(prev)
                            next.has(toolName) ? next.delete(toolName) : next.add(toolName)
                            return next
                          })}
                          className="text-left text-xs text-gray-500 hover:text-gray-700"
                        >
                          {isScenarioExpanded ? scenario : scenario.length > 50 ? scenario.slice(0, 50) + '...' : scenario}
                        </button>
                      )}
                      {firstCell?.scenarioSource === 'user_provided' && (
                        <span className="ml-1 px-1 py-0.5 text-[9px] font-medium bg-teal-100 text-teal-700 rounded">GT</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr className="border-t border-gray-200 bg-gray-50">
                <td className="px-3 py-2.5 text-xs font-medium text-gray-600 sticky left-0 bg-gray-50 z-10">LLM Score</td>
                {comparison.llms.map(llm => {
                  const s = comparison.scores[llm] ?? { pass: 0, total: 0 }
                  const pct = s.total > 0 ? (s.pass / s.total) * 100 : 0
                  const color = pct >= 80 ? 'text-green-700' : pct >= 60 ? 'text-yellow-700' : 'text-red-700'
                  return (
                    <td key={llm} className="px-3 py-2.5 text-center">
                      <span className={`text-sm font-bold ${color}`}>{pct.toFixed(0)}%</span>
                      <span className="text-[10px] text-gray-400 ml-1">({s.pass}/{s.total})</span>
                    </td>
                  )
                })}
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      {showModal && (
        <LlmEvalModal
          configs={llmConfigs}
          selectedLlms={selectedLlms}
          onToggleLlm={toggleLlm}
          groundTruthCount={groundTruthCount}
          groundTruthPromptCount={groundTruthPromptCount}
          onUploadGroundTruth={handleUploadGroundTruth}
          onDeleteGroundTruth={handleDeleteGroundTruth}
          onDownloadTemplate={handleDownloadTemplate}
          onRun={runComparison}
          onClose={() => setShowModal(false)}
          loading={loading}
          title="LLM Tool Selection Comparison"
          runLabel="Run Comparison"
        />
      )}
    </div>
  )
}
