import { useState, useEffect } from 'react'
import type { FullEvalReport, FullCheckResult, FullLayerResult } from '../types'
import * as api from '../api'
import type { LlmConfigInfo } from '../api'
import LlmEvalModal from './LlmEvalModal'

interface Props {
  serverName: string
  onToast: (message: string, type: 'success' | 'error' | 'info') => void
  onReportChange?: (report: FullEvalReport | null) => void
}

const LAYER_LABELS: Record<string, string> = {
  protocol: 'Protocol Compliance',
  quality: 'Tool Quality',
  security: 'Security Analysis',
  llm: 'LLM-Assisted Evaluation',
}

const LAYER_ORDER = ['protocol', 'quality', 'security', 'llm']

function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-600'
  if (score >= 60) return 'text-yellow-600'
  return 'text-red-600'
}

function scoreBg(score: number): string {
  if (score >= 80) return 'bg-green-500'
  if (score >= 60) return 'bg-yellow-500'
  return 'bg-red-500'
}

function scoreBadgeBg(score: number): string {
  if (score >= 80) return 'bg-green-100 text-green-800'
  if (score >= 60) return 'bg-yellow-100 text-yellow-800'
  return 'bg-red-100 text-red-800'
}

function statusIcon(status: string): { icon: string; color: string } {
  switch (status) {
    case 'pass': return { icon: '✓', color: 'text-green-600' }
    case 'fail': return { icon: '✗', color: 'text-red-600' }
    case 'warn': return { icon: '!', color: 'text-yellow-600' }
    case 'skip': return { icon: '—', color: 'text-gray-400' }
    default: return { icon: '?', color: 'text-gray-400' }
  }
}

function severityBadge(severity: string): string {
  switch (severity) {
    case 'critical': return 'bg-red-100 text-red-700'
    case 'high': return 'bg-orange-100 text-orange-700'
    case 'medium': return 'bg-yellow-100 text-yellow-700'
    case 'low': return 'bg-blue-100 text-blue-700'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit',
    })
  } catch {
    return ts
  }
}

