import { jsPDF } from 'jspdf'
import autoTable from 'jspdf-autotable'
import { dump as yamlDump } from 'js-yaml'
import type { FullEvalReport, ToolInfo } from '../types'

export function downloadJson(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const LAYER_LABELS: Record<string, string> = {
  protocol: 'Protocol Compliance',
  quality: 'Tool Quality',
  security: 'Security Analysis',
  llm: 'LLM-Assisted Evaluation',
}

const LAYER_ORDER = ['protocol', 'quality', 'security', 'llm']

function formatDate(ts: string): string {
  try {
    return new Date(ts).toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit',
    })
  } catch {
    return ts
  }
}

function scoreLabel(score: number): string {
  if (score >= 80) return 'Good'
  if (score >= 60) return 'Fair'
  return 'Poor'
}

export interface EvalDownloadOptions {
  layers: Set<string>
  showSummary: boolean
  showFalsePositives: boolean
}

export function downloadEvalPdf(report: FullEvalReport, serverName: string, opts?: EvalDownloadOptions) {
  const includeLayers = opts?.layers ?? new Set(LAYER_ORDER)
  const showSummary = opts?.showSummary !== false
  const showFP = opts?.showFalsePositives !== false
  const doc = new jsPDF()
  const pageWidth = doc.internal.pageSize.getWidth()
  let y = 20

  // Title
  doc.setFontSize(18)
  doc.setFont('helvetica', 'bold')
  doc.text('MCP Evaluation Report', 14, y)
  y += 8
  doc.setFontSize(12)
  doc.setFont('helvetica', 'normal')
  doc.text(serverName, 14, y)
  y += 10

  if (showSummary) {
    // Summary box
    doc.setFontSize(10)
    doc.setDrawColor(200, 200, 200)
    doc.setFillColor(248, 248, 248)
    doc.roundedRect(14, y, pageWidth - 28, 28, 2, 2, 'FD')
    y += 7
    doc.setFont('helvetica', 'bold')
    doc.text(`Overall Score: ${report.overall_score.toFixed(1)}/100 (${scoreLabel(report.overall_score)})`, 20, y)
    y += 6
    doc.setFont('helvetica', 'normal')
    doc.text(`Gate: ${report.gate_passed ? 'PASSED' : 'FAILED'}`, 20, y)
    y += 6
    if (report.timestamp) {
      doc.text(`Evaluated: ${formatDate(report.timestamp)}`, 20, y)
    }
    y += 12

    // LLM metadata
    if (report.metadata?.llm_provider) {
      doc.setFontSize(9)
      doc.setTextColor(100, 100, 100)
      doc.text(`LLM Provider: ${report.metadata.llm_provider}${report.metadata.llm_model ? ' / ' + report.metadata.llm_model : ''}`, 14, y)
      doc.setTextColor(0, 0, 0)
      y += 8
    }

    // Layer summary table
    doc.setFontSize(12)
    doc.setFont('helvetica', 'bold')
    doc.text('Layer Summary', 14, y)
    y += 2

    const summaryKeys = LAYER_ORDER.filter(k => k in report.layers && includeLayers.has(k))
    const layerRows = summaryKeys.map(k => {
      const layer = report.layers[k]
      const checks = layer.tools.flatMap(t => t.checks)
      const pass = checks.filter(c => c.status === 'pass').length
      const fail = checks.filter(c => c.status === 'fail').length
      const warn = checks.filter(c => c.status === 'warn').length
      return [LAYER_LABELS[k] || k, layer.score.toFixed(1), String(layer.tool_count), String(pass), String(fail), String(warn)]
    })

    if (layerRows.length > 0) {
      autoTable(doc, {
        startY: y,
        head: [['Layer', 'Score', 'Tools', 'Pass', 'Fail', 'Warn']],
        body: layerRows,
        theme: 'grid',
        headStyles: { fillColor: [59, 130, 246], fontSize: 9 },
        bodyStyles: { fontSize: 8 },
        columnStyles: {
          1: { halign: 'center' },
          2: { halign: 'center' },
          3: { halign: 'center' },
          4: { halign: 'center' },
          5: { halign: 'center' },
        },
        margin: { left: 14, right: 14 },
      })
      y = (doc as any).lastAutoTable.finalY + 10
    }
  }

  // Per-layer detail tables
  const layerKeys = LAYER_ORDER.filter(k => k in report.layers && includeLayers.has(k))
  for (const key of layerKeys) {
    const layer = report.layers[key]

    if (y > doc.internal.pageSize.getHeight() - 40) {
      doc.addPage()
      y = 20
    }

    doc.setFontSize(11)
    doc.setFont('helvetica', 'bold')
    doc.text(`${LAYER_LABELS[key] || key} — Score: ${layer.score.toFixed(1)}`, 14, y)
    y += 2

    // Catalog checks
    if (layer.catalog_checks && layer.catalog_checks.length > 0) {
      const fps = showFP ? ((report.metadata?.false_positives ?? {}) as Record<string, string>) : {}
      const catRows = layer.catalog_checks.map(c => {
        const fpKey = `${key}:_catalog_:${c.check_id}`
        const fpJ = fps[fpKey]
        const status = fpJ ? 'FP' : c.status.toUpperCase()
        const msg = fpJ ? `[FP] ${c.message.slice(0, 90)} — ${fpJ.slice(0, 60)}` : c.message
        return [status, msg, c.severity || '']
      })
      autoTable(doc, {
        startY: y,
        head: [['Status', 'Message', 'Severity']],
        body: catRows,
        theme: 'striped',
        headStyles: { fillColor: [107, 114, 128], fontSize: 8 },
        bodyStyles: { fontSize: 7 },
        columnStyles: { 0: { cellWidth: 18 }, 2: { cellWidth: 22 } },
        margin: { left: 14, right: 14 },
        didParseCell: (data) => {
          if (data.section === 'body' && data.column.index === 0) {
            const val = data.cell.raw as string
            if (val === 'PASS') data.cell.styles.textColor = [22, 163, 74]
            else if (val === 'FAIL') data.cell.styles.textColor = [220, 38, 38]
            else if (val === 'WARN') data.cell.styles.textColor = [202, 138, 4]
            else if (val === 'FP') data.cell.styles.textColor = [126, 34, 206]
          }
        },
      })
      y = (doc as any).lastAutoTable.finalY + 4
    }

    // Tool checks
    const fps = showFP ? ((report.metadata?.false_positives ?? {}) as Record<string, string>) : {}
    const checkRows: string[][] = []
    for (const tool of layer.tools) {
      for (const check of tool.checks) {
        const fpKey = `${key}:${tool.tool_name}:${check.check_id}`
        const fpJustification = fps[fpKey]
        const statusLabel = fpJustification ? 'FP' : check.status.toUpperCase()
        const msg = fpJustification
          ? `[FP] ${check.message.slice(0, 90)} — ${fpJustification.slice(0, 60)}`
          : check.message.slice(0, 120)
        checkRows.push([
          tool.tool_name,
          statusLabel,
          msg,
          check.severity || '',
        ])
      }
    }

    if (checkRows.length > 0) {
      autoTable(doc, {
        startY: y,
        head: [['Tool', 'Status', 'Check', 'Severity']],
        body: checkRows,
        theme: 'striped',
        headStyles: { fillColor: [107, 114, 128], fontSize: 8 },
        bodyStyles: { fontSize: 7 },
        columnStyles: {
          0: { cellWidth: 35 },
          1: { cellWidth: 16 },
          3: { cellWidth: 20 },
        },
        margin: { left: 14, right: 14 },
        didParseCell: (data) => {
          if (data.section === 'body' && data.column.index === 1) {
            const val = data.cell.raw as string
            if (val === 'PASS') data.cell.styles.textColor = [22, 163, 74]
            else if (val === 'FAIL') data.cell.styles.textColor = [220, 38, 38]
            else if (val === 'WARN') data.cell.styles.textColor = [202, 138, 4]
            else if (val === 'FP') data.cell.styles.textColor = [126, 34, 206]
          }
        },
      })
      y = (doc as any).lastAutoTable.finalY + 10
    }
  }

  // Footer
  const pageCount = doc.getNumberOfPages()
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i)
    doc.setFontSize(8)
    doc.setTextColor(150, 150, 150)
    doc.text(
      `MCP Lens — ${serverName} — Page ${i} of ${pageCount}`,
      pageWidth / 2, doc.internal.pageSize.getHeight() - 10,
      { align: 'center' },
    )
  }

  doc.save(`${serverName}-eval-report.pdf`)
}

