import { useState, useEffect, useRef } from 'react'
import type { McpServerConfig } from '../types'
import * as api from '../api'
import { downloadComparisonJson, downloadComparisonPdf, downloadComparisonYaml, downloadComparisonMd } from '../utils/download'
import type {
  ServerComparisonReport,
  CapabilitiesComparison,
  ToolInventoryDiff,
  CategoryCoverage,
  EvalScoreComparison,
  SchemaDiff,
} from '../api'

interface Props {
  onToast: (message: string, type: 'success' | 'error' | 'info') => void
}

function Spinner({ message }: { message?: string }) {
  return (
    <div className="text-center py-16">
      <svg className="animate-spin h-8 w-8 mx-auto text-indigo-500" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      {message && <p className="text-sm text-gray-500 mt-3">{message}</p>}
    </div>
  )
}

function SearchableSelect({
  value,
  onChange,
  options,
  placeholder = 'Select server...',
}: {
  value: string
  onChange: (val: string) => void
  options: string[]
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const filtered = search
    ? options.filter(o => o.toLowerCase().includes(search.toLowerCase()))
    : options

  return (
    <div ref={ref} className="relative">
      <input
        ref={inputRef}
        type="text"
        value={open ? search : value}
        placeholder={placeholder}
        onChange={e => { setSearch(e.target.value); if (!open) setOpen(true) }}
        onFocus={() => { setOpen(true); setSearch('') }}
        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
      />
      {value && !open && (
        <button
          onClick={() => { onChange(''); setSearch(''); inputRef.current?.focus() }}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs"
        >x</button>
      )}
      {open && (
        <div className="absolute z-20 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="px-3 py-2 text-sm text-gray-400">No matches</div>
          ) : (
            filtered.map(name => (
              <button
                key={name}
                onClick={() => { onChange(name); setOpen(false); setSearch('') }}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-indigo-50 ${
                  name === value ? 'bg-indigo-50 text-indigo-700 font-medium' : 'text-gray-700'
                }`}
              >{name}</button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

function CapabilitiesSection({ data, serverA, serverB }: { data: CapabilitiesComparison | null; serverA: string; serverB: string }) {
  if (!data) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <h3 className="text-base font-semibold text-gray-800 mb-2">Protocol Capabilities</h3>
        <p className="text-sm text-gray-400">Could not connect to one or both servers to retrieve capabilities.</p>
      </div>
    )
  }

  const infoA = data.server_a.serverInfo as Record<string, string>
  const infoB = data.server_b.serverInfo as Record<string, string>

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <h3 className="text-base font-semibold text-gray-800 mb-4">Protocol Capabilities</h3>
      <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
        <div className="bg-gray-50 rounded-lg p-3">
          <div className="font-medium text-gray-700">{serverA}</div>
          <div className="text-xs text-gray-400 mt-1">
            {infoA.name && <span>{infoA.name}</span>}
            {infoA.version && <span> v{infoA.version}</span>}
          </div>
        </div>
        <div className="bg-gray-50 rounded-lg p-3">
          <div className="font-medium text-gray-700">{serverB}</div>
          <div className="text-xs text-gray-400 mt-1">
            {infoB.name && <span>{infoB.name}</span>}
            {infoB.version && <span> v{infoB.version}</span>}
          </div>
        </div>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="text-left py-2 text-xs font-medium text-gray-500 uppercase">Capability</th>
            <th className="text-center py-2 text-xs font-medium text-gray-500 uppercase">{serverA}</th>
            <th className="text-center py-2 text-xs font-medium text-gray-500 uppercase">{serverB}</th>
          </tr>
        </thead>
        <tbody>
          {data.capability_matrix.map(row => (
            <tr key={row.capability} className="border-b border-gray-100 last:border-0">
              <td className="py-2 font-mono text-xs text-gray-700">{row.capability}</td>
              <td className="py-2 text-center">
                {row.server_a
                  ? <span className="text-green-600 font-bold">Yes</span>
                  : <span className="text-gray-300">No</span>}
              </td>
              <td className="py-2 text-center">
                {row.server_b
                  ? <span className="text-green-600 font-bold">Yes</span>
                  : <span className="text-gray-300">No</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ToolInventorySection({ data, serverA, serverB }: { data: ToolInventoryDiff; serverA: string; serverB: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <h3 className="text-base font-semibold text-gray-800 mb-1">Tool Inventory</h3>
      <p className="text-sm text-gray-400 mb-4">
        {serverA}: {data.count_a} tools | {serverB}: {data.count_b} tools | {data.common.length} shared
      </p>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <div className="text-xs font-medium text-gray-500 uppercase mb-2">
            Only in {serverA} ({data.only_a.length})
          </div>
          {data.only_a.length === 0 ? (
            <p className="text-xs text-gray-300 italic">None</p>
          ) : (
            <ul className="space-y-1">
              {data.only_a.map(name => (
                <li key={name} className="text-xs font-mono bg-blue-50 text-blue-700 px-2 py-1 rounded">{name}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="text-xs font-medium text-gray-500 uppercase mb-2">
            Only in {serverB} ({data.only_b.length})
          </div>
          {data.only_b.length === 0 ? (
            <p className="text-xs text-gray-300 italic">None</p>
          ) : (
            <ul className="space-y-1">
              {data.only_b.map(name => (
                <li key={name} className="text-xs font-mono bg-purple-50 text-purple-700 px-2 py-1 rounded">{name}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="text-xs font-medium text-gray-500 uppercase mb-2">
            Common ({data.common.length})
          </div>
          {data.common.length === 0 ? (
            <p className="text-xs text-gray-300 italic">None</p>
          ) : (
            <ul className="space-y-1">
              {data.common.map(name => (
                <li key={name} className="text-xs font-mono bg-green-50 text-green-700 px-2 py-1 rounded">{name}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

function CategoriesSection({ data, serverA, serverB }: { data: CategoryCoverage[]; serverA: string; serverB: string }) {
  if (data.length === 0) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <h3 className="text-base font-semibold text-gray-800 mb-2">Capability Categories</h3>
        <p className="text-sm text-gray-400">LLM categorization not available.</p>
      </div>
    )
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <h3 className="text-base font-semibold text-gray-800 mb-4">Capability Categories</h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="text-left py-2 text-xs font-medium text-gray-500 uppercase">Category</th>
            <th className="text-left py-2 text-xs font-medium text-gray-500 uppercase">{serverA}</th>
            <th className="text-left py-2 text-xs font-medium text-gray-500 uppercase">{serverB}</th>
          </tr>
        </thead>
        <tbody>
          {data.map(cat => {
            const hasBoth = cat.server_a_count > 0 && cat.server_b_count > 0
            const bgClass = hasBoth ? '' : 'bg-amber-50'
            return (
              <tr key={cat.category} className={`border-b border-gray-100 last:border-0 ${bgClass}`}>
                <td className="py-2 font-medium text-gray-700">{cat.category}</td>
                <td className="py-2">
                  {cat.server_a_count > 0 ? (
                    <div>
                      <span className="text-xs text-gray-500">{cat.server_a_count} tools: </span>
                      <span className="text-xs font-mono text-gray-600">{cat.server_a_tools.join(', ')}</span>
                    </div>
                  ) : (
                    <span className="text-xs text-gray-300">--</span>
                  )}
                </td>
                <td className="py-2">
                  {cat.server_b_count > 0 ? (
                    <div>
                      <span className="text-xs text-gray-500">{cat.server_b_count} tools: </span>
                      <span className="text-xs font-mono text-gray-600">{cat.server_b_tools.join(', ')}</span>
                    </div>
                  ) : (
                    <span className="text-xs text-gray-300">--</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ScoreBar({ score, label }: { score: number | null; label: string }) {
  if (score === null || score === undefined) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-400 w-16">{label}</span>
        <span className="text-xs text-gray-300">No data</span>
      </div>
    )
  }
  const color = score >= 80 ? 'bg-green-500' : score >= 60 ? 'bg-yellow-500' : 'bg-red-500'
  const textColor = score >= 80 ? 'text-green-700' : score >= 60 ? 'text-yellow-700' : 'text-red-700'
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-500 w-16 shrink-0">{label}</span>
      <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${Math.min(score, 100)}%` }} />
      </div>
      <span className={`text-xs font-bold w-10 text-right ${textColor}`}>{score.toFixed(0)}</span>
    </div>
  )
}

function EvalScoresSection({ data, serverA, serverB }: { data: EvalScoreComparison; serverA: string; serverB: string }) {
  const layers = Object.entries(data.layers)

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <h3 className="text-base font-semibold text-gray-800 mb-4">Evaluation Scores</h3>
      <div className="grid grid-cols-2 gap-6">
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-gray-700">{serverA}</span>
            {data.server_a_score !== null && (
              <span className="text-lg font-bold text-gray-800">{data.server_a_score.toFixed(1)}</span>
            )}
          </div>
          <div className="space-y-2">
            {layers.map(([layer, scores]) => (
              <ScoreBar key={layer} score={scores.server_a} label={layer} />
            ))}
          </div>
        </div>
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-gray-700">{serverB}</span>
            {data.server_b_score !== null && (
              <span className="text-lg font-bold text-gray-800">{data.server_b_score.toFixed(1)}</span>
            )}
          </div>
          <div className="space-y-2">
            {layers.map(([layer, scores]) => (
              <ScoreBar key={layer} score={scores.server_b} label={layer} />
            ))}
          </div>
        </div>
      </div>
      {data.server_a_score === null && data.server_b_score === null && (
        <p className="text-sm text-gray-400 mt-4">Run evaluations on both servers first to see score comparison.</p>
      )}
    </div>
  )
}

function SchemaDiffsSection({ data }: { data: SchemaDiff[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  if (data.length === 0) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <h3 className="text-base font-semibold text-gray-800 mb-2">Schema Diffs</h3>
        <p className="text-sm text-gray-400">No common tools to compare schemas.</p>
      </div>
    )
  }

  const identical = data.filter(d => d.identical).length
  const different = data.length - identical

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <h3 className="text-base font-semibold text-gray-800 mb-1">Schema Diffs</h3>
      <p className="text-sm text-gray-400 mb-4">
        {data.length} common tools: {identical} identical, {different} with differences
      </p>
      <div className="space-y-2">
        {data.map(diff => {
          const isExpanded = expanded.has(diff.tool_name)
          return (
            <div key={diff.tool_name} className="border border-gray-100 rounded-lg">
              <button
                onClick={() => setExpanded(prev => {
                  const next = new Set(prev)
                  next.has(diff.tool_name) ? next.delete(diff.tool_name) : next.add(diff.tool_name)
                  return next
                })}
                className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-gray-50"
              >
                <span className="text-sm font-mono text-gray-700">{diff.tool_name}</span>
                <div className="flex items-center gap-2">
                  {diff.identical ? (
                    <span className="px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded-full">Identical</span>
                  ) : (
                    <span className="px-2 py-0.5 text-xs bg-amber-100 text-amber-700 rounded-full">
                      {diff.differences.length} difference{diff.differences.length !== 1 ? 's' : ''}
                    </span>
                  )}
                  <span className="text-xs text-gray-400">{isExpanded ? '▲' : '▼'}</span>
                </div>
              </button>
              {isExpanded && !diff.identical && (
                <div className="px-4 pb-3">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-gray-100">
                        <th className="text-left py-1.5 text-gray-500 font-medium">Path</th>
                        <th className="text-left py-1.5 text-gray-500 font-medium">Server A</th>
                        <th className="text-left py-1.5 text-gray-500 font-medium">Server B</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diff.differences.map((d, i) => (
                        <tr key={i} className="border-b border-gray-50 last:border-0">
                          <td className="py-1.5 font-mono text-gray-600">{d.path}</td>
                          <td className="py-1.5 text-gray-600">
                            {d.server_a === null ? <span className="text-red-400 italic">missing</span> : JSON.stringify(d.server_a)}
                          </td>
                          <td className="py-1.5 text-gray-600">
                            {d.server_b === null ? <span className="text-red-400 italic">missing</span> : JSON.stringify(d.server_b)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ExportDropdown({ report }: { report: ServerComparisonReport }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="px-3 py-1.5 text-xs font-medium bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
      >
        Export
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-32 bg-white border border-gray-200 rounded-lg shadow-lg z-20">
          <button
            onClick={() => { downloadComparisonPdf(report); setOpen(false) }}
            className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >PDF</button>
          <button
            onClick={() => { downloadComparisonJson(report); setOpen(false) }}
            className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >JSON</button>
          <button
            onClick={() => { downloadComparisonYaml(report); setOpen(false) }}
            className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >YAML</button>
          <button
            onClick={() => { downloadComparisonMd(report); setOpen(false) }}
            className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >Markdown</button>
        </div>
      )}
    </div>
  )
}

export default function ComparePage({ onToast }: Props) {
  const [servers, setServers] = useState<Record<string, McpServerConfig>>({})
  const [serverA, setServerA] = useState('')
  const [serverB, setServerB] = useState('')
  const [report, setReport] = useState<ServerComparisonReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(false)
  const [noReport, setNoReport] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listServers().then(setServers).catch(() => {})
  }, [])

  const serverNames = Object.keys(servers).sort()

  async function handleCompare() {
    if (!serverA || !serverB) {
      onToast('Select two servers to compare', 'error')
      return
    }
    setChecking(true)
    setError(null)
    setReport(null)
    setNoReport(false)
    try {
      const result = await api.checkComparison(serverA, serverB)
      if (result.exists && result.report) {
        setReport(result.report)
      } else {
        setNoReport(true)
      }
    } catch (e) {
      setError(`${e}`)
    } finally {
      setChecking(false)
    }
  }

  async function handleRun() {
    setLoading(true)
    setError(null)
    setNoReport(false)
    try {
      const result = await api.runServerComparison(serverA, serverB)
      setReport(result)
      onToast('Comparison complete', 'success')
    } catch (e) {
      setError(`${e}`)
      onToast(`Comparison failed: ${e}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Compare Two Servers</h2>
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-500 mb-1">Server A</label>
            <SearchableSelect
              value={serverA}
              onChange={val => { setServerA(val); setReport(null); setNoReport(false) }}
              options={serverNames.filter(s => s !== serverB)}
              placeholder="Search servers..."
            />
          </div>
          <span className="text-gray-400 font-bold pb-2">vs</span>
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-500 mb-1">Server B</label>
            <SearchableSelect
              value={serverB}
              onChange={val => { setServerB(val); setReport(null); setNoReport(false) }}
              options={serverNames.filter(s => s !== serverA)}
              placeholder="Search servers..."
            />
          </div>
          <button
            onClick={handleCompare}
            disabled={!serverA || !serverB || checking}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {checking ? 'Checking...' : 'Compare'}
          </button>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {noReport && !loading && (
        <div className="text-center py-12">
          <p className="text-sm text-gray-500 mb-4">No stored comparison found for this pair.</p>
          <button
            onClick={handleRun}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"
          >
            Run Comparison
          </button>
        </div>
      )}

      {loading && <Spinner message="Running comparison (LLM categorization may take a moment)..." />}

      {report && !loading && (
        <>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-800">
                {report.server_a} vs {report.server_b}
              </h3>
              <p className="text-xs text-gray-400">
                Generated {new Date(report.timestamp).toLocaleString()}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <ExportDropdown report={report} />
              <button
                onClick={handleRun}
                className="px-3 py-1.5 text-xs font-medium bg-indigo-100 text-indigo-700 rounded hover:bg-indigo-200"
              >
                Re-run Comparison
              </button>
            </div>
          </div>

          <CapabilitiesSection data={report.capabilities} serverA={report.server_a} serverB={report.server_b} />
          <ToolInventorySection data={report.tool_inventory} serverA={report.server_a} serverB={report.server_b} />
          <CategoriesSection data={report.categories} serverA={report.server_a} serverB={report.server_b} />
          <EvalScoresSection data={report.eval_scores} serverA={report.server_a} serverB={report.server_b} />
          <SchemaDiffsSection data={report.schema_diffs} />
        </>
      )}
    </div>
  )
}
