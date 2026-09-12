import { useRef } from 'react'
import type { LlmConfigInfo } from '../api'

interface Props {
  configs: Record<string, LlmConfigInfo>
  selectedLlms: string[]
  onToggleLlm: (name: string) => void
  groundTruthCount: number | null
  groundTruthPromptCount: number
  onUploadGroundTruth: (file: File) => void
  onDeleteGroundTruth: () => void
  onDownloadTemplate: () => void
  onRun: () => void
  onClose: () => void
  loading: boolean
  title?: string
  runLabel?: string
}

export default function LlmEvalModal({
  configs, selectedLlms, onToggleLlm,
  groundTruthCount, groundTruthPromptCount,
  onUploadGroundTruth, onDeleteGroundTruth, onDownloadTemplate,
  onRun, onClose, loading,
  title = 'LLM Evaluation Settings',
  runLabel = 'Run',
}: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const configEntries = Object.entries(configs)
  const hasConfigs = configEntries.length > 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
        </div>

        <div className="px-5 py-4 space-y-5">
          {/* LLM Selection */}
          <div>
            <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Select LLMs</div>
            {!hasConfigs ? (
              <p className="text-xs text-gray-400">No LLM configurations found. Set <code className="bg-gray-100 px-1 rounded">EVAL_LLM_PROVIDER</code> in .env or create llm.json.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {configEntries.map(([name, cfg]) => {
                  const isSelected = selectedLlms.includes(name)
                  return (
                    <button
                      key={name}
                      onClick={() => onToggleLlm(name)}
                      title={`${cfg.provider} / ${cfg.model}`}
                      className={`px-2.5 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                        isSelected
                          ? 'bg-indigo-100 border-indigo-300 text-indigo-700'
                          : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                      }`}
                    >
                      {name}
                      {!cfg.has_credentials && <span className="ml-1 text-amber-500" title="Missing credentials">!</span>}
                    </button>
                  )
                })}
              </div>
            )}
            {hasConfigs && selectedLlms.length === 0 && (
              <p className="text-[11px] text-gray-400 mt-1.5">No LLMs selected — will use default configuration</p>
            )}
          </div>

          {/* Ground Truth */}
          <div>
            <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Ground Truth</div>
            <div className="flex items-center gap-2 flex-wrap">
              {groundTruthCount !== null ? (
                <>
                  <span className="text-xs text-gray-700">
                    <span className="font-medium text-green-700">{groundTruthCount}</span> test cases
                    {groundTruthPromptCount > 0 && <span className="text-gray-400 ml-1">({groundTruthPromptCount} prompts)</span>}
                  </span>
                  <button
                    onClick={onDeleteGroundTruth}
                    className="px-2 py-0.5 text-[10px] font-medium text-red-600 bg-red-50 rounded hover:bg-red-100"
                  >Delete</button>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="px-2 py-0.5 text-[10px] font-medium text-blue-600 bg-blue-50 rounded hover:bg-blue-100"
                  >Replace</button>
                </>
              ) : (
                <>
                  <span className="text-xs text-gray-400">None uploaded</span>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="px-2 py-0.5 text-[10px] font-medium text-blue-600 bg-blue-50 rounded hover:bg-blue-100"
                  >Upload YAML</button>
                  <button
                    onClick={onDownloadTemplate}
                    className="px-2 py-0.5 text-[10px] font-medium text-gray-500 bg-gray-50 rounded hover:bg-gray-100"
                  >Download Template</button>
                </>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".yaml,.yml"
              className="hidden"
              onChange={e => {
                const file = e.target.files?.[0]
                if (file) {
                  onUploadGroundTruth(file)
                  e.target.value = ''
                }
              }}
            />
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-100 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 rounded hover:bg-gray-200"
          >Cancel</button>
          <button
            onClick={onRun}
            disabled={loading || !hasConfigs}
            className="px-4 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded hover:bg-indigo-700 disabled:opacity-50"
          >{loading ? 'Running...' : runLabel}</button>
        </div>
      </div>
    </div>
  )
}