export function downloadEvalJson(report: FullEvalReport, serverName: string, opts?: EvalDownloadOptions) {
  const includeLayers = opts?.layers ?? new Set(LAYER_ORDER)
  const showSummary = opts?.showSummary !== false
  const showFP = opts?.showFalsePositives !== false

  const filtered: Record<string, unknown> = {
    timestamp: report.timestamp,
    server_name: report.server_name,
  }
  if (showSummary) {
    filtered.overall_score = report.overall_score
    filtered.gate_passed = report.gate_passed
  }

  const layers: Record<string, unknown> = {}
  for (const k of LAYER_ORDER) {
    if (k in report.layers && includeLayers.has(k)) {
      layers[k] = report.layers[k]
    }
  }
  filtered.layers = layers

  if (report.metadata) {
    const meta = { ...report.metadata }
    if (!showFP) {
      delete meta.false_positives
    }
    filtered.metadata = meta
  }

  downloadJson(filtered, `${serverName}-eval.json`)
}

export interface ToolsDownloadOptions {
  showOverview: boolean
  showParameters: boolean
  showSchemas: boolean
}

export function downloadToolsPdf(tools: ToolInfo[], serverName: string, opts?: ToolsDownloadOptions) {
  const showOverview = opts?.showOverview !== false
  const showParams = opts?.showParameters !== false
  const doc = new jsPDF()
  const pageWidth = doc.internal.pageSize.getWidth()
  let y = 20

  // Title
  doc.setFontSize(18)
  doc.setFont('helvetica', 'bold')
  doc.text('MCP Tools Report', 14, y)
  y += 8
  doc.setFontSize(12)
  doc.setFont('helvetica', 'normal')
  doc.text(`${serverName} — ${tools.length} tools`, 14, y)
  y += 12

  if (showOverview) {
    // Tools overview table
    const overviewRows = tools.map(t => {
      const params = t.inputSchema?.properties as Record<string, unknown> | undefined
      const required = (t.inputSchema?.required as string[]) || []
      const paramCount = params ? Object.keys(params).length : 0
      return [
        t.name,
        (t.description || '').slice(0, 80) + ((t.description || '').length > 80 ? '...' : ''),
        String(paramCount),
        String(required.length),
      ]
    })

    autoTable(doc, {
      startY: y,
      head: [['Tool Name', 'Description', 'Params', 'Required']],
      body: overviewRows,
      theme: 'grid',
      headStyles: { fillColor: [59, 130, 246], fontSize: 9 },
      bodyStyles: { fontSize: 8 },
      columnStyles: {
        0: { cellWidth: 40, font: 'courier' },
        2: { halign: 'center', cellWidth: 18 },
        3: { halign: 'center', cellWidth: 20 },
      },
      margin: { left: 14, right: 14 },
    })

    y = (doc as any).lastAutoTable.finalY + 12
  }

  if (showParams) {
    // Per-tool detail tables
    for (const tool of tools) {
      const params = tool.inputSchema?.properties as Record<string, { type?: string; description?: string }> | undefined
      if (!params || Object.keys(params).length === 0) continue

      if (y > doc.internal.pageSize.getHeight() - 40) {
        doc.addPage()
        y = 20
      }

      const required = (tool.inputSchema?.required as string[]) || []

      doc.setFontSize(10)
      doc.setFont('helvetica', 'bold')
      doc.text(tool.name, 14, y)
      y += 1
      if (tool.description) {
        doc.setFontSize(8)
        doc.setFont('helvetica', 'normal')
        doc.setTextColor(100, 100, 100)
        const descLines = doc.splitTextToSize(tool.description, pageWidth - 28)
        doc.text(descLines.slice(0, 2), 14, y + 4)
        y += Math.min(descLines.length, 2) * 4 + 2
        doc.setTextColor(0, 0, 0)
      }

      const paramRows = Object.entries(params).map(([name, def]) => [
        name,
        def.type || '—',
        required.includes(name) ? 'Yes' : 'No',
        (def.description || '—').slice(0, 80),
      ])

      autoTable(doc, {
        startY: y,
        head: [['Parameter', 'Type', 'Required', 'Description']],
        body: paramRows,
        theme: 'striped',
        headStyles: { fillColor: [107, 114, 128], fontSize: 8 },
        bodyStyles: { fontSize: 7 },
        columnStyles: {
          0: { cellWidth: 30, font: 'courier' },
          1: { cellWidth: 20 },
          2: { cellWidth: 20, halign: 'center' },
        },
        margin: { left: 14, right: 14 },
      })

      y = (doc as any).lastAutoTable.finalY + 10
    }
  }

  // Footer
  const pageCount = doc.getNumberOfPages()
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i)
    doc.setFontSize(8)
    doc.setTextColor(150, 150, 150)
    doc.text(
      `MCP Lens — ${serverName} — Page ${i} of ${pageCount}`,
      pageWidth / 2, doc.internal.pageSize.getHeight() - 10,
      { align: 'center' },
    )
  }

  doc.save(`${serverName}-tools.pdf`)
}

