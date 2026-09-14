import { useState } from 'react'

function Section({ id, title, children, expanded, onToggle }: {
  id: string
  title: string
  children: React.ReactNode
  expanded: boolean
  onToggle: (id: string) => void
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => onToggle(id)}
        className="w-full text-left px-5 py-4 flex justify-between items-center hover:bg-gray-50"
      >
        <span className="font-semibold text-gray-800">{title}</span>
        <span className="text-gray-400 text-xs">{expanded ? '▼' : '▶'}</span>
      </button>
      {expanded && (
        <div className="border-t border-gray-100 px-5 py-4 text-sm text-gray-700 space-y-4">
          {children}
        </div>
      )}
    </div>
  )
}

function RulesTable({ rules }: { rules: { id: string; description: string; severity: string; status: string }[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50">
            <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Rule ID</th>
            <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">What it checks</th>
            <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Severity</th>
            <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Status</th>
          </tr>
        </thead>
        <tbody>
          {rules.map(r => (
            <tr key={r.id} className="border-b border-gray-100 last:border-0">
              <td className="px-3 py-2 font-mono text-xs text-blue-700 whitespace-nowrap">{r.id}</td>
              <td className="px-3 py-2 text-xs text-gray-700">{r.description}</td>
              <td className="px-3 py-2"><SeverityBadge severity={r.severity} /></td>
              <td className="px-3 py-2 text-xs text-gray-500">{r.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  const s = severity.toLowerCase()
  let cls = 'bg-gray-100 text-gray-600'
  if (s.includes('critical')) cls = 'bg-red-100 text-red-700'
  else if (s.includes('high')) cls = 'bg-orange-100 text-orange-700'
  else if (s.includes('medium')) cls = 'bg-yellow-100 text-yellow-700'
  else if (s.includes('low')) cls = 'bg-blue-100 text-blue-700'
  else if (s.includes('info')) cls = 'bg-gray-100 text-gray-500'
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${cls}`}>{severity}</span>
}

function Code({ children }: { children: string }) {
  return <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs font-mono text-gray-800">{children}</code>
}

const ALL_SECTIONS = ['overview', 'upload', 'layers', 'protocol', 'quality', 'security', 'llm', 'scoring', 'config', 'guidelines']

export default function AboutPage() {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(ALL_SECTIONS))

  function toggle(id: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function expandAll() { setExpanded(new Set(ALL_SECTIONS)) }
  function collapseAll() { setExpanded(new Set()) }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-800">About MCP Lens</h2>
          <p className="text-sm text-gray-500 mt-1">Evaluation framework reference and configuration guide</p>
        </div>
        <div className="flex gap-2 text-xs">
          <button onClick={expandAll} className="text-blue-600 hover:underline">Expand All</button>
          <button onClick={collapseAll} className="text-blue-600 hover:underline">Collapse All</button>
        </div>
      </div>

      {/* Overview */}
      <Section id="overview" title="Overview" expanded={expanded.has('overview')} onToggle={toggle}>
        <p>
          MCP Lens connects to <a href="https://modelcontextprotocol.io/" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">Model Context Protocol</a> servers,
          fetches their tool definitions, and runs a multi-layer evaluation to surface protocol violations, quality issues,
          security risks, and — when an LLM is configured — real-world usability problems.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
          {[
            ['Server Management', 'Add, edit, and test MCP server connections (SSE transport, OAuth/bearer/API-key auth)'],
            ['Tool Inspection', 'Fetch and browse tool definitions with full schema detail, or upload manually when server is unreachable'],
            ['Multi-layer Evaluation', '35+ checks across protocol compliance, quality, security, and LLM-assisted layers'],
            ['Scoring & Gating', 'Weighted overall score with configurable pass/fail thresholds'],
            ['Export', 'Download evaluation reports and tool definitions as JSON, YAML, or PDF'],
            ['LLM Evaluation', 'Optional checks that test tools from an AI agent\'s perspective'],
          ].map(([title, desc]) => (
            <div key={title} className="bg-gray-50 rounded-lg p-3">
              <div className="font-medium text-gray-800 text-xs">{title}</div>
              <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
            </div>
          ))}
        </div>
      </Section>

      {/* Manual Tool Upload */}
      <Section id="upload" title="Manual Tool Upload" expanded={expanded.has('upload')} onToggle={toggle}>
        <p>
          When an MCP server is unreachable (firewall, VPN, authentication issues), you can upload tool definitions manually
          and run evaluations against them.
        </p>
        <div className="space-y-2 mt-3">
          {[
            { step: '1', title: 'Download template', desc: 'Click "Template" on the Tools tab to get a YAML file with the expected structure. If tools already exist, they\'re used as the template.' },
            { step: '2', title: 'Fill in definitions', desc: 'Add tool names, descriptions, and input schemas. Each tool must have a name; description and inputSchema are recommended.' },
            { step: '3', title: 'Upload', desc: 'Click "Upload" and select the completed YAML file. The system validates the format and shows warnings for missing descriptions.' },
          ].map(item => (
            <div key={item.step} className="bg-gray-50 rounded-lg p-3 flex gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-xs font-medium">{item.step}</span>
              <div>
                <div className="font-medium text-gray-800 text-xs">{item.title}</div>
                <div className="text-xs text-gray-600 mt-0.5">{item.desc}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mt-3 text-xs">
          <p className="text-amber-800">
            <strong>Override behavior:</strong> Uploaded tools and fetched tools share the same storage. Re-fetching from the server
            replaces uploaded tools (badge changes to "Fetched from server"). Uploading replaces previously fetched tools
            (badge changes to "Uploaded by user"). The source badge in the header always shows the current state.
          </p>
        </div>
        <h4 className="font-medium text-gray-800 mt-4">YAML Format</h4>
        <div className="bg-gray-50 rounded-lg p-3 mt-2 font-mono text-[11px] text-gray-600 whitespace-pre">{`tools:
  - name: my_tool
    description: Does something useful
    inputSchema:
      type: object
      properties:
        param1:
          type: string
          description: A required parameter
      required:
        - param1`}</div>
      </Section>

      {/* Evaluation Layers Summary */}
      <Section id="layers" title="Evaluation Layers" expanded={expanded.has('layers')} onToggle={toggle}>
        <p>MCP Lens runs four evaluation layers. The first three are static analysis — they examine tool definitions structurally. The fourth (LLM) requires a configured provider and tests tools from an agent's perspective.</p>
        <div className="overflow-x-auto mt-3">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Layer</th>
                <th className="text-center px-3 py-2 text-xs font-medium text-gray-500">Checks</th>
                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">What it catches</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['Protocol', '12', 'Missing names, invalid schemas, malformed annotations'],
                ['Quality', '11', 'Vague descriptions, missing parameter docs, naming inconsistencies'],
                ['Security', '6', 'Annotation mismatches, prompt injection, SQL injection surfaces, data exfil risks'],
                ['LLM', '5+', 'Description confusion, wrong tool selection, argument hallucination, overlap ambiguity, unsafe tool activation'],
              ].map(([layer, checks, catches]) => (
                <tr key={layer} className="border-b border-gray-100 last:border-0">
                  <td className="px-3 py-2 font-medium text-gray-800">{layer}</td>
                  <td className="px-3 py-2 text-center text-gray-600">{checks}</td>
                  <td className="px-3 py-2 text-gray-600">{catches}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-gray-500 mt-3">
          Without LLM: ~29 checks per tool (static analysis only, instant evaluation). With LLM configured: ~34+ checks per tool (static + real LLM probing, adds API latency).
        </p>
      </Section>

      {/* Protocol Compliance */}
      <Section id="protocol" title="Layer 1: Protocol Compliance" expanded={expanded.has('protocol')} onToggle={toggle}>
        <p>Validates tool definitions against the MCP specification (version 2024-11-05). These are structural correctness checks — a tool that fails protocol checks may not work with any MCP client.</p>
        <RulesTable rules={PROTOCOL_RULES} />
      </Section>

      {/* Tool Quality */}
      <Section id="quality" title="Layer 2: Tool Quality" expanded={expanded.has('quality')} onToggle={toggle}>
        <p>Checks whether tool definitions are clear, consistent, and well-documented enough for an AI agent (or human) to use correctly. Tools can function without passing these, but agents will make more mistakes.</p>
        <RulesTable rules={QUALITY_RULES} />

        <h4 className="font-medium text-gray-800 mt-4">Overlap Detection</h4>
        <p>In addition to per-tool checks, the quality layer runs catalog-level overlap detection between tool pairs using a weighted combination:</p>
        <ul className="list-disc list-inside text-xs text-gray-600 space-y-1 ml-2">
          <li>30% — Name similarity (normalized edit distance)</li>
          <li>40% — Description similarity (token-level Jaccard)</li>
          <li>30% — Schema overlap (property name Jaccard)</li>
        </ul>
        <p className="text-xs text-gray-500 mt-2">Pairs exceeding the threshold (default 0.6) are flagged with rule <Code>overlap.tool_pair</Code> at Medium severity.</p>
      </Section>

      {/* Security Analysis */}
      <Section id="security" title="Layer 3: Security Analysis" expanded={expanded.has('security')} onToggle={toggle}>
        <p>Detects potential security risks in tool definitions. These checks identify patterns that could allow prompt injection, data exfiltration, or accidental destructive operations when tools are used by AI agents.</p>
        <RulesTable rules={SECURITY_RULES} />

        <h4 className="font-medium text-gray-800 mt-4">Tool Action Classification</h4>
        <p className="text-xs text-gray-500 mb-2">Security checks classify each tool into one of four categories based on its name and description:</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Action</th>
                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Verb Patterns</th>
                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Examples</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['read_only', 'get, list, search, find, read, fetch, query, show, view, describe', 'get_user, list_orders'],
                ['write', 'create, update, set, put, patch, add, modify, insert, save, edit', 'create_user, update_config'],
                ['destructive', 'delete, remove, destroy, drop, purge, clear, truncate, erase', 'delete_user, drop_table'],
                ['external_side_effect', 'send, publish, post, email, notify, deploy, broadcast, trigger', 'send_email, deploy_app'],
              ].map(([action, verbs, examples]) => (
                <tr key={action} className="border-b border-gray-100 last:border-0">
                  <td className="px-3 py-2 font-mono text-xs text-blue-700">{action}</td>
                  <td className="px-3 py-2 text-xs text-gray-600">{verbs}</td>
                  <td className="px-3 py-2 text-xs text-gray-500 font-mono">{examples}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h4 className="font-medium text-gray-800 mt-4">Annotation Consistency</h4>
        <p className="text-xs text-gray-500">The <Code>security.annotation_consistency</Code> check catches specific mismatches:</p>
        <ul className="list-disc list-inside text-xs text-gray-600 space-y-1 ml-2 mt-2">
          <li><strong>readOnlyHint: true on a non-read tool</strong> — Agents will treat write/destructive/side-effect tools as safe to call without user confirmation</li>
          <li><strong>destructiveHint: false on a destructive tool</strong> — Agents won't add safeguards for delete/drop/purge operations</li>
        </ul>
      </Section>

      {/* LLM-Assisted Evaluation */}
      <Section id="llm" title="Layer 4: LLM-Assisted Evaluation" expanded={expanded.has('llm')} onToggle={toggle}>
        <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3 mb-4">
          <p className="text-xs text-indigo-800">
            <strong>Requires configuration.</strong> These checks only run when <Code>llm.json</Code> is configured (see <Code>llm.json.example</Code>). They test tool definitions from an AI agent's perspective using a real LLM.
          </p>
        </div>

        <RulesTable rules={LLM_RULES} />

        <h4 className="font-medium text-gray-800 mt-4">How Each Check Works</h4>
        <div className="space-y-3 mt-2">
          {[
            {
              title: 'Description Clarity',
              id: 'llm.description_clarity',
              desc: 'The LLM is asked to explain what the tool does, when an agent should use it, and what it returns, then rate clarity from 1-10.',
              detail: '8-10 (pass): Agent knows exactly when and how to use it. 5-7 (warn): Agent could figure it out but description could improve. 1-4 (fail): Agent would not know when to use this tool.',
            },
            {
              title: 'Tool Selection',
              id: 'llm.tool_selection',
              desc: 'For each tool, the LLM generates a realistic user request from the tool\'s name and description. Then all tools are presented and the LLM must pick the right one.',
              detail: 'Pass: LLM selects the correct tool. Fail: LLM selects a different tool — the description isn\'t distinctive enough.',
            },
            {
              title: 'Argument Generation',
              id: 'llm.arg_generation',
              desc: 'Given a scenario and the full tool list, the LLM selects the tool and generates arguments. The generated arguments are validated against the schema.',
              detail: 'Checks: Are all required fields provided? Are there hallucinated parameters not in the schema? Do argument types match schema definitions?',
            },
            {
              title: 'Overlap Disambiguation',
              id: 'llm.tool_disambiguation',
              desc: 'For each pair of tools flagged by the static overlap detector, a scenario targeting one tool is generated. The LLM must select the correct one.',
              detail: 'Only runs when overlapping pairs exist. Pass: LLM picks the intended tool. Fail: LLM picks the other tool — descriptions are too similar.',
            },
            {
              title: 'Safety Resistance',
              id: 'llm.safety_resistance',
              desc: 'For each destructive/write/side-effect tool, a benign read-only prompt is sent. The LLM should not select the dangerous tool.',
              detail: 'Pass: LLM correctly avoids the dangerous tool. Fail (Critical): LLM selects the dangerous tool for a benign request.',
            },
          ].map(item => (
            <div key={item.id} className="bg-gray-50 rounded-lg p-3">
              <div className="flex items-center gap-2">
                <span className="font-medium text-gray-800 text-xs">{item.title}</span>
                <Code>{item.id}</Code>
              </div>
              <p className="text-xs text-gray-600 mt-1">{item.desc}</p>
              <p className="text-xs text-gray-500 mt-1 italic">{item.detail}</p>
            </div>
          ))}
        </div>

        <h4 className="font-medium text-gray-800 mt-4">What LLM Eval Catches That Static Analysis Misses</h4>
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs">
          <p className="text-amber-800 mb-2"><strong>Example:</strong> Static analysis says tool <Code>archive_project</Code> has a description, proper schema, and correct annotations. All checks pass.</p>
          <p className="text-amber-700"><strong>LLM eval finds:</strong></p>
          <ul className="list-disc list-inside text-amber-700 space-y-1 ml-2 mt-1">
            <li>Description clarity = 4/10: "says 'archive a project' but doesn't explain what archiving means"</li>
            <li>Tool selection = FAIL: Given "back up project data," LLM selected archive_project instead of export_project</li>
            <li>Safety resistance = FAIL: Given "show me project details," LLM selected archive_project (destructive) instead of get_project</li>
          </ul>
        </div>
      </Section>

      {/* Scoring */}
      <Section id="scoring" title="Scoring & Gate Logic" expanded={expanded.has('scoring')} onToggle={toggle}>
        <h4 className="font-medium text-gray-800">Layer Weights</h4>
        <p className="text-xs text-gray-500 mb-2">When all layers are active, the default weights are:</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Layer</th>
                <th className="text-center px-3 py-2 text-xs font-medium text-gray-500">Weight</th>
              </tr>
            </thead>
            <tbody>
              {[['Protocol', '0.15'], ['Quality', '0.10'], ['Security', '0.10'], ['LLM', '0.10']].map(([l, w]) => (
                <tr key={l} className="border-b border-gray-100 last:border-0">
                  <td className="px-3 py-2 text-gray-700">{l}</td>
                  <td className="px-3 py-2 text-center text-gray-600">{w}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-gray-500 mt-2">Weights auto-normalize based on which layers are present. With three static layers only (no LLM), protocol gets ~43%, quality ~29%, security ~29%.</p>

        <h4 className="font-medium text-gray-800 mt-4">Severity Weights</h4>
        <p className="text-xs text-gray-500 mb-2">Each check result is weighted by its severity:</p>
        <div className="flex flex-wrap gap-2">
          {[
            ['Critical', '5.0', 'bg-red-100 text-red-700'],
            ['High', '3.0', 'bg-orange-100 text-orange-700'],
            ['Medium', '2.0', 'bg-yellow-100 text-yellow-700'],
            ['Low', '1.0', 'bg-blue-100 text-blue-700'],
            ['Info', '0.5', 'bg-gray-100 text-gray-600'],
          ].map(([name, weight, cls]) => (
            <div key={name} className={`px-2.5 py-1 rounded text-xs font-medium ${cls}`}>
              {name}: {weight}
            </div>
          ))}
        </div>

        <h4 className="font-medium text-gray-800 mt-4">Per-Layer Score Formula</h4>
        <div className="bg-gray-50 rounded-lg p-3 font-mono text-xs text-gray-700">
          score = 100 × weighted_pass / (weighted_pass + weighted_fail + weighted_warn × 0.5)
        </div>

        <h4 className="font-medium text-gray-800 mt-4">Gate Logic</h4>
        <p className="text-xs text-gray-500">The evaluation gate passes when both conditions are met:</p>
        <ol className="list-decimal list-inside text-xs text-gray-600 space-y-1 ml-2 mt-2">
          <li>Overall score &ge; threshold (default <strong>70.0</strong>)</li>
          <li>No critical failures in <Code>protocol</Code> or <Code>security</Code> layers</li>
        </ol>
        <p className="text-xs text-gray-500 mt-2">A single critical security failure gates the entire report regardless of the overall score.</p>
      </Section>

      {/* Configuration */}
      <Section id="config" title="LLM Configuration" expanded={expanded.has('config')} onToggle={toggle}>
        <p>Create a <Code>llm.json</Code> file to enable LLM-assisted evaluation. See <Code>llm.json.example</Code> for the full format. Secrets go in <Code>.env</Code> and are referenced via the <Code>_env</Code> suffix convention. When not configured, the LLM layer is skipped entirely and scores auto-normalize.</p>

        <h4 className="font-medium text-gray-800 mt-3">Supported Providers</h4>
        <div className="space-y-3 mt-2">
          {[
            { name: 'OpenAI', config: '{"provider": "openai", "model": "gpt-4o", "api_key_env": "OPENAI_API_KEY"}' },
            { name: 'Anthropic', config: '{"provider": "anthropic", "model": "claude-sonnet-4-20250514", "api_key_env": "ANTHROPIC_API_KEY"}' },
            { name: 'VertexAI (Gemini)', config: '{"provider": "vertexai", "model": "gemini-2.5-flash", "project_env": "GCP_PROJECT", "location_env": "GCP_LOCATION"}' },
            { name: 'Claude on VertexAI', config: '{"provider": "anthropic-vertex", "model": "claude-sonnet-4-20250514", "project_env": "GCP_PROJECT", "location_env": "GCP_LOCATION"}' },
          ].map(provider => (
            <div key={provider.name} className="bg-gray-50 rounded-lg p-3">
              <div className="font-medium text-gray-800 text-xs mb-1">{provider.name}</div>
              <div className="font-mono text-[11px] text-gray-600 whitespace-pre-wrap break-all">
                {provider.config}
              </div>
            </div>
          ))}
        </div>

        <p className="text-xs text-gray-500 mt-3">
          For OpenAI-compatible endpoints (Azure, Ollama, vLLM), add <Code>"base_url"</Code> to your config in llm.json.
        </p>

        <h4 className="font-medium text-gray-800 mt-4">Example llm.json</h4>
        <p className="text-xs text-gray-500 mt-2">
          Create a <Code>llm.json</Code> file in the project root.
          See <Code>llm.json.example</Code> for a complete template with all providers.
        </p>
        <div className="bg-gray-50 rounded-lg p-3 mt-2 font-mono text-[11px] text-gray-600 whitespace-pre">{`{
  "default": "gemini-flash",
  "configs": {
    "gemini-flash": {
      "provider": "vertexai",
      "model": "gemini-2.5-flash",
      "project_env": "GCP_PROJECT",
      "location_env": "GCP_LOCATION"
    },
    "claude": {
      "provider": "anthropic",
      "model": "claude-sonnet-4-20250514",
      "api_key_env": "ANTHROPIC_API_KEY"
    }
  }
}`}</div>
        <ul className="list-disc list-inside text-xs text-gray-600 space-y-1 ml-2 mt-2">
          <li><strong><Code>_env</Code> suffix convention</strong> — Keys ending in <Code>_env</Code> reference environment variable names from <Code>.env</Code>, not raw values</li>
          <li><strong><Code>default</Code></strong> — The LLM config used for single-model evaluation</li>
          <li><strong>LLM selector</strong> — When 2+ configs exist, a dropdown appears in the evaluation panel to choose which LLM(s) to run</li>
          <li><strong>Multi-LLM evaluation</strong> — Runs all selected configs in parallel and returns comparative results</li>
        </ul>
        <p className="text-xs text-gray-500 mt-2">
          Supported providers: <Code>openai</Code>, <Code>anthropic</Code>, <Code>vertexai</Code>, <Code>anthropic-vertex</Code>.
          Available configs are listed via <Code>GET /api/llm-configs</Code>.
        </p>
      </Section>

      {/* MCP Tool Guidelines */}
      <Section id="guidelines" title="MCP Tool Guidelines" expanded={expanded.has('guidelines')} onToggle={toggle}>
        <p>
          Best practices and specification requirements for authoring high-quality MCP tool definitions. Following these guidelines
          helps AI agents reliably discover, select, and use your tools.
        </p>

        <h4 className="font-medium text-gray-800 mt-4">Specification Requirements</h4>
        <p className="text-xs text-gray-500 mt-1">
          Key structural requirements from the{' '}
          <a href="https://modelcontextprotocol.io/specification/2024-11-05/server/tools" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">
            MCP specification (2024-11-05)
          </a>:
        </p>
        <div className="space-y-2 mt-2">
          {[
            { label: 'Tool definition', detail: 'Every tool must have name (string), description (string), and inputSchema (JSON Schema object)' },
            { label: 'Schema structure', detail: 'inputSchema must be type: "object" with a properties map. Each property should have a type.' },
            { label: 'Annotations', detail: 'Tools should declare readOnlyHint, destructiveHint, idempotentHint, and openWorldHint as boolean annotations to guide agent behavior.' },
            { label: 'Transport', detail: 'Communication uses JSON-RPC 2.0 over streamable HTTP. Servers expose tools/list and tools/call methods.' },
            { label: 'Required fields', detail: 'The required array should list properties that must be provided. Only reference properties that exist in the schema.' },
          ].map(item => (
            <div key={item.label} className="bg-gray-50 rounded-lg p-2.5">
              <span className="font-medium text-gray-800 text-xs">{item.label}:</span>
              <span className="text-xs text-gray-600 ml-1">{item.detail}</span>
            </div>
          ))}
        </div>

        <h4 className="font-medium text-gray-800 mt-4">Tool Authoring Best Practices</h4>
        <p className="text-xs text-gray-500 mt-1">
          Guidance from the{' '}
          <a href="https://modelcontextprotocol.io/docs/concepts/tools" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">
            MCP tool authoring documentation
          </a>:
        </p>
        <div className="space-y-2 mt-2">
          {[
            { category: 'Naming', tips: 'Use verb-first names (get_user, create_order). Be consistent with casing (snake_case or camelCase). Avoid generic names like doAction or process.' },
            { category: 'Descriptions', tips: 'Start with an action verb. Be specific about what the tool does, when to use it, and what it returns. Differentiate clearly from similar tools on the same server.' },
            { category: 'Schemas', tips: 'Type every property. Mark required parameters explicitly. Describe each parameter with a clear description. Use enums for constrained values.' },
            { category: 'Annotations', tips: 'Always set readOnlyHint and destructiveHint. Match annotations to actual behavior — a write tool must not claim readOnlyHint: true.' },
            { category: 'Security', tips: 'Avoid raw SQL or shell command parameters. Validate URLs and file paths. Guard destructive operations with clear warnings in descriptions.' },
          ].map(item => (
            <div key={item.category} className="bg-indigo-50 rounded-lg p-2.5">
              <span className="font-medium text-indigo-800 text-xs">{item.category}:</span>
              <span className="text-xs text-indigo-700 ml-1">{item.tips}</span>
            </div>
          ))}
        </div>

        <h4 className="font-medium text-gray-800 mt-4">Common Anti-Patterns</h4>
        <div className="overflow-x-auto mt-2">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Anti-Pattern</th>
                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Problem</th>
                <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Fix</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['Vague description', 'LLM can\'t distinguish tools', 'Be specific: what it does, when to use it, what it returns'],
                ['Missing annotations', 'Agents skip safety checks', 'Set readOnlyHint + destructiveHint on every tool'],
                ['Overlapping names', 'Disambiguation failures', 'Differentiate via description and distinct naming'],
                ['Unconstrained strings', 'SQL/prompt injection risk', 'Add enums, patterns, or descriptions to constrain input'],
                ['No required fields', 'Hallucinated arguments', 'Mark required parameters explicitly in the schema'],
              ].map(([pattern, problem, fix]) => (
                <tr key={pattern} className="border-b border-gray-100 last:border-0">
                  <td className="px-3 py-2 text-xs font-medium text-gray-700">{pattern}</td>
                  <td className="px-3 py-2 text-xs text-gray-600">{problem}</td>
                  <td className="px-3 py-2 text-xs text-gray-600">{fix}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mt-4 text-xs">
          <p className="text-blue-800">
            <strong>Sources:</strong>{' '}
            <a href="https://modelcontextprotocol.io/specification/2024-11-05/server/tools" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">
              MCP Specification — Tools
            </a>{' · '}
            <a href="https://modelcontextprotocol.io/docs/concepts/tools" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">
              MCP Docs — Tool Concepts
            </a>
          </p>
        </div>
      </Section>
    </div>
  )
}

const PROTOCOL_RULES = [
  { id: 'protocol.name_present', description: 'Tool has a name field that is a non-null string', severity: 'Critical', status: 'pass / fail' },
  { id: 'protocol.name_non_empty', description: 'Name is non-empty and contains no spaces', severity: 'Critical / High', status: 'pass / fail' },
  { id: 'protocol.description_present', description: 'Tool has a string description field', severity: 'Medium / High', status: 'pass / warn / fail' },
  { id: 'protocol.input_schema_valid', description: 'inputSchema is a dict with type: "object"', severity: 'High / Medium', status: 'pass / warn / fail / skip' },
  { id: 'protocol.properties_valid', description: 'inputSchema.properties is a valid object (not a list, not null)', severity: 'High', status: 'pass / fail' },
  { id: 'protocol.property_is_object', description: 'Each entry in properties is an object (not a string or array)', severity: 'High', status: 'fail (per property)' },
  { id: 'protocol.property_has_type', description: 'Each property has type, anyOf, oneOf, allOf, or $ref', severity: 'Low', status: 'warn (per property)' },
  { id: 'protocol.required_valid', description: 'required array only references properties that actually exist', severity: 'High', status: 'pass / fail / skip' },
  { id: 'protocol.annotation_{key}_bool', description: 'Annotation hints (readOnlyHint, destructiveHint, idempotentHint, openWorldHint) are boolean', severity: 'Medium', status: 'fail (per key)' },
  { id: 'protocol.annotations_present', description: 'Annotations dict exists on the tool', severity: 'Info', status: 'skip' },
  { id: 'protocol.additional_properties', description: 'Schema declares additionalProperties to control extra fields', severity: 'Low', status: 'pass / warn / skip' },
]

const QUALITY_RULES = [
  { id: 'quality.desc_actionable', description: 'Description starts with an action verb (get, create, search, list, update, delete, etc.)', severity: 'High / Medium', status: 'pass / warn / fail' },
  { id: 'quality.desc_adequate_length', description: 'Description is longer than 20 characters', severity: 'High / Medium', status: 'pass / warn / fail' },
  { id: 'quality.desc_no_filler', description: 'Description does not start with generic filler ("this tool", "a tool that", "allows you to")', severity: 'Low', status: 'pass / warn' },
  { id: 'quality.desc_explains_usage', description: 'Description exceeds 50 characters, providing enough context for usage', severity: 'Low', status: 'pass / warn' },
  { id: 'quality.param_all_described', description: 'Every parameter in properties has a description field', severity: 'Medium', status: 'pass / warn / skip' },
  { id: 'quality.param_all_typed', description: 'Every parameter has type, anyOf, or oneOf defined', severity: 'Medium', status: 'pass / warn / skip' },
  { id: 'quality.naming_consistent', description: 'Tool name follows a consistent convention (snake_case or camelCase)', severity: 'Medium', status: 'pass / warn' },
  { id: 'quality.naming_verb_prefix', description: 'Tool name starts with an action verb (get_, list_, create_, update_, delete_, etc.)', severity: 'Low', status: 'pass / warn' },
  { id: 'quality.annotation_hints', description: 'Tool includes both readOnlyHint and destructiveHint in annotations', severity: 'Low', status: 'pass / warn' },
]

const SECURITY_RULES = [
  { id: 'security.annotation_consistency', description: 'Annotation hints match the tool\'s actual behavior', severity: 'Critical / High', status: 'pass / fail' },
  { id: 'security.destructive_guard', description: 'Destructive tools (delete, remove, drop, purge) have annotations defined', severity: 'High', status: 'pass / fail' },
  { id: 'security.prompt_injection', description: 'Description does not contain prompt injection patterns', severity: 'Medium', status: 'pass / fail' },
  { id: 'security.data_exfil', description: 'No parameters named url, endpoint, webhook, callback, or redirect', severity: 'Medium', status: 'pass / fail' },
  { id: 'security.sql_injection', description: 'No unconstrained string params named query, sql, command, expression, or filter', severity: 'High', status: 'pass / fail' },
  { id: 'security.broad_permissions', description: 'Description does not contain phrases like "execute any", "run any", "arbitrary", "unrestricted"', severity: 'High', status: 'pass / fail' },
]

const LLM_RULES = [
  { id: 'llm.description_clarity', description: 'LLM rates description clarity on a 1-10 scale', severity: 'High / Medium', status: 'pass (8+) / warn (5-7) / fail (<5) / skip' },
  { id: 'llm.tool_selection', description: 'LLM correctly selects this tool from the full list given an auto-generated scenario', severity: 'High', status: 'pass / fail / skip' },
  { id: 'llm.arg_generation', description: 'LLM generates valid arguments matching the tool\'s schema', severity: 'High / Medium', status: 'pass / warn / fail / skip' },
  { id: 'llm.tool_disambiguation', description: 'LLM correctly distinguishes between overlapping tool pairs', severity: 'High / Medium', status: 'pass / fail / warn / skip' },
  { id: 'llm.safety_resistance', description: 'Benign prompts do not trigger selection of destructive/write tools', severity: 'Critical', status: 'pass / fail / skip' },
]
