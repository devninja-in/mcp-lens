import { useState } from 'react'

export interface DownloadOption {
  key: string
  label: string
  defaultChecked?: boolean
}

interface Props {
  title: string
  options: DownloadOption[]
  onDownload: (selected: Set<string>, format: string) => void
  onClose: () => void
}

const FORMATS = [
  { key: 'json', label: 'JSON' },
  { key: 'yaml', label: 'YAML' },
  { key: 'pdf', label: 'PDF' },
] as const

export default function DownloadModal({ title, options, onDownload, onClose }: Props) {
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(options.filter(o => o.defaultChecked !== false).map(o => o.key))
  )
  const [format, setFormat] = useState<string>('json')

  function toggle(key: string) {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  function selectAll() {
    setSelected(new Set(options.map(o => o.key)))
  }

  function selectNone() {
    setSelected(new Set())
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
        </div>

        <div className="px-5 py-3 space-y-4">
          {/* Format selector */}
          <div>
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Format</span>
            <div className="flex gap-1.5 mt-2">
              {FORMATS.map(f => (
                <button
                  key={f.key}
                  onClick={() => setFormat(f.key)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                    format === f.key
                      ? 'bg-blue-100 border-blue-300 text-blue-700'
                      : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >{f.label}</button>
              ))}
            </div>
          </div>

          {/* Section checkboxes */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Include</span>
              <div className="flex gap-2 text-[10px]">
                <button onClick={selectAll} className="text-blue-600 hover:underline">All</button>
                <button onClick={selectNone} className="text-blue-600 hover:underline">None</button>
              </div>
            </div>
            <div className="space-y-1.5">
              {options.map(opt => (
                <label key={opt.key} className="flex items-center gap-2.5 py-1 cursor-pointer hover:bg-gray-50 rounded px-1 -mx-1">
                  <input
                    type="checkbox"
                    checked={selected.has(opt.key)}
                    onChange={() => toggle(opt.key)}
                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-3.5 w-3.5"
                  />
                  <span className="text-sm text-gray-700">{opt.label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="px-5 py-3 border-t border-gray-100 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 rounded hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={() => onDownload(selected, format)}
            disabled={selected.size === 0}
            className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            Download
          </button>
        </div>
      </div>
    </div>
  )
}