export function downloadToolsJson(tools: ToolInfo[], serverName: string, opts?: ToolsDownloadOptions) {
  const showSchemas = opts?.showSchemas !== false
  const data = {
    server: serverName,
    tools_count: tools.length,
    tools: showSchemas ? tools : tools.map(t => ({
      name: t.name,
      description: t.description,
      parameters: t.inputSchema?.properties
        ? Object.fromEntries(
            Object.entries(t.inputSchema.properties as Record<string, { type?: string; description?: string }>).map(
              ([k, v]) => [k, { type: v.type, description: v.description }]
            )
          )
        : undefined,
      required: t.inputSchema?.required,
    })),
  }
  downloadJson(data, `${serverName}-tools.json`)
}

export interface CombinedDownloadOptions {
  tools: ToolsDownloadOptions | null
  eval: EvalDownloadOptions | null
  comparison: boolean
}

function buildComparisonData(report: FullEvalReport): unknown[] | null {
  const perLlm = report.metadata?.per_llm as Record<string, {
    layer?: { tools: Array<{ tool_name: string; checks: Array<{ check_id: string; status: string; details?: Record<string, unknown> }> }> }
    metadata: { llm_provider: string; llm_model: string }
  }> | undefined
  if (!perLlm) return null

  const toolMap: Record<string, Record<string, { selected: string; status: string; scenario: string }>> = {}
  for (const [llmName, data] of Object.entries(perLlm)) {
    if (!data.layer) continue
    for (const tool of data.layer.tools) {
      for (const check of tool.checks) {
        if (check.check_id !== 'llm.tool_selection') continue
        if (!toolMap[tool.tool_name]) toolMap[tool.tool_name] = {}
        const d = check.details ?? {}
        toolMap[tool.tool_name][llmName] = {
          selected: (d.selected as string) ?? '',
          status: check.status,
          scenario: (d.scenario as string) ?? '',
        }
      }
    }
  }

  return Object.entries(toolMap).map(([tool, results]) => ({ tool, results }))
}

