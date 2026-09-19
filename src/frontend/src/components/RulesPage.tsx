import { useState, useEffect, useRef } from 'react'
import type { RuleInfo } from '../api'
import * as api from '../api'

interface Props {
  onToast: (message: string, type: 'success' | 'error' | 'info') => void
}

const LAYER_LABELS: Record<string, string> = {
  protocol: 'Protocol Compliance',
  quality: 'Tool Quality',
  security: 'Security Analysis',
  llm: 'LLM Evaluation',
  agent: 'Agent Evaluation',
}

const LAYER_ORDER = ['protocol', 'quality', 'security', 'llm', 'agent']

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info']

function severityBadge(severity: string): string {
  switch (severity) {
    case 'critical': return 'bg-red-100 text-red-700'
    case 'high': return 'bg-orange-100 text-orange-700'
    case 'medium': return 'bg-yellow-100 text-yellow-700'
    case 'low': return 'bg-blue-100 text-blue-700'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function ParamEditor({
  paramKey,
  schema,
  value,
  onChange,
}: {
  paramKey: string
  schema: api.RuleParamSchema
  value: unknown
  onChange: (key: string, val: unknown) => void
}) {
  if (schema.type === 'int' || schema.type === 'float') {
    return (
      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-600 min-w-[120px]">{paramKey}</label>
        <input
          type="number"
          step={schema.type === 'float' ? '0.1' : '1'}
          value={String(value ?? schema.default ?? '')}
          onChange={(e) => {
            const v = schema.type === 'float' ? parseFloat(e.target.value) : parseInt(e.target.value, 10)
            if (!isNaN(v)) onChange(paramKey, v)
          }}
          className="w-24 px-2 py-1 text-sm border rounded"
        />
        <span className="text-xs text-gray-400">(default: {String(schema.default)})</span>
      </div>
    )
  }

  if (schema.type === 'bool') {
    return (
      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-600 min-w-[120px]">{paramKey}</label>
        <input
          type="checkbox"
          checked={Boolean(value ?? schema.default)}
          onChange={(e) => onChange(paramKey, e.target.checked)}
          className="rounded"
        />
      </div>
    )
  }

  if (schema.type === 'list') {
    const items = Array.isArray(value) ? value as string[] : (Array.isArray(schema.default) ? schema.default as string[] : [])
    return (
      <div>
        <label className="text-xs text-gray-600">{paramKey}</label>
        <p className="text-xs text-gray-400 mb-1">{schema.description}</p>
        <div className="text-xs text-gray-400 mb-1">{items.length} items configured</div>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-gray-600 min-w-[120px]">{paramKey}</label>
      <input
        type="text"
        value={String(value ?? schema.default ?? '')}
        onChange={(e) => onChange(paramKey, e.target.value)}
        className="flex-1 px-2 py-1 text-sm border rounded"
      />
    </div>
  )
}

export default function RulesPage({ onToast }: Props) {
  const [rules, setRules] = useState<RuleInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedRules, setExpandedRules] = useState<Set<string>>(new Set())
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function loadRules() {
    try {
      setLoading(true)
      const data = await api.getRules()
      setRules(data.rules)
    } catch (e) {
      onToast(`Failed to load rules: ${e}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadRules() }, [])

  async function handleToggle(ruleId: string, enabled: boolean) {
    try {
      await api.updateRule(ruleId, { enabled })
      setRules(prev => prev.map(r => r.rule_id === ruleId ? { ...r, enabled } : r))
    } catch (e) {
      onToast(`Failed to update rule: ${e}`, 'error')
    }
  }

  async function handleSeverityChange(ruleId: string, severity: string) {
    try {
      const severityOverride = severity === '' ? null : severity
      await api.updateRule(ruleId, { severity_override: severityOverride })
      setRules(prev => prev.map(r => r.rule_id === ruleId ? { ...r, severity_override: severityOverride } : r))
    } catch (e) {
      onToast(`Failed to update severity: ${e}`, 'error')
    }
  }

  async function handleParamChange(ruleId: string, key: string, value: unknown) {
    const rule = rules.find(r => r.rule_id === ruleId)
    if (!rule) return
    const newParams = { ...rule.params, [key]: value }
    try {
      await api.updateRule(ruleId, { params: newParams })
      setRules(prev => prev.map(r => r.rule_id === ruleId ? { ...r, params: newParams } : r))
    } catch (e) {
      onToast(`Failed to update params: ${e}`, 'error')
    }
  }

  async function handleReset() {
    if (!confirm('Reset all rules to defaults? This will clear all customizations.')) return
    try {
      await api.resetRules()
      await loadRules()
      onToast('Rules reset to defaults', 'success')
    } catch (e) {
      onToast(`Failed to reset: ${e}`, 'error')
    }
  }

  async function handleExport() {
    try {
      const data = await api.exportRules()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'mcp-lens-rules.json'
      a.click()
      URL.revokeObjectURL(url)
      onToast('Rules exported', 'success')
    } catch (e) {
      onToast(`Export failed: ${e}`, 'error')
    }
  }

  function handleImportClick() {
    fileInputRef.current?.click()
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const result = await api.importRules(data)
      await loadRules()
      let msg = `Imported ${result.imported_count} rules`
      if (result.warnings.length > 0) {
        msg += ` (${result.warnings.length} warnings)`
      }
      onToast(msg, 'success')
    } catch (e) {
      onToast(`Import failed: ${e}`, 'error')
    }
    e.target.value = ''
  }

  function toggleExpand(ruleId: string) {
    setExpandedRules(prev => {
      const next = new Set(prev)
      if (next.has(ruleId)) next.delete(ruleId)
      else next.add(ruleId)
      return next
    })
  }

  const rulesByLayer: Record<string, RuleInfo[]> = {}
  for (const rule of rules) {
    if (!rulesByLayer[rule.layer]) rulesByLayer[rule.layer] = []
    rulesByLayer[rule.layer].push(rule)
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <svg className="animate-spin h-6 w-6 text-gray-400" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Rules Configuration</h2>
          <p className="text-sm text-gray-500 mt-1">{rules.length} rules across {Object.keys(rulesByLayer).length} layers</p>
        </div>
        <div className="flex gap-2">
          <input ref={fileInputRef} type="file" accept=".json" className="hidden" onChange={handleImportFile} />
          <button
            onClick={handleImportClick}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Import
          </button>
          <button
            onClick={handleExport}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Export
          </button>
          <button
            onClick={handleReset}
            className="px-3 py-1.5 text-sm bg-red-50 text-red-700 border border-red-200 rounded-md hover:bg-red-100 transition-colors"
          >
            Reset to Defaults
          </button>
        </div>
      </div>

      {LAYER_ORDER.map(layer => {
        const layerRules = rulesByLayer[layer]
        if (!layerRules?.length) return null
        const enabledCount = layerRules.filter(r => r.enabled).length

        return (
          <div key={layer} className="mb-6">
            <div className="flex items-center gap-2 mb-3">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
                {LAYER_LABELS[layer] || layer}
              </h3>
              <span className="text-xs text-gray-400">
                {enabledCount}/{layerRules.length} enabled
              </span>
            </div>

            <div className="border rounded-lg divide-y">
              {layerRules.map(rule => {
                const hasParams = Object.keys(rule.params_schema).length > 0
                const isExpanded = expandedRules.has(rule.rule_id)
                const effectiveSeverity = rule.severity_override || rule.default_severity

                return (
                  <div key={rule.rule_id} className={`${rule.enabled ? '' : 'opacity-60'}`}>
                    <div className="flex items-center gap-3 px-4 py-3">
                      <button
                        onClick={() => handleToggle(rule.rule_id, !rule.enabled)}
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                          rule.enabled ? 'bg-blue-600' : 'bg-gray-300'
                        }`}
                      >
                        <span
                          className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                            rule.enabled ? 'translate-x-[18px]' : 'translate-x-[2px]'
                          }`}
                        />
                      </button>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <code className="text-sm font-mono text-gray-800">{rule.rule_id}</code>
                          {hasParams && (
                            <button
                              onClick={() => toggleExpand(rule.rule_id)}
                              className="text-xs text-blue-600 hover:text-blue-800"
                            >
                              {isExpanded ? 'Hide params' : 'Show params'}
                            </button>
                          )}
                        </div>
                        <p className="text-xs text-gray-500 mt-0.5">{rule.description}</p>
                      </div>

                      <select
                        value={effectiveSeverity}
                        onChange={(e) => handleSeverityChange(rule.rule_id, e.target.value)}
                        className={`text-xs font-medium px-2 py-1 rounded-full border-0 cursor-pointer ${severityBadge(effectiveSeverity)}`}
                      >
                        {SEVERITIES.map(s => (
                          <option key={s} value={s}>
                            {s.toUpperCase()}{s === rule.default_severity ? ' (default)' : ''}
                          </option>
                        ))}
                      </select>
                    </div>

                    {isExpanded && hasParams && (
                      <div className="px-4 pb-3 pt-1 bg-gray-50 border-t border-gray-100">
                        <div className="space-y-2">
                          {Object.entries(rule.params_schema).map(([key, schema]) => (
                            <ParamEditor
                              key={key}
                              paramKey={key}
                              schema={schema}
                              value={rule.params[key]}
                              onChange={(k, v) => handleParamChange(rule.rule_id, k, v)}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
