import { jsPDF } from 'jspdf'
import autoTable from 'jspdf-autotable'
import { dump as yamlDump } from 'js-yaml'
import type { FullEvalReport, ToolInfo } from '../types'
import type { ServerComparisonReport, ServerCapabilities, CapabilityAnalysis } from '../api'

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

export interface CapabilitiesDownloadData {
  protocol: ServerCapabilities | null
  analysis: CapabilityAnalysis | null
}

export interface CombinedDownloadOptions {
  tools: ToolsDownloadOptions | null
  eval: EvalDownloadOptions | null
  comparison: boolean
  capabilities: CapabilitiesDownloadData | null
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

  if (opts.capabilities) {
    const { protocol, analysis } = opts.capabilities

    if (protocol && protocol.capabilities && Object.keys(protocol.capabilities).length > 0) {
      if (y > doc.internal.pageSize.getHeight() - 40) { doc.addPage(); y = 20 }

      doc.setFontSize(14)
      doc.setFont('helvetica', 'bold')
      doc.text('Protocol Capabilities', 14, y)
      y += 6

      const capsRows = Object.entries(protocol.capabilities).map(([cap, val]) => [
        cap,
        val ? 'Supported' : 'Not Supported',
      ])
      autoTable(doc, {
        startY: y,
        head: [['Capability', 'Status']],
        body: capsRows,
        theme: 'grid',
        headStyles: { fillColor: [59, 130, 246], fontSize: 9 },
        bodyStyles: { fontSize: 8 },
        columnStyles: { 1: { halign: 'center' } },
        margin: { left: 14, right: 14 },
        didParseCell: (data) => {
          if (data.section === 'body' && data.column.index === 1) {
            const val = data.cell.raw as string
            if (val === 'Supported') data.cell.styles.textColor = [22, 163, 74]
            else data.cell.styles.textColor = [180, 180, 180]
          }
        },
      })
      y = (doc as any).lastAutoTable.finalY + 10
    }

    if (analysis && Object.keys(analysis.categories).length > 0) {
      if (y > doc.internal.pageSize.getHeight() - 40) { doc.addPage(); y = 20 }

      doc.setFontSize(14)
      doc.setFont('helvetica', 'bold')
      doc.text('Capability Analysis', 14, y)
      y += 2
      doc.setFontSize(10)
      doc.setFont('helvetica', 'normal')
      doc.text(`${analysis.tool_count} tools across ${analysis.category_count} categories`, 14, y + 4)
      y += 10

      const catRows = Object.entries(analysis.categories)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([category, catData]) => [
          category,
          catData.description || '',
          [...catData.tools].sort().join(', '),
          String(catData.tools.length),
        ])
      autoTable(doc, {
        startY: y,
        head: [['Category', 'Description', 'Tools', 'Count']],
        body: catRows,
        theme: 'grid',
        headStyles: { fillColor: [99, 102, 241], fontSize: 9 },
        bodyStyles: { fontSize: 7 },
        columnStyles: {
          0: { cellWidth: 30, fontStyle: 'bold' },
          1: { cellWidth: 50 },
          3: { halign: 'center', cellWidth: 16 },
        },
        margin: { left: 14, right: 14 },
      })
      y = (doc as any).lastAutoTable.finalY + 10
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

  if (opts.capabilities) {
    const capsData: Record<string, unknown> = {}
    if (opts.capabilities.protocol) {
      capsData.protocol = {
        serverInfo: opts.capabilities.protocol.serverInfo,
        capabilities: opts.capabilities.protocol.capabilities,
      }
    }
    if (opts.capabilities.analysis) {
      capsData.analysis = {
        categories: opts.capabilities.analysis.categories,
        tool_count: opts.capabilities.analysis.tool_count,
        category_count: opts.capabilities.analysis.category_count,
      }
    }
    data.capabilities = capsData
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

  if (opts.capabilities) {
    const capsData: Record<string, unknown> = {}
    if (opts.capabilities.protocol) {
      capsData.protocol = {
        serverInfo: opts.capabilities.protocol.serverInfo,
        capabilities: opts.capabilities.protocol.capabilities,
      }
    }
    if (opts.capabilities.analysis) {
      capsData.analysis = {
        categories: opts.capabilities.analysis.categories,
        tool_count: opts.capabilities.analysis.tool_count,
        category_count: opts.capabilities.analysis.category_count,
      }
    }
    data.capabilities = capsData
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

function downloadMd(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function mdTable(headers: string[], rows: string[][]): string {
  const hdr = `| ${headers.join(' | ')} |`
  const sep = `| ${headers.map(() => '---').join(' | ')} |`
  const body = rows.map(r => `| ${r.join(' | ')} |`).join('\n')
  return `${hdr}\n${sep}\n${body}`
}

function truncate(text: string, max: number): string {
  const clean = text.replace(/[\r\n]+/g, ' ').replace(/\s+/g, ' ').trim()
  if (clean.length <= max) return clean
  return clean.slice(0, max - 1) + '…'
}

function mdEscape(text: string, max?: number): string {
  const t = max ? truncate(text, max) : text.replace(/[\r\n]+/g, ' ').replace(/\s+/g, ' ').trim()
  return t.replace(/\|/g, '\\|')
}

export function downloadCombinedMd(
  tools: ToolInfo[],
  report: FullEvalReport | null,
  serverName: string,
  opts: CombinedDownloadOptions,
) {
  const lines: string[] = []
  lines.push(`# MCP Lens Report — ${serverName}`)
  lines.push('')

  if (opts.tools) {
    if (opts.tools.showOverview) {
      lines.push('## Tools Overview')
      lines.push('')
      lines.push(`**${tools.length} tools**`)
      lines.push('')
      const rows = tools.map(t => {
        const params = t.inputSchema?.properties as Record<string, unknown> | undefined
        const required = (t.inputSchema?.required as string[]) || []
        const paramCount = params ? Object.keys(params).length : 0
        return [
          `\`${t.name}\``,
          mdEscape(t.description || '—', 120),
          String(paramCount),
          String(required.length),
        ]
      })
      lines.push(mdTable(['Tool', 'Description', 'Params', 'Required'], rows))
      lines.push('')
    }

    if (opts.tools.showParameters) {
      lines.push('## Parameter Details')
      lines.push('')
      for (const tool of tools) {
        const params = tool.inputSchema?.properties as Record<string, { type?: string; description?: string }> | undefined
        if (!params || Object.keys(params).length === 0) continue
        const required = (tool.inputSchema?.required as string[]) || []
        lines.push(`### \`${tool.name}\``)
        if (tool.description) lines.push(`> ${mdEscape(tool.description, 200)}`)
        lines.push('')
        const rows = Object.entries(params).map(([name, def]) => [
          `\`${name}\``,
          def.type || '—',
          required.includes(name) ? 'Yes' : 'No',
          mdEscape(def.description || '—', 120),
        ])
        lines.push(mdTable(['Parameter', 'Type', 'Required', 'Description'], rows))
        lines.push('')
      }
    }
  }

  if (opts.capabilities) {
    const { protocol, analysis } = opts.capabilities
    if (protocol?.capabilities && Object.keys(protocol.capabilities).length > 0) {
      lines.push('## Protocol Capabilities')
      lines.push('')
      const rows = Object.entries(protocol.capabilities).map(([cap, val]) => [
        cap, val ? 'Supported' : 'Not Supported',
      ])
      lines.push(mdTable(['Capability', 'Status'], rows))
      lines.push('')
    }
    if (analysis && Object.keys(analysis.categories).length > 0) {
      lines.push('## Capability Analysis')
      lines.push(`**${analysis.tool_count} tools** across **${analysis.category_count} categories**`)
      if (analysis.llm_name) lines.push(`*Analyzed by ${analysis.llm_name}*`)
      lines.push('')
      for (const [category, catData] of Object.entries(analysis.categories).sort(([a], [b]) => a.localeCompare(b))) {
        lines.push(`### ${category}`)
        if (catData.description) lines.push(catData.description)
        lines.push('')
        lines.push(catData.tools.sort().map(t => `\`${t}\``).join('  '))
        lines.push('')
      }
    }
  }

  if (opts.eval && report) {
    const includeLayers = opts.eval.layers
    const showFP = opts.eval.showFalsePositives

    if (opts.eval.showSummary) {
      lines.push('## Evaluation Summary')
      lines.push('')
      lines.push(`- **Overall Score:** ${report.overall_score.toFixed(1)}/100 (${scoreLabel(report.overall_score)})`)
      lines.push(`- **Gate:** ${report.gate_passed ? 'PASSED' : 'FAILED'}`)
      if (report.timestamp) lines.push(`- **Evaluated:** ${formatDate(report.timestamp)}`)
      if (report.metadata?.llm_provider) {
        lines.push(`- **LLM:** ${report.metadata.llm_provider}${report.metadata.llm_model ? ' / ' + report.metadata.llm_model : ''}`)
      }
      lines.push('')

      const summaryKeys = LAYER_ORDER.filter(k => k in report.layers && includeLayers.has(k))
      if (summaryKeys.length > 0) {
        const rows = summaryKeys.map(k => {
          const layer = report.layers[k]
          const checks = layer.tools.flatMap(t => t.checks)
          const pass = checks.filter(c => c.status === 'pass').length
          const fail = checks.filter(c => c.status === 'fail').length
          const warn = checks.filter(c => c.status === 'warn').length
          return [LAYER_LABELS[k] || k, layer.score.toFixed(1), String(pass), String(fail), String(warn)]
        })
        lines.push(mdTable(['Layer', 'Score', 'Pass', 'Fail', 'Warn'], rows))
        lines.push('')
      }
    }

    const layerKeys = LAYER_ORDER.filter(k => k in report.layers && includeLayers.has(k))
    for (const key of layerKeys) {
      const layer = report.layers[key]
      lines.push(`### ${LAYER_LABELS[key] || key} — Score: ${layer.score.toFixed(1)}`)
      lines.push('')

      const fps = showFP ? ((report.metadata?.false_positives ?? {}) as Record<string, string>) : {}
      const checkRows: string[][] = []
      if (layer.catalog_checks) {
        for (const c of layer.catalog_checks) {
          const fpKey = `${key}:_catalog_:${c.check_id}`
          const fpJ = fps[fpKey]
          checkRows.push([
            fpJ ? 'FP' : c.status.toUpperCase(),
            `_(catalog)_`,
            (fpJ ? `[FP] ${c.message}` : c.message).replace(/\|/g, '\\|'),
            c.severity || '',
          ])
        }
      }
      for (const tool of layer.tools) {
        for (const check of tool.checks) {
          const fpKey = `${key}:${tool.tool_name}:${check.check_id}`
          const fpJ = fps[fpKey]
          checkRows.push([
            fpJ ? 'FP' : check.status.toUpperCase(),
            `\`${tool.tool_name}\``,
            (fpJ ? `[FP] ${check.message}` : check.message).replace(/\|/g, '\\|'),
            check.severity || '',
          ])
        }
      }
      if (checkRows.length > 0) {
        lines.push(mdTable(['Status', 'Tool', 'Check', 'Severity'], checkRows))
        lines.push('')
      }
    }
  }

  if (opts.comparison && report) {
    const compData = buildComparisonData(report)
    if (compData) {
      lines.push('## LLM Tool Selection Comparison')
      lines.push('')
      for (const entry of compData as Array<{ tool: string; results: Record<string, { selected: string; status: string; scenario: string }> }>) {
        lines.push(`### \`${entry.tool}\``)
        const rows = Object.entries(entry.results).map(([llm, r]) => [
          llm, r.selected, r.status.toUpperCase(), r.scenario.replace(/\|/g, '\\|'),
        ])
        lines.push(mdTable(['LLM', 'Selected', 'Status', 'Scenario'], rows))
        lines.push('')
      }
    }
  }

  lines.push('---')
  lines.push(`*Generated by MCP Lens*`)

  downloadMd(lines.join('\n'), `${serverName}-report.md`)
}

export function downloadComparisonMd(report: ServerComparisonReport) {
  const lines: string[] = []
  lines.push(`# MCP Server Comparison — ${report.server_a} vs ${report.server_b}`)
  lines.push(`*Generated: ${formatDate(report.timestamp)}*`)
  lines.push('')

  if (report.capabilities) {
    lines.push('## Protocol Capabilities')
    lines.push('')
    const rows = report.capabilities.capability_matrix.map(row => [
      row.capability,
      row.server_a ? 'Yes' : 'No',
      row.server_b ? 'Yes' : 'No',
    ])
    lines.push(mdTable(['Capability', report.server_a, report.server_b], rows))
    lines.push('')
  }

  const inv = report.tool_inventory
  lines.push('## Tool Inventory')
  lines.push('')
  lines.push(mdTable(
    ['Metric', report.server_a, report.server_b],
    [
      ['Total tools', String(inv.count_a), String(inv.count_b)],
      ['Unique tools', String(inv.only_a.length), String(inv.only_b.length)],
      ['Common tools', String(inv.common.length), String(inv.common.length)],
    ],
  ))
  lines.push('')

  if (inv.only_a.length > 0) {
    lines.push(`### Only in ${report.server_a}`)
    lines.push(inv.only_a.map(n => `- \`${n}\``).join('\n'))
    lines.push('')
  }
  if (inv.only_b.length > 0) {
    lines.push(`### Only in ${report.server_b}`)
    lines.push(inv.only_b.map(n => `- \`${n}\``).join('\n'))
    lines.push('')
  }

  if (report.categories.length > 0) {
    lines.push('## Capability Categories')
    lines.push('')
    const rows = report.categories.map(cat => [
      cat.category,
      cat.server_a_count > 0 ? cat.server_a_tools.join(', ') : '—',
      cat.server_b_count > 0 ? cat.server_b_tools.join(', ') : '—',
    ])
    lines.push(mdTable(['Category', report.server_a, report.server_b], rows))
    lines.push('')
  }

  const scores = report.eval_scores
  if (scores.server_a_score !== null || scores.server_b_score !== null) {
    lines.push('## Evaluation Scores')
    lines.push('')
    const rows: string[][] = [
      ['Overall', scores.server_a_score?.toFixed(1) ?? 'N/A', scores.server_b_score?.toFixed(1) ?? 'N/A'],
    ]
    for (const [layer, vals] of Object.entries(scores.layers)) {
      rows.push([layer, vals.server_a?.toFixed(1) ?? 'N/A', vals.server_b?.toFixed(1) ?? 'N/A'])
    }
    lines.push(mdTable(['Layer', report.server_a, report.server_b], rows))
    lines.push('')
  }

  const diffs = report.schema_diffs.filter(d => !d.identical)
  if (diffs.length > 0) {
    lines.push('## Schema Differences')
    lines.push('')
    const rows: string[][] = []
    for (const diff of diffs) {
      for (const d of diff.differences) {
        rows.push([
          `\`${diff.tool_name}\``,
          `\`${d.path}\``,
          d.server_a === null ? '_missing_' : `\`${JSON.stringify(d.server_a)}\``,
          d.server_b === null ? '_missing_' : `\`${JSON.stringify(d.server_b)}\``,
        ])
      }
    }
    lines.push(mdTable(['Tool', 'Path', report.server_a, report.server_b], rows))
    lines.push('')
  }

  lines.push('---')
  lines.push('*Generated by MCP Lens*')

  downloadMd(lines.join('\n'), `comparison-${report.server_a}-vs-${report.server_b}.md`)
}

export function downloadComparisonJson(report: ServerComparisonReport) {
  downloadJson(report, `comparison-${report.server_a}-vs-${report.server_b}.json`)
}

export function downloadComparisonYaml(report: ServerComparisonReport) {
  const yamlStr = yamlDump(report, { noRefs: true, lineWidth: 120, sortKeys: false })
  const blob = new Blob([yamlStr], { type: 'text/yaml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `comparison-${report.server_a}-vs-${report.server_b}.yaml`
  a.click()
  URL.revokeObjectURL(url)
}

export function downloadComparisonPdf(report: ServerComparisonReport) {
  const doc = new jsPDF()
  const pageWidth = doc.internal.pageSize.getWidth()
  let y = 20

  doc.setFontSize(18)
  doc.setFont('helvetica', 'bold')
  doc.text('MCP Server Comparison Report', 14, y)
  y += 8
  doc.setFontSize(12)
  doc.setFont('helvetica', 'normal')
  doc.text(`${report.server_a} vs ${report.server_b}`, 14, y)
  y += 6
  doc.setFontSize(9)
  doc.setTextColor(120, 120, 120)
  doc.text(`Generated: ${formatDate(report.timestamp)}`, 14, y)
  doc.setTextColor(0, 0, 0)
  y += 12

  // Capabilities
  if (report.capabilities) {
    doc.setFontSize(13)
    doc.setFont('helvetica', 'bold')
    doc.text('Protocol Capabilities', 14, y)
    y += 6

    const capsRows = report.capabilities.capability_matrix.map(row => [
      row.capability,
      row.server_a ? 'Yes' : 'No',
      row.server_b ? 'Yes' : 'No',
    ])
    autoTable(doc, {
      startY: y,
      head: [['Capability', report.server_a, report.server_b]],
      body: capsRows,
      theme: 'grid',
      headStyles: { fillColor: [59, 130, 246], fontSize: 9 },
      bodyStyles: { fontSize: 8 },
      columnStyles: { 1: { halign: 'center' }, 2: { halign: 'center' } },
      margin: { left: 14, right: 14 },
      didParseCell: (data) => {
        if (data.section === 'body' && (data.column.index === 1 || data.column.index === 2)) {
          const val = data.cell.raw as string
          if (val === 'Yes') data.cell.styles.textColor = [22, 163, 74]
          else data.cell.styles.textColor = [180, 180, 180]
        }
      },
    })
    y = (doc as any).lastAutoTable.finalY + 10
  }

  // Tool Inventory
  const inv = report.tool_inventory
  doc.setFontSize(13)
  doc.setFont('helvetica', 'bold')
  if (y > doc.internal.pageSize.getHeight() - 40) { doc.addPage(); y = 20 }
  doc.text('Tool Inventory', 14, y)
  y += 6

  const invRows = [
    ['Total tools', String(inv.count_a), String(inv.count_b)],
    ['Unique tools', String(inv.only_a.length), String(inv.only_b.length)],
    ['Common tools', String(inv.common.length), String(inv.common.length)],
  ]
  autoTable(doc, {
    startY: y,
    head: [['Metric', report.server_a, report.server_b]],
    body: invRows,
    theme: 'grid',
    headStyles: { fillColor: [59, 130, 246], fontSize: 9 },
    bodyStyles: { fontSize: 8 },
    columnStyles: { 1: { halign: 'center' }, 2: { halign: 'center' } },
    margin: { left: 14, right: 14 },
  })
  y = (doc as any).lastAutoTable.finalY + 6

  if (inv.only_a.length > 0) {
    autoTable(doc, {
      startY: y,
      head: [[`Only in ${report.server_a} (${inv.only_a.length})`]],
      body: inv.only_a.map(n => [n]),
      theme: 'striped',
      headStyles: { fillColor: [59, 130, 246], fontSize: 8 },
      bodyStyles: { fontSize: 7, font: 'courier' },
      margin: { left: 14, right: 14 },
    })
    y = (doc as any).lastAutoTable.finalY + 4
  }
  if (inv.only_b.length > 0) {
    autoTable(doc, {
      startY: y,
      head: [[`Only in ${report.server_b} (${inv.only_b.length})`]],
      body: inv.only_b.map(n => [n]),
      theme: 'striped',
      headStyles: { fillColor: [147, 51, 234], fontSize: 8 },
      bodyStyles: { fontSize: 7, font: 'courier' },
      margin: { left: 14, right: 14 },
    })
    y = (doc as any).lastAutoTable.finalY + 10
  }

  // Categories
  if (report.categories.length > 0) {
    if (y > doc.internal.pageSize.getHeight() - 40) { doc.addPage(); y = 20 }
    doc.setFontSize(13)
    doc.setFont('helvetica', 'bold')
    doc.text('Capability Categories', 14, y)
    y += 6

    const catRows = report.categories.map(cat => [
      cat.category,
      cat.server_a_count > 0 ? cat.server_a_tools.join(', ') : '--',
      cat.server_b_count > 0 ? cat.server_b_tools.join(', ') : '--',
    ])
    autoTable(doc, {
      startY: y,
      head: [['Category', report.server_a, report.server_b]],
      body: catRows,
      theme: 'grid',
      headStyles: { fillColor: [59, 130, 246], fontSize: 9 },
      bodyStyles: { fontSize: 7 },
      margin: { left: 14, right: 14 },
    })
    y = (doc as any).lastAutoTable.finalY + 10
  }

  // Eval Scores
  const scores = report.eval_scores
  if (scores.server_a_score !== null || scores.server_b_score !== null) {
    if (y > doc.internal.pageSize.getHeight() - 40) { doc.addPage(); y = 20 }
    doc.setFontSize(13)
    doc.setFont('helvetica', 'bold')
    doc.text('Evaluation Scores', 14, y)
    y += 6

    const scoreRows: string[][] = [
      ['Overall', scores.server_a_score?.toFixed(1) ?? 'N/A', scores.server_b_score?.toFixed(1) ?? 'N/A'],
    ]
    for (const [layer, vals] of Object.entries(scores.layers)) {
      scoreRows.push([layer, vals.server_a?.toFixed(1) ?? 'N/A', vals.server_b?.toFixed(1) ?? 'N/A'])
    }
    autoTable(doc, {
      startY: y,
      head: [['Layer', report.server_a, report.server_b]],
      body: scoreRows,
      theme: 'grid',
      headStyles: { fillColor: [59, 130, 246], fontSize: 9 },
      bodyStyles: { fontSize: 8 },
      columnStyles: { 1: { halign: 'center' }, 2: { halign: 'center' } },
      margin: { left: 14, right: 14 },
    })
    y = (doc as any).lastAutoTable.finalY + 10
  }

  // Schema Diffs
  const diffs = report.schema_diffs.filter(d => !d.identical)
  if (diffs.length > 0) {
    if (y > doc.internal.pageSize.getHeight() - 40) { doc.addPage(); y = 20 }
    doc.setFontSize(13)
    doc.setFont('helvetica', 'bold')
    doc.text('Schema Differences', 14, y)
    y += 6

    const diffRows: string[][] = []
    for (const diff of diffs) {
      for (const d of diff.differences) {
        diffRows.push([
          diff.tool_name,
          d.path,
          d.server_a === null ? 'missing' : JSON.stringify(d.server_a),
          d.server_b === null ? 'missing' : JSON.stringify(d.server_b),
        ])
      }
    }
    autoTable(doc, {
      startY: y,
      head: [['Tool', 'Path', report.server_a, report.server_b]],
      body: diffRows,
      theme: 'striped',
      headStyles: { fillColor: [107, 114, 128], fontSize: 8 },
      bodyStyles: { fontSize: 7 },
      columnStyles: { 0: { cellWidth: 30, font: 'courier' }, 1: { cellWidth: 35, font: 'courier' } },
      margin: { left: 14, right: 14 },
    })
  }

  // Footer
  const pageCount = doc.getNumberOfPages()
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i)
    doc.setFontSize(8)
    doc.setTextColor(150, 150, 150)
    doc.text(
      `MCP Lens — ${report.server_a} vs ${report.server_b} — Page ${i} of ${pageCount}`,
      pageWidth / 2, doc.internal.pageSize.getHeight() - 10,
      { align: 'center' },
    )
  }

  doc.save(`comparison-${report.server_a}-vs-${report.server_b}.pdf`)
}