export function downloadCombinedPdf(
  tools: ToolInfo[],
  report: FullEvalReport | null,
  serverName: string,
  opts: CombinedDownloadOptions,
) {
  const doc = new jsPDF()
  const pageWidth = doc.internal.pageSize.getWidth()
  let y = 20

  doc.setFontSize(18)
  doc.setFont('helvetica', 'bold')
  doc.text('MCP Lens Report', 14, y)
  y += 8
  doc.setFontSize(12)
  doc.setFont('helvetica', 'normal')
  doc.text(serverName, 14, y)
  y += 12

  if (opts.tools) {
    const showOverview = opts.tools.showOverview
    const showParams = opts.tools.showParameters

    if (showOverview || showParams) {
      doc.setFontSize(14)
      doc.setFont('helvetica', 'bold')
      doc.text('Tools', 14, y)
      y += 2
      doc.setFontSize(10)
      doc.setFont('helvetica', 'normal')
      doc.text(`${tools.length} tools`, 14, y + 4)
      y += 10
    }

    if (showOverview) {
      const overviewRows = tools.map(t => {
        const params = t.inputSchema?.properties as Record<string, unknown> | undefined
        const required = (t.inputSchema?.required as string[]) || []
        const paramCount = params ? Object.keys(params).length : 0
        return [
          t.name,
          (t.description || '').slice(0, 80) + ((t.description || '').length > 80 ? '...' : ''),
          String(paramCount),
          String(required.length),
        ]
      })

      autoTable(doc, {
        startY: y,
        head: [['Tool Name', 'Description', 'Params', 'Required']],
        body: overviewRows,
        theme: 'grid',
        headStyles: { fillColor: [59, 130, 246], fontSize: 9 },
        bodyStyles: { fontSize: 8 },
        columnStyles: {
          0: { cellWidth: 40, font: 'courier' },
          2: { halign: 'center', cellWidth: 18 },
          3: { halign: 'center', cellWidth: 20 },
        },
        margin: { left: 14, right: 14 },
      })
      y = (doc as any).lastAutoTable.finalY + 12
    }

    if (showParams) {
      for (const tool of tools) {
        const params = tool.inputSchema?.properties as Record<string, { type?: string; description?: string }> | undefined
        if (!params || Object.keys(params).length === 0) continue

        if (y > doc.internal.pageSize.getHeight() - 40) {
          doc.addPage()
          y = 20
        }

        const required = (tool.inputSchema?.required as string[]) || []

        doc.setFontSize(10)
        doc.setFont('helvetica', 'bold')
        doc.text(tool.name, 14, y)
        y += 1
        if (tool.description) {
          doc.setFontSize(8)
          doc.setFont('helvetica', 'normal')
          doc.setTextColor(100, 100, 100)
          const descLines = doc.splitTextToSize(tool.description, pageWidth - 28)
          doc.text(descLines.slice(0, 2), 14, y + 4)
          y += Math.min(descLines.length, 2) * 4 + 2
          doc.setTextColor(0, 0, 0)
        }

        const paramRows = Object.entries(params).map(([name, def]) => [
          name,
          def.type || '—',
          required.includes(name) ? 'Yes' : 'No',
          (def.description || '—').slice(0, 80),
        ])

        autoTable(doc, {
          startY: y,
          head: [['Parameter', 'Type', 'Required', 'Description']],
          body: paramRows,
          theme: 'striped',
          headStyles: { fillColor: [107, 114, 128], fontSize: 8 },
          bodyStyles: { fontSize: 7 },
          columnStyles: {
            0: { cellWidth: 30, font: 'courier' },
            1: { cellWidth: 20 },
            2: { cellWidth: 20, halign: 'center' },
          },
          margin: { left: 14, right: 14 },
        })
        y = (doc as any).lastAutoTable.finalY + 10
      }
    }
  }

  if (opts.eval && report) {
    const includeLayers = opts.eval.layers
    const showSummary = opts.eval.showSummary
    const showFP = opts.eval.showFalsePositives

    if (y > 30) {
      doc.addPage()
      y = 20
    }

    doc.setFontSize(14)
    doc.setFont('helvetica', 'bold')
    doc.text('Evaluation Report', 14, y)
    y += 10

    if (showSummary) {
      doc.setFontSize(10)
      doc.setDrawColor(200, 200, 200)
      doc.setFillColor(248, 248, 248)
      doc.roundedRect(14, y, pageWidth - 28, 28, 2, 2, 'FD')
      y += 7
      doc.setFont('helvetica', 'bold')
      doc.text(`Overall Score: ${report.overall_score.toFixed(1)}/100 (${scoreLabel(report.overall_score)})`, 20, y)
      y += 6
      doc.setFont('helvetica', 'normal')
      doc.text(`Gate: ${report.gate_passed ? 'PASSED' : 'FAILED'}`, 20, y)
      y += 6
      if (report.timestamp) {
        doc.text(`Evaluated: ${formatDate(report.timestamp)}`, 20, y)
      }
      y += 12

      if (report.metadata?.llm_provider) {
        doc.setFontSize(9)
        doc.setTextColor(100, 100, 100)
        doc.text(`LLM Provider: ${report.metadata.llm_provider}${report.metadata.llm_model ? ' / ' + report.metadata.llm_model : ''}`, 14, y)
        doc.setTextColor(0, 0, 0)
        y += 8
      }

      doc.setFontSize(12)
      doc.setFont('helvetica', 'bold')
      doc.text('Layer Summary', 14, y)
      y += 2

      const summaryKeys = LAYER_ORDER.filter(k => k in report.layers && includeLayers.has(k))
      const layerRows = summaryKeys.map(k => {
        const layer = report.layers[k]
        const checks = layer.tools.flatMap(t => t.checks)
        const pass = checks.filter(c => c.status === 'pass').length
        const fail = checks.filter(c => c.status === 'fail').length
        const warn = checks.filter(c => c.status === 'warn').length
        return [LAYER_LABELS[k] || k, layer.score.toFixed(1), String(layer.tool_count), String(pass), String(fail), String(warn)]
      })

      if (layerRows.length > 0) {
        autoTable(doc, {
          startY: y,
          head: [['Layer', 'Score', 'Tools', 'Pass', 'Fail', 'Warn']],
          body: layerRows,
          theme: 'grid',
          headStyles: { fillColor: [59, 130, 246], fontSize: 9 },
          bodyStyles: { fontSize: 8 },
          columnStyles: {
            1: { halign: 'center' },
            2: { halign: 'center' },
            3: { halign: 'center' },
            4: { halign: 'center' },
            5: { halign: 'center' },
          },
          margin: { left: 14, right: 14 },
        })
        y = (doc as any).lastAutoTable.finalY + 10
      }
    }

    const layerKeys = LAYER_ORDER.filter(k => k in report.layers && includeLayers.has(k))
    for (const key of layerKeys) {
      const layer = report.layers[key]

      if (y > doc.internal.pageSize.getHeight() - 40) {
        doc.addPage()
        y = 20
      }

      doc.setFontSize(11)
      doc.setFont('helvetica', 'bold')
      doc.text(`${LAYER_LABELS[key] || key} — Score: ${layer.score.toFixed(1)}`, 14, y)
      y += 2

      if (layer.catalog_checks && layer.catalog_checks.length > 0) {
        const fps = showFP ? ((report.metadata?.false_positives ?? {}) as Record<string, string>) : {}
        const catRows = layer.catalog_checks.map(c => {
          const fpKey = `${key}:_catalog_:${c.check_id}`
          const fpJ = fps[fpKey]
          const status = fpJ ? 'FP' : c.status.toUpperCase()
          const msg = fpJ ? `[FP] ${c.message.slice(0, 90)} — ${fpJ.slice(0, 60)}` : c.message
          return [status, msg, c.severity || '']
        })
        autoTable(doc, {
          startY: y,
          head: [['Status', 'Message', 'Severity']],
          body: catRows,
          theme: 'striped',
          headStyles: { fillColor: [107, 114, 128], fontSize: 8 },
          bodyStyles: { fontSize: 7 },
          columnStyles: { 0: { cellWidth: 18 }, 2: { cellWidth: 22 } },
          margin: { left: 14, right: 14 },
          didParseCell: (data) => {
            if (data.section === 'body' && data.column.index === 0) {
              const val = data.cell.raw as string
              if (val === 'PASS') data.cell.styles.textColor = [22, 163, 74]
              else if (val === 'FAIL') data.cell.styles.textColor = [220, 38, 38]
              else if (val === 'WARN') data.cell.styles.textColor = [202, 138, 4]
              else if (val === 'FP') data.cell.styles.textColor = [126, 34, 206]
            }
          },
        })
        y = (doc as any).lastAutoTable.finalY + 4
      }

      const fps = showFP ? ((report.metadata?.false_positives ?? {}) as Record<string, string>) : {}
      const checkRows: string[][] = []
      for (const tool of layer.tools) {
        for (const check of tool.checks) {
          const fpKey = `${key}:${tool.tool_name}:${check.check_id}`
          const fpJustification = fps[fpKey]
          const statusLabel = fpJustification ? 'FP' : check.status.toUpperCase()
          const msg = fpJustification
            ? `[FP] ${check.message.slice(0, 90)} — ${fpJustification.slice(0, 60)}`
            : check.message.slice(0, 120)
          checkRows.push([tool.tool_name, statusLabel, msg, check.severity || ''])
        }
      }

      if (checkRows.length > 0) {
        autoTable(doc, {
          startY: y,
          head: [['Tool', 'Status', 'Check', 'Severity']],
          body: checkRows,
          theme: 'striped',
          headStyles: { fillColor: [107, 114, 128], fontSize: 8 },
          bodyStyles: { fontSize: 7 },
          columnStyles: {
            0: { cellWidth: 35 },
            1: { cellWidth: 16 },
            3: { cellWidth: 20 },
          },
          margin: { left: 14, right: 14 },
          didParseCell: (data) => {
            if (data.section === 'body' && data.column.index === 1) {
              const val = data.cell.raw as string
              if (val === 'PASS') data.cell.styles.textColor = [22, 163, 74]
              else if (val === 'FAIL') data.cell.styles.textColor = [220, 38, 38]
              else if (val === 'WARN') data.cell.styles.textColor = [202, 138, 4]
              else if (val === 'FP') data.cell.styles.textColor = [126, 34, 206]
            }
          },
        })
        y = (doc as any).lastAutoTable.finalY + 10
      }
    }
  }

  if (opts.comparison && report) {
    const perLlm = report.metadata?.per_llm as Record<string, {
      layer?: { tools: Array<{ tool_name: string; checks: Array<{ check_id: string; status: string; details?: Record<string, unknown> }> }>; score: number }
      metadata: { llm_provider: string; llm_model: string }
    }> | undefined

    if (perLlm && Object.keys(perLlm).length > 0) {
      if (y > 30) {
        doc.addPage()
        y = 20
      }

      doc.setFontSize(14)
      doc.setFont('helvetica', 'bold')
      doc.text('LLM Tool Selection Comparison', 14, y)
      y += 10

      const llmNames = Object.keys(perLlm).filter(n => perLlm[n].layer)
      const toolMap: Record<string, Record<string, { selected: string; status: string }>> = {}
      for (const llm of llmNames) {
        const layer = perLlm[llm].layer!
        for (const tool of layer.tools) {
          for (const check of tool.checks) {
            if (check.check_id !== 'llm.tool_selection') continue
            if (!toolMap[tool.tool_name]) toolMap[tool.tool_name] = {}
            toolMap[tool.tool_name][llm] = {
              selected: (check.details?.selected as string) ?? '',
              status: check.status,
            }
          }
        }
      }

      const head = ['Tool', ...llmNames]
      const body = Object.entries(toolMap).sort(([a], [b]) => a.localeCompare(b)).map(([tool, results]) => {
        const row = [tool]
        for (const llm of llmNames) {
          const r = results[llm]
          row.push(r ? `${r.selected} (${r.status})` : '—')
        }
        return row
      })

      const scoreRow = ['Score']
      for (const llm of llmNames) {
        scoreRow.push(perLlm[llm].layer!.score.toFixed(1))
      }
      body.push(scoreRow)

      autoTable(doc, {
        startY: y,
        head: [head],
        body,
        theme: 'grid',
        headStyles: { fillColor: [99, 102, 241], fontSize: 8 },
        bodyStyles: { fontSize: 7 },
        columnStyles: { 0: { cellWidth: 40, font: 'courier' } },
        margin: { left: 14, right: 14 },
        didParseCell: (data) => {
          if (data.section === 'body') {
            const val = String(data.cell.raw)
            if (val.includes('(pass)')) data.cell.styles.textColor = [22, 163, 74]
            else if (val.includes('(fail)')) data.cell.styles.textColor = [220, 38, 38]
            else if (val.includes('(warn)')) data.cell.styles.textColor = [202, 138, 4]
            if (data.row.index === body.length - 1) {
              data.cell.styles.fontStyle = 'bold'
            }
          }
        },
      })
      y = (doc as any).lastAutoTable.finalY + 10
    }
  }

  const pageCount = doc.getNumberOfPages()
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i)
    doc.setFontSize(8)
    doc.setTextColor(150, 150, 150)
    doc.text(
      `MCP Lens — ${serverName} — Page ${i} of ${pageCount}`,
      pageWidth / 2, doc.internal.pageSize.getHeight() - 10,
      { align: 'center' },
    )
  }

  doc.save(`${serverName}-report.pdf`)
}