function Spinner({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

export default function EvaluationView({ serverName, onToast, onReportChange }: Props) {
  const [report, setReport] = useState<FullEvalReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [llmLoading, setLlmLoading] = useState(false)
  const [llmError, setLlmError] = useState<string | null>(null)
  const [expandedLayers, setExpandedLayers] = useState<Set<string>>(new Set())
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set())
  const [groundTruthCount, setGroundTruthCount] = useState<number | null>(null)
  const [groundTruthPromptCount, setGroundTruthPromptCount] = useState<number>(0)
  const [llmConfigs, setLlmConfigs] = useState<Record<string, LlmConfigInfo>>({})
  const [selectedLlms, setSelectedLlms] = useState<string[]>([])
  const [perLlmResults, setPerLlmResults] = useState<Record<string, { layer?: FullLayerResult; error?: string; metadata: Record<string, string> }> | null>(null)
  const [activeLlmTab, setActiveLlmTab] = useState<string>('combined')
  const [showLlmModal, setShowLlmModal] = useState(false)

  useEffect(() => {
    loadCachedReport()
    loadGroundTruth()
    loadLlmConfigs()
  }, [serverName])

  async function loadGroundTruth() {
    const gt = await api.getGroundTruth(serverName)
    setGroundTruthCount(gt ? gt.test_case_count : null)
    setGroundTruthPromptCount(gt ? gt.prompt_count : 0)
  }

  async function loadLlmConfigs() {
    try {
      const data = await api.getLlmConfigs()
      setLlmConfigs(data.configs)
    } catch { /* ignore */ }
  }

  async function handleUploadGroundTruth(file: File) {
    try {
      const result = await api.uploadGroundTruth(serverName, file)
      setGroundTruthCount(result.test_case_count)
      setGroundTruthPromptCount(result.prompt_count)
      onToast(`Uploaded ${result.test_case_count} test cases (${result.prompt_count} prompts)`, 'success')
      if (result.warnings.length > 0) {
        onToast(`Warnings: ${result.warnings.join(', ')}`, 'info')
      }
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

  function toggleLlmSelection(name: string) {
    setSelectedLlms(prev =>
      prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]
    )
  }

  function updateReport(r: FullEvalReport | null) {
    setReport(r)
    onReportChange?.(r)
  }

  async function loadCachedReport() {
    setLoading(true)
    try {
      const cached = await api.getEvalReport(serverName)
      updateReport(cached)
    } catch {
      updateReport(null)
    } finally {
      setLoading(false)
    }
  }

  async function runEvaluation(withLlm: boolean) {
    setRunning(true)
    setLlmLoading(false)
    setLlmError(null)
    setPerLlmResults(null)
    setActiveLlmTab('combined')
    try {
      const data = await api.evaluateToolsFull(serverName)
      updateReport(data)
      setRunning(false)

      const hasLlmConfigs = Object.keys(llmConfigs).length > 0
      if (withLlm && (data.metadata?.llm_configured || hasLlmConfigs)) {
        setLlmLoading(true)
        try {
          const llmsToUse = selectedLlms.length > 0 ? selectedLlms : undefined
          const llmResult = await api.evaluateLlm(serverName, llmsToUse)
          if (llmResult.error) {
            setLlmError(llmResult.error)
            setReport(prev => {
              const next = prev ? { ...prev, metadata: { ...prev.metadata, ...llmResult.metadata } } : prev
              if (next) onReportChange?.(next)
              return next
            })
          } else if (llmResult.layer) {
            setReport(prev => {
              const next = prev ? {
                ...prev,
                layers: { ...prev.layers, llm: llmResult.layer! },
                overall_score: llmResult.overall_score ?? prev.overall_score,
                gate_passed: llmResult.gate_passed ?? prev.gate_passed,
                metadata: { ...prev.metadata, ...llmResult.metadata },
              } : prev
              if (next) onReportChange?.(next)
              return next
            })
          }
          if (llmResult.per_llm) {
            setPerLlmResults(llmResult.per_llm as any)
          }
        } catch (e) {
          setLlmError(`${e}`)
        } finally {
          setLlmLoading(false)
        }
      } else if (withLlm && !data.metadata?.llm_configured && !hasLlmConfigs) {
        onToast('LLM not configured. Set EVAL_LLM_PROVIDER in .env or create llm.json.', 'info')
      }
    } catch (e) {
      onToast(`Evaluation failed: ${e}`, 'error')
      setRunning(false)
    }
  }

  function toggleLayer(layer: string) {
    setExpandedLayers(prev => {
      const next = new Set(prev)
      next.has(layer) ? next.delete(layer) : next.add(layer)
      return next
    })
  }

  function toggleTool(key: string) {
    setExpandedTools(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const falsePositives: Record<string, string> = (report?.metadata?.false_positives as Record<string, string>) ?? {}

  async function handleToggleFP(checkKey: string, justification: string | null) {
    try {
      const result = await api.markFalsePositive(serverName, checkKey, justification)
      if (result.success) {
        setReport(prev => {
          const next = prev ? { ...prev, metadata: { ...prev.metadata, false_positives: result.false_positives } } : prev
          if (next) onReportChange?.(next)
          return next
        })
      }
    } catch (e) {
      onToast(`Failed to update false positive: ${e}`, 'error')
    }
  }

  const isRunning = running || llmLoading

  if (loading) return <div className="text-center py-12 text-gray-500">Loading...</div>

  if (!report) {
    return (
      <div className="text-center py-16">
        <div className="text-gray-400 text-lg mb-2">No evaluation has been run yet</div>
        <p className="text-sm text-gray-400 mb-6">Run an evaluation to check protocol compliance, quality, and security of this server's tools.</p>
        <div className="flex justify-center gap-3 mt-4">
          <button
            onClick={() => runEvaluation(false)}
            disabled={isRunning}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium disabled:opacity-50"
          >
            {running ? <><Spinner className="h-4 w-4 inline mr-1.5" /> Running...</> : 'Run Evaluation'}
          </button>
          <button
            onClick={() => setShowLlmModal(true)}
            disabled={isRunning}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
          >
            Run with LLM
          </button>
        </div>
        {showLlmModal && (
          <LlmEvalModal
            configs={llmConfigs}
            selectedLlms={selectedLlms}
            onToggleLlm={toggleLlmSelection}
            groundTruthCount={groundTruthCount}
            groundTruthPromptCount={groundTruthPromptCount}
            onUploadGroundTruth={handleUploadGroundTruth}
            onDeleteGroundTruth={handleDeleteGroundTruth}
            onDownloadTemplate={handleDownloadTemplate}
            onRun={() => { setShowLlmModal(false); runEvaluation(true) }}
            onClose={() => setShowLlmModal(false)}
            loading={isRunning}
          />
        )}
      </div>
    )
  }

  const layers = LAYER_ORDER
    .filter(k => k in report.layers)
    .map(k => ({ key: k, ...report.layers[k] }))

  const totalChecks = Object.values(report.layers).reduce((sum, l) => {
    const toolChecks = l.tools.reduce((ts, t) => ts + t.checks.length, 0)
    return sum + toolChecks + (l.catalog_checks?.length || 0)
  }, 0)

  return (
    <div className="space-y-6">
      {/* LLM Status Banner */}
      {report.metadata?.llm_provider && !report.metadata.llm_error && !llmLoading ? (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-indigo-50 border border-indigo-200 rounded-lg text-sm text-indigo-800">
          <span className="w-2 h-2 rounded-full bg-indigo-500 shrink-0" />
          LLM-assisted evaluation: enabled
          <span className="text-indigo-600 font-medium">
            ({report.metadata.llm_provider}{report.metadata.llm_model ? ` / ${report.metadata.llm_model}` : ''})
          </span>
        </div>
      ) : llmLoading ? (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-indigo-50 border border-indigo-200 rounded-lg text-sm text-indigo-700">
          <Spinner className="h-4 w-4 text-indigo-500 shrink-0" />
          LLM-assisted evaluation: running...
        </div>
      ) : (report.metadata?.llm_error || llmError) ? (
        <div className="flex items-start gap-2 px-4 py-2.5 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0 mt-1" />
          <div>
            <span>LLM-assisted evaluation: failed</span>
            {report.metadata?.llm_provider && (
              <span className="text-amber-600 font-medium ml-1">
                ({report.metadata.llm_provider}{report.metadata.llm_model ? ` / ${report.metadata.llm_model}` : ''})
              </span>
            )}
            <p className="text-xs text-amber-700 mt-0.5">{report.metadata?.llm_error || llmError}</p>
          </div>
        </div>
      ) : !report.metadata?.llm_configured ? (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-500">
          <span className="w-2 h-2 rounded-full bg-gray-300 shrink-0" />
          LLM-assisted evaluation: not configured — set <code className="bg-gray-100 px-1 rounded text-xs">EVAL_LLM_PROVIDER</code> in .env to enable
        </div>
      ) : null}

      {/* Summary Header */}
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-3">
              <h3 className="text-lg font-semibold text-gray-800">Evaluation Report</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => runEvaluation(false)}
                  disabled={isRunning}
                  className="px-2.5 py-1 text-xs font-medium bg-gray-100 text-gray-700 rounded hover:bg-gray-200 disabled:opacity-50"
                >
                  {running && !llmLoading ? <><Spinner className="h-3 w-3 inline mr-1" />Running...</> : 'Re-run'}
                </button>
                <button
                  onClick={() => setShowLlmModal(true)}
                  disabled={isRunning}
                  className="px-2.5 py-1 text-xs font-medium bg-indigo-100 text-indigo-700 rounded hover:bg-indigo-200 disabled:opacity-50"
                >
                  {llmLoading ? <><Spinner className="h-3 w-3 inline mr-1" />LLM running...</> : 'Re-run with LLM'}
                </button>
              </div>
            </div>
            <p className="text-sm text-gray-500 mt-1">
              {Object.values(report.layers).reduce((s, l) => s + l.tool_count, 0)} tools across {layers.length}{llmLoading ? '+1' : ''} layers — {totalChecks} checks total
            </p>
            {report.timestamp && (
              <p className="text-xs text-gray-400 mt-0.5">
                Last evaluated: {formatTimestamp(report.timestamp)}
              </p>
            )}
          </div>
          <div className="text-right">
            <div className={`text-4xl font-bold ${scoreColor(report.overall_score)}`}>
              {report.overall_score.toFixed(1)}
              <span className="text-lg text-gray-400">/100</span>
            </div>
            {llmLoading && (
              <span className="text-xs text-indigo-500">LLM score pending...</span>
            )}
            <span className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-bold ${
              report.gate_passed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
            }`}>
              Gate: {report.gate_passed ? 'PASSED' : 'FAILED'}
            </span>
            {!report.gate_passed && (() => {
              const gateLayers = ['protocol', 'security']
              const criticals: { layer: string; tool: string; msg: string }[] = []
              for (const lk of gateLayers) {
                const lr = report.layers[lk]
                if (!lr) continue
                for (const t of lr.tools) {
                  for (const c of t.checks) {
                    if (c.status === 'fail' && c.severity === 'critical') {
                      criticals.push({ layer: lk, tool: t.tool_name, msg: c.message })
                    }
                  }
                }
              }
              if (criticals.length === 0) return null
              const layerSet = new Set(criticals.map(c => c.layer))
              const layerNames = [...layerSet].map(l => LAYER_LABELS[l] || l).join(', ')
              return (
                <div className="mt-1.5 text-[11px] text-red-600 max-w-xs text-right">
                  {criticals.length} critical failure{criticals.length > 1 ? 's' : ''} in {layerNames}
                  <details className="mt-0.5">
                    <summary className="cursor-pointer text-red-500 hover:text-red-700">Show details</summary>
                    <ul className="mt-1 text-left text-[10px] text-red-500 space-y-0.5">
                      {criticals.map((c, i) => (
                        <li key={i} className="break-words">
                          <span className="font-mono text-red-600">{c.tool}</span>: {c.msg.length > 80 ? c.msg.slice(0, 80) + '...' : c.msg}
                        </li>
                      ))}
                    </ul>
                  </details>
                </div>
              )
            })()}
          </div>
        </div>

        {/* Layer Score Bars */}
        <div className="space-y-2">
          {layers.map(layer => (
            <div key={layer.key} className="flex items-center gap-3">
              <span className="text-sm text-gray-600 w-44 shrink-0">{LAYER_LABELS[layer.key] || layer.key}</span>
              <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${scoreBg(layer.score)}`} style={{ width: `${layer.score}%` }} />
              </div>
              <span className={`text-sm font-medium w-12 text-right ${scoreColor(layer.score)}`}>
                {layer.score.toFixed(1)}
              </span>
            </div>
          ))}
          {llmLoading && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-600 w-44 shrink-0">{LAYER_LABELS.llm}</span>
              <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full rounded-full bg-indigo-300 animate-pulse" style={{ width: '100%' }} />
              </div>
              <span className="text-sm text-indigo-400 w-12 text-right">...</span>
            </div>
          )}
        </div>
      </div>

      {/* Layer Cards */}
      {layers.map(layer => {
        const isExpanded = expandedLayers.has(layer.key)
        const allChecks = layer.tools.flatMap(t => t.checks)
        const failCount = allChecks.filter(c => c.status === 'fail').length
        const warnCount = allChecks.filter(c => c.status === 'warn').length
        const passCount = allChecks.filter(c => c.status === 'pass').length
        const skipCount = allChecks.filter(c => c.status === 'skip').length

        return (
          <div key={layer.key} className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <button
              onClick={() => toggleLayer(layer.key)}
              className="w-full text-left px-5 py-4 flex justify-between items-center hover:bg-gray-50"
            >
              <div className="flex items-center gap-3">
                <span className={`px-2.5 py-1 rounded text-sm font-bold ${scoreBadgeBg(layer.score)}`}>
                  {layer.score.toFixed(1)}
                </span>
                <div>
                  <span className="font-semibold text-gray-800">{LAYER_LABELS[layer.key] || layer.key}</span>
                  <span className="text-xs text-gray-500 ml-2">{layer.tool_count} tools</span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex gap-2 text-xs">
                  {passCount > 0 && <span className="text-green-600">{passCount} pass</span>}
                  {failCount > 0 && <span className="text-red-600">{failCount} fail</span>}
                  {warnCount > 0 && <span className="text-yellow-600">{warnCount} warn</span>}
                  {skipCount > 0 && <span className="text-gray-400">{skipCount} skip</span>}
                </div>
                <span className="text-gray-400 text-xs">{isExpanded ? '▼' : '▶'}</span>
              </div>
            </button>

            {isExpanded && (
              <div className="border-t border-gray-100 px-5 py-3">
                {layer.catalog_checks && layer.catalog_checks.length > 0 && (
                  <div className="mb-3 space-y-1">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Catalog Checks</p>
                    {layer.catalog_checks.map((c, i) => (
                      <CheckRow
                        key={i}
                        check={c}
                        checkKey={`${layer.key}:_catalog_:${c.check_id}`}
                        falsePositives={falsePositives}
                        onToggleFP={handleToggleFP}
                      />
                    ))}
                  </div>
                )}

                <div className="space-y-1">
                  {layer.tools.map((tool) => {
                    const toolKey = `${layer.key}:${tool.tool_name}`
                    const isToolExpanded = expandedTools.has(toolKey)
                    return (
                      <div key={toolKey} className="border border-gray-100 rounded">
                        <button
                          onClick={() => toggleTool(toolKey)}
                          className="w-full text-left px-3 py-2 flex justify-between items-center hover:bg-gray-50 text-sm"
                        >
                          <div className="flex items-center gap-2">
                            <span className={`w-5 h-5 flex items-center justify-center rounded text-xs font-bold ${
                              tool.passed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                            }`}>
                              {tool.passed ? '✓' : '✗'}
                            </span>
                            <span className="font-mono text-gray-800">{tool.tool_name}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <StatusCounts checks={tool.checks} />
                            <span className="text-gray-400 text-xs">{isToolExpanded ? '▼' : '▶'}</span>
                          </div>
                        </button>
                        {isToolExpanded && (
                          <div className="border-t border-gray-50 px-3 py-2 space-y-0.5">
                            {tool.checks.map((c, i) => (
                              <CheckRow
                                key={i}
                                check={c}
                                checkKey={`${layer.key}:${tool.tool_name}:${c.check_id}`}
                                falsePositives={falsePositives}
                                onToggleFP={handleToggleFP}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )
      })}

      {/* LLM Loading Placeholder Card */}
      {llmLoading && (
        <div className="bg-white border border-indigo-200 rounded-lg overflow-hidden">
          <div className="px-5 py-4 flex items-center gap-3">
            <Spinner className="h-5 w-5 text-indigo-500" />
            <div>
              <span className="font-semibold text-indigo-800">{LAYER_LABELS.llm}</span>
              <p className="text-xs text-indigo-500 mt-0.5">Running LLM checks — testing description clarity, tool selection, argument generation, disambiguation, and safety...</p>
            </div>
          </div>
        </div>
      )}

      {/* Per-LLM Results Tabs */}
      {perLlmResults && Object.keys(perLlmResults).length > 1 && (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100">
            <div className="flex gap-1">
              <button
                onClick={() => setActiveLlmTab('combined')}
                className={`px-3 py-1.5 text-xs font-medium rounded ${
                  activeLlmTab === 'combined' ? 'bg-indigo-100 text-indigo-700' : 'text-gray-500 hover:bg-gray-100'
                }`}
              >
                Combined
              </button>
              {Object.keys(perLlmResults).map(llmName => (
                <button
                  key={llmName}
                  onClick={() => setActiveLlmTab(llmName)}
                  className={`px-3 py-1.5 text-xs font-medium rounded ${
                    activeLlmTab === llmName ? 'bg-indigo-100 text-indigo-700' : 'text-gray-500 hover:bg-gray-100'
                  }`}
                >
                  {llmName}
                  {perLlmResults[llmName].error && <span className="ml-1 text-red-500">!</span>}
                </button>
              ))}
            </div>
          </div>
          {activeLlmTab !== 'combined' && perLlmResults[activeLlmTab] && (
            <div className="px-5 py-3">
              {perLlmResults[activeLlmTab].error ? (
                <div className="text-sm text-red-600">{perLlmResults[activeLlmTab].error}</div>
              ) : perLlmResults[activeLlmTab].layer ? (
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-sm text-gray-600 mb-2">
                    <span className="font-medium">{perLlmResults[activeLlmTab].metadata.llm_provider}</span>
                    <span className="text-gray-400">/</span>
                    <span>{perLlmResults[activeLlmTab].metadata.llm_model}</span>
                    <span className={`ml-auto font-bold ${scoreColor(perLlmResults[activeLlmTab].layer!.score)}`}>
                      {perLlmResults[activeLlmTab].layer!.score.toFixed(1)}
                    </span>
                  </div>
                  {perLlmResults[activeLlmTab].layer!.tools.map((tool) => {
                    const toolKey = `pllm:${activeLlmTab}:${tool.tool_name}`
                    const isToolExpanded = expandedTools.has(toolKey)
                    return (
                      <div key={toolKey} className="border border-gray-100 rounded">
                        <button
                          onClick={() => toggleTool(toolKey)}
                          className="w-full text-left px-3 py-2 flex justify-between items-center hover:bg-gray-50 text-sm"
                        >
                          <div className="flex items-center gap-2">
                            <span className={`w-5 h-5 flex items-center justify-center rounded text-xs font-bold ${
                              tool.passed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                            }`}>
                              {tool.passed ? '✓' : '✗'}
                            </span>
                            <span className="font-mono text-gray-800">{tool.tool_name}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <StatusCounts checks={tool.checks} />
                            <span className="text-gray-400 text-xs">{isToolExpanded ? '▼' : '▶'}</span>
                          </div>
                        </button>
                        {isToolExpanded && (
                          <div className="border-t border-gray-50 px-3 py-2 space-y-0.5">
                            {tool.checks.map((c, i) => (
                              <CheckRow
                                key={i}
                                check={c}
                                checkKey={`pllm:${activeLlmTab}:${tool.tool_name}:${c.check_id}`}
                                falsePositives={falsePositives}
                                onToggleFP={handleToggleFP}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              ) : null}
            </div>
          )}
        </div>
      )}

      {showLlmModal && (
        <LlmEvalModal
          configs={llmConfigs}
          selectedLlms={selectedLlms}
          onToggleLlm={toggleLlmSelection}
          groundTruthCount={groundTruthCount}
          groundTruthPromptCount={groundTruthPromptCount}
          onUploadGroundTruth={handleUploadGroundTruth}
          onDeleteGroundTruth={handleDeleteGroundTruth}
          onDownloadTemplate={handleDownloadTemplate}
          onRun={() => { setShowLlmModal(false); runEvaluation(true) }}
          onClose={() => setShowLlmModal(false)}
          loading={isRunning}
        />
      )}
    </div>
  )
}

interface CheckRowProps {
  check: FullCheckResult
  checkKey: string
  falsePositives: Record<string, string>
  onToggleFP: (key: string, justification: string | null) => void
}

function CheckRow({ check, checkKey, falsePositives, onToggleFP }: CheckRowProps) {
  const [editing, setEditing] = useState(false)
  const [justification, setJustification] = useState('')
  const isFP = checkKey in falsePositives
  const { icon, color } = statusIcon(check.status)
  const hasDetails = check.details && (check.details.location || check.details.suggestion)
  const showDetails = check.status === 'fail' || check.status === 'warn'
  const canMarkFP = check.status === 'fail' || check.status === 'warn'

  function handleMarkFP() {
    if (isFP) {
      onToggleFP(checkKey, null)
    } else {
      setJustification('')
      setEditing(true)
    }
  }

  function handleSaveFP() {
    if (justification.trim()) {
      onToggleFP(checkKey, justification.trim())
      setEditing(false)
    }
  }

  return (
    <div className={`py-1 ${isFP ? 'opacity-60' : ''}`}>
      <div className="flex items-start gap-2 text-xs">
        <span className={`font-bold ${color} w-3 shrink-0 text-center`}>{icon}</span>
        <span className={`text-gray-700 flex-1 ${isFP ? 'line-through' : ''}`}>{check.message}</span>
        {check.details?.scenario_source === 'user_provided' && (
          <span className="px-1.5 py-0 rounded text-[10px] font-medium bg-teal-100 text-teal-700 shrink-0" title="Ground truth scenario">
            GT
          </span>
        )}
        {isFP && (
          <span className="px-1.5 py-0 rounded text-[10px] font-medium bg-purple-100 text-purple-700 shrink-0">
            FP
          </span>
        )}
        {check.severity && check.severity !== 'info' && (
          <span className={`px-1.5 py-0 rounded text-[10px] font-medium ${severityBadge(check.severity)}`}>
            {check.severity}
          </span>
        )}
        {canMarkFP && (
          <button
            onClick={handleMarkFP}
            title={isFP ? 'Remove false positive' : 'Mark as false positive'}
            className={`px-1.5 py-0 rounded text-[10px] font-medium shrink-0 ${
              isFP
                ? 'bg-purple-100 text-purple-700 hover:bg-purple-200'
                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
            }`}
          >
            {isFP ? 'Undo FP' : 'FP'}
          </button>
        )}
      </div>
      {editing && (
        <div className="ml-5 mt-1.5 flex items-center gap-2">
          <input
            type="text"
            value={justification}
            onChange={e => setJustification(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSaveFP()}
            placeholder="Justification for marking as false positive..."
            className="flex-1 px-2 py-1 text-xs border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-purple-400"
            autoFocus
          />
          <button
            onClick={handleSaveFP}
            disabled={!justification.trim()}
            className="px-2 py-1 text-xs bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
          >
            Save
          </button>
          <button
            onClick={() => setEditing(false)}
            className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200"
          >
            Cancel
          </button>
        </div>
      )}
      {isFP && !editing && (
        <div className="ml-5 mt-0.5 text-[11px] text-purple-600 italic">
          FP: {falsePositives[checkKey]}
        </div>
      )}
      {showDetails && hasDetails && !isFP && (
        <div className="ml-5 mt-1 mb-1 pl-3 border-l-2 border-gray-200 space-y-0.5">
          {check.details!.location && (
            <div className="text-[11px] text-gray-500">
              <span className="font-medium text-gray-600">Where: </span>
              <code className="bg-gray-100 px-1 py-0.5 rounded text-red-700 font-mono">{String(check.details!.location)}</code>
              {check.details!.current_value !== undefined && check.details!.current_value !== null && (
                <span className="ml-1.5">
                  = <code className="bg-gray-100 px-1 py-0.5 rounded text-gray-700 font-mono">{String(check.details!.current_value)}</code>
                </span>
              )}
            </div>
          )}
          {check.details!.suggestion && (
            <div className="text-[11px] text-emerald-700">
              <span className="font-medium">Fix: </span>
              {String(check.details!.suggestion)}
            </div>
          )}
          {check.details!.suggested_description && (
            <div className="text-[11px] text-blue-700 mt-1 bg-blue-50 rounded px-2 py-1.5 border border-blue-100">
              <span className="font-medium">Suggested description: </span>
              <span className="italic">{String(check.details!.suggested_description)}</span>
              <button
                onClick={() => navigator.clipboard.writeText(String(check.details!.suggested_description))}
                className="ml-2 text-[10px] text-blue-500 hover:text-blue-700 underline"
              >
                Copy
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function StatusCounts({ checks }: { checks: FullCheckResult[] }) {
  const counts = { pass: 0, fail: 0, warn: 0, skip: 0 }
  for (const c of checks) {
    if (c.status in counts) counts[c.status as keyof typeof counts]++
  }
  return (
    <div className="flex gap-1.5 text-[10px]">
      {counts.pass > 0 && <span className="text-green-600">{counts.pass}✓</span>}
      {counts.fail > 0 && <span className="text-red-600">{counts.fail}✗</span>}
      {counts.warn > 0 && <span className="text-yellow-600">{counts.warn}!</span>}
      {counts.skip > 0 && <span className="text-gray-400">{counts.skip}—</span>}
    </div>
  )
}