export function downloadCombinedJson(
  tools: ToolInfo[],
  report: FullEvalReport | null,
  serverName: string,
  opts: CombinedDownloadOptions,
) {
  const data: Record<string, unknown> = { server: serverName }

  if (opts.tools) {
    const showSchemas = opts.tools.showSchemas
    data.tools_count = tools.length
    data.tools = showSchemas ? tools : tools.map(t => ({
      name: t.name,
      description: t.description,
      parameters: t.inputSchema?.properties
        ? Object.fromEntries(
            Object.entries(t.inputSchema.properties as Record<string, { type?: string; description?: string }>).map(
              ([k, v]) => [k, { type: v.type, description: v.description }]
            )
          )
        : undefined,
      required: t.inputSchema?.required,
    }))
  }

  if (opts.eval && report) {
    const includeLayers = opts.eval.layers
    const showSummary = opts.eval.showSummary
    const showFP = opts.eval.showFalsePositives

    const evalData: Record<string, unknown> = {
      timestamp: report.timestamp,
    }
    if (showSummary) {
      evalData.overall_score = report.overall_score
      evalData.gate_passed = report.gate_passed
    }

    const layers: Record<string, unknown> = {}
    for (const k of LAYER_ORDER) {
      if (k in report.layers && includeLayers.has(k)) {
        layers[k] = report.layers[k]
      }
    }
    evalData.layers = layers

    if (report.metadata) {
      const meta = { ...report.metadata }
      if (!showFP) {
        delete meta.false_positives
      }
      evalData.metadata = meta
    }

    data.evaluation = evalData
  }

  if (opts.comparison && report) {
    const compData = buildComparisonData(report)
    if (compData) data.llm_tool_selection = { comparison: compData }
  }

  downloadJson(data, `${serverName}-report.json`)
}

export function downloadCombinedYaml(
  tools: ToolInfo[],
  report: FullEvalReport | null,
  serverName: string,
  opts: CombinedDownloadOptions,
) {
  const data: Record<string, unknown> = { server: serverName }

  if (opts.tools) {
    const showSchemas = opts.tools.showSchemas
    data.tools_count = tools.length
    data.tools = showSchemas ? tools : tools.map(t => ({
      name: t.name,
      description: t.description,
      parameters: t.inputSchema?.properties
        ? Object.fromEntries(
            Object.entries(t.inputSchema.properties as Record<string, { type?: string; description?: string }>).map(
              ([k, v]) => [k, { type: v.type, description: v.description }]
            )
          )
        : undefined,
      required: t.inputSchema?.required,
    }))
  }

  if (opts.eval && report) {
    const includeLayers = opts.eval.layers
    const showSummary = opts.eval.showSummary
    const showFP = opts.eval.showFalsePositives

    const evalData: Record<string, unknown> = { timestamp: report.timestamp }
    if (showSummary) {
      evalData.overall_score = report.overall_score
      evalData.gate_passed = report.gate_passed
    }

    const layers: Record<string, unknown> = {}
    for (const k of LAYER_ORDER) {
      if (k in report.layers && includeLayers.has(k)) {
        layers[k] = report.layers[k]
      }
    }
    evalData.layers = layers

    if (report.metadata) {
      const meta = { ...report.metadata }
      if (!showFP) delete meta.false_positives
      evalData.metadata = meta
    }

    data.evaluation = evalData
  }

  if (opts.comparison && report) {
    const compData = buildComparisonData(report)
    if (compData) data.llm_tool_selection = { comparison: compData }
  }

  const yamlStr = yamlDump(data, { noRefs: true, lineWidth: 120, sortKeys: false })
  const blob = new Blob([yamlStr], { type: 'text/yaml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${serverName}-report.yaml`
  a.click()
  URL.revokeObjectURL(url)
}
