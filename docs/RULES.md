# Evaluation Rules Reference

Complete reference for all checks in the MCP Lens evaluation framework. Each rule runs against every tool definition fetched from an MCP server.

---

## Layer 1: Protocol Compliance

Validates tool definitions against the [MCP specification](https://modelcontextprotocol.io/) (version 2024-11-05). These are structural correctness checks — a tool that fails protocol checks may not work with any MCP client.

| Rule ID | What it checks | Severity | Status |
|---------|---------------|----------|--------|
| `protocol.name_present` | Tool has a `name` field that is a non-null string | Critical | pass / fail |
| `protocol.name_non_empty` | Name is non-empty and contains no spaces | Critical / High | pass / fail |
| `protocol.description_present` | Tool has a string `description` field | Medium / High | pass / warn / fail |
| `protocol.input_schema_valid` | `inputSchema` is a dict with `type: "object"` | High / Medium | pass / warn / fail / skip |
| `protocol.properties_valid` | `inputSchema.properties` is a valid object (not a list, not null) | High | pass / fail |
| `protocol.property_is_object` | Each entry in `properties` is an object (not a string or array) | High | fail (per property) |
| `protocol.property_has_type` | Each property has `type`, `anyOf`, `oneOf`, `allOf`, or `$ref` | Low | warn (per property) |
| `protocol.required_valid` | `required` array only references properties that actually exist | High | pass / fail / skip |
| `protocol.annotation_{key}_bool` | Annotation hints (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) are boolean | Medium | fail (per key) |
| `protocol.annotations_present` | Annotations dict exists on the tool | Info | skip |
| `protocol.additional_properties` | Schema declares `additionalProperties` to control extra fields | Low | pass / warn / skip |

### Examples

A tool that fails `protocol.name_non_empty`:
```json
{"name": "", "description": "..."}
```

A tool that fails `protocol.input_schema_valid`:
```json
{"name": "search", "inputSchema": ["not", "an", "object"]}
```

---

## Layer 2: Tool Quality

Checks whether tool definitions are clear, consistent, and well-documented enough for an AI agent (or human) to use correctly. These are best-practice recommendations — tools can function without passing these, but agents will make more mistakes.

| Rule ID | What it checks | Severity | Status |
|---------|---------------|----------|--------|
| `quality.desc_actionable` | Description starts with an action verb (get, create, search, list, update, delete, etc.) | High / Medium | pass / warn / fail |
| `quality.desc_adequate_length` | Description is longer than 20 characters | High / Medium | pass / warn / fail |
| `quality.desc_no_filler` | Description does not start with generic filler ("this tool", "a tool that", "allows you to") | Low | pass / warn |
| `quality.desc_explains_usage` | Description exceeds 50 characters, providing enough context for usage | Low | pass / warn |
| `quality.param_all_described` | Every parameter in `properties` has a `description` field | Medium | pass / warn / skip |
| `quality.param_all_typed` | Every parameter has `type`, `anyOf`, or `oneOf` defined | Medium | pass / warn / skip |
| `quality.naming_consistent` | Tool name follows a consistent convention (snake_case or camelCase) | Medium | pass / warn |
| `quality.naming_verb_prefix` | Tool name starts with an action verb (get_, list_, create_, update_, delete_, etc.) | Low | pass / warn |
| `quality.annotation_hints` | Tool includes both `readOnlyHint` and `destructiveHint` in annotations | Low | pass / warn |

### Overlap Detection

In addition to per-tool checks, the quality layer runs catalog-level overlap detection:

| Rule ID | What it checks | Severity | Status |
|---------|---------------|----------|--------|
| `overlap.tool_pair` | Two tools have suspiciously similar names, descriptions, or schemas | Medium | warn |

Overlap scoring uses a weighted combination:
- 30% — Name similarity (normalized edit distance)
- 40% — Description similarity (token-level Jaccard)
- 30% — Schema overlap (property name Jaccard)

Pairs exceeding the threshold (default 0.6) are flagged. Details include the similarity score and both tool names.

### Examples

A tool that fails `quality.desc_actionable`:
```json
{"name": "user_data", "description": "user data from the database"}
```
**Fix:** Start with a verb: "Retrieve user data from the database by user ID"

A pair that triggers `overlap.tool_pair`:
```json
[
  {"name": "search_customers", "description": "Search for customers by name or email"},
  {"name": "find_customers", "description": "Find customers by name or email address"}
]
```
**Fix:** Merge into one tool, or differentiate their purposes clearly.

---

## Layer 3: Security Analysis

Detects potential security risks in tool definitions. These checks identify patterns that could allow prompt injection, data exfiltration, or accidental destructive operations when tools are used by AI agents.

| Rule ID | What it checks | Severity | Status |
|---------|---------------|----------|--------|
| `security.annotation_consistency` | Annotation hints match the tool's actual behavior | Critical / High | pass / fail |
| `security.destructive_guard` | Destructive tools (delete, remove, drop, purge) have annotations defined | High | pass / fail |
| `security.prompt_injection` | Description does not contain prompt injection patterns | Medium | pass / fail |
| `security.data_exfil` | No parameters named `url`, `endpoint`, `webhook`, `callback`, or `redirect` | Medium | pass / fail |
| `security.sql_injection` | No unconstrained string params named `query`, `sql`, `command`, `expression`, or `filter` | High | pass / fail |
| `security.broad_permissions` | Description does not contain phrases like "execute any", "run any", "arbitrary", "unrestricted" | High | pass / fail |

### Tool Action Classification

Security checks classify each tool into one of four action categories based on its name and description:

| Action | Verb patterns | Example tools |
|--------|--------------|---------------|
| `read_only` | get, list, search, find, read, fetch, query, show, view, describe | `get_user`, `list_orders` |
| `write` | create, update, set, put, patch, add, modify, insert, save, edit | `create_user`, `update_config` |
| `destructive` | delete, remove, destroy, drop, purge, clear, truncate, erase | `delete_user`, `drop_table` |
| `external_side_effect` | send, publish, post, email, notify, deploy, broadcast, trigger | `send_email`, `deploy_app` |

### Annotation Consistency Detail

The `security.annotation_consistency` check catches three specific mismatches:

**1. `readOnlyHint: true` on a non-read tool**

When a tool is classified as `write`, `destructive`, or `external_side_effect` but claims `readOnlyHint: true`, agents will treat it as safe to call without user confirmation.

- Write tool: "The tool modifies data (create/update/set), but `readOnlyHint: true` tells agents it's safe to call freely. Agents may create or modify resources without asking for confirmation."
- Destructive tool: "The tool performs destructive operations (delete/remove/drop), but `readOnlyHint: true` tells agents it's safe to call freely. Agents may permanently delete data without user confirmation."
- External side-effect tool: "The tool triggers external side effects (send/publish/deploy), but `readOnlyHint: true` tells agents it's safe to call freely. Agents may send emails, trigger deployments, or perform other irreversible external actions without asking."

**2. `destructiveHint: false` on a destructive tool**

When a tool named `delete_*`, `drop_*`, etc. has `destructiveHint: false`, agents won't add safeguards.

### Examples

A tool that fails `security.annotation_consistency`:
```json
{
  "name": "delete_all_records",
  "description": "Delete all records from the database",
  "annotations": {"readOnlyHint": true}
}
```

A tool that fails `security.sql_injection`:
```json
{
  "name": "run_query",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "SQL query to execute"}
    }
  }
}
```
**Fix:** Add `enum` or `pattern` constraints, or use parameterized query parameters instead.

---

## Layer 4: LLM-Assisted Evaluation

**Requires configuration.** These checks only run when `EVAL_LLM_PROVIDER` is set in `.env`. They test tool definitions from an AI agent's perspective using a real LLM to probe for usability issues that static analysis cannot detect.

### Configuration

```bash
# .env — choose one provider
EVAL_LLM_PROVIDER=openai          # or: anthropic, vertexai, anthropic-vertex
EVAL_LLM_MODEL=gpt-4o             # model name
EVAL_LLM_API_KEY=sk-...           # API key (required for openai/anthropic)

# VertexAI with Gemini
EVAL_LLM_PROJECT=my-gcp-project   # GCP project ID
EVAL_LLM_LOCATION=us-central1     # GCP region

# Claude on VertexAI (uses service account / ADC)
# EVAL_LLM_PROVIDER=anthropic-vertex
# EVAL_LLM_MODEL=claude-sonnet-4-20250514
# EVAL_LLM_PROJECT=my-gcp-project
# EVAL_LLM_LOCATION=us-east5
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# OpenAI-compatible endpoints (Azure, Ollama, vLLM, etc.)
EVAL_LLM_BASE_URL=https://...     # custom base URL
```

When `EVAL_LLM_PROVIDER` is not set or empty, the entire LLM layer is skipped. The evaluation runs with three static layers only, and scores auto-normalize.

### LLM Checks

| Rule ID | What it checks | Severity | Status |
|---------|---------------|----------|--------|
| `llm.description_clarity` | LLM rates description clarity on a 1-10 scale | High / Medium | pass (8+) / warn (5-7) / fail (<5) / skip |
| `llm.tool_selection` | LLM correctly selects this tool from the full list given an auto-generated scenario | High | pass / fail / skip |
| `llm.arg_generation` | LLM generates valid arguments matching the tool's schema | — | pass / skip |
| `llm.arg_generation.missing.{param}` | LLM failed to provide a required argument | High | fail |
| `llm.arg_generation.hallucinated.{param}` | LLM invented an argument not in the schema | Medium | warn |
| `llm.arg_generation.type.{param}` | LLM provided wrong type for an argument | Medium | warn |
| `llm.tool_disambiguation` | LLM correctly distinguishes between overlapping tool pairs | High / Medium | pass / fail / warn / skip |
| `llm.safety_resistance` | Benign prompts do not trigger selection of destructive/write tools | Critical | pass / fail / skip |

### How Each Check Works

#### Description Clarity (`llm.description_clarity`)

The LLM is asked to explain what the tool does, when an agent should use it, and what it returns, then rate clarity from 1-10.

- **8-10** (pass): An agent knows exactly when and how to use it
- **5-7** (warn): An agent could figure it out but the description could improve
- **1-4** (fail): An agent would not know when to use this tool

*Runs per tool. Skips tools with no description.*

#### Tool Selection (`llm.tool_selection`)

For each tool, the LLM generates a realistic user request (scenario) from the tool's name and description. Then all tools are presented and the LLM must pick the right one.

- **Pass**: LLM selects the correct tool
- **Warn** (medium): LLM selects a different tool, but as a valid prerequisite/information-gathering step (e.g., selecting `getAccessibleResources` before `updatePage`). This indicates multi-step agent planning, not confusion.
- **Fail** (high): LLM selects a different tool — the description isn't distinctive enough

When a mismatch occurs, a follow-up check asks whether the selected tool is a reasonable prerequisite for the expected tool. If the LLM confirms it is (e.g., discovering resources before updating one), the result is downgraded to WARN. This reduces false positives from legitimate multi-step workflows.

*Runs per tool. Skips tools with no description.*

#### Argument Generation (`llm.arg_generation`)

Given a scenario and the full tool list, the LLM selects the tool and generates arguments. The generated arguments are validated against the schema:

- Are all `required` fields provided?
- Are there hallucinated parameters not in the schema?
- Do argument types match schema definitions?

*Runs per tool with properties and required fields. Skips tools without a schema.*

#### Overlap Disambiguation (`llm.tool_disambiguation`)

For each pair of tools flagged by the static overlap detector, a scenario targeting one tool is generated. The LLM must select the correct one.

- **Pass**: LLM picks the intended tool
- **Warn** (medium): LLM picks the other tool as a prerequisite step (same prerequisite detection as tool selection)
- **Fail** (high): LLM picks the other tool in the pair — descriptions are too similar

*Only runs when overlapping pairs exist. Skips otherwise.*

#### Safety Resistance (`llm.safety_resistance`)

For each destructive, write, or external-side-effect tool, a benign read-only prompt is sent (e.g., "Show me a list of all items" for a `delete_all` tool). The LLM should not select the dangerous tool.

- **Pass**: LLM correctly avoids the dangerous tool
- **Fail** (Critical): LLM selects the dangerous tool for a benign request

*Requires both dangerous tools and read-only tools in the catalog. Skips otherwise.*

### Example: What LLM Eval Catches That Static Analysis Misses

**Static analysis says:** "Tool `archive_project` has a description, proper schema, and correct annotations. All checks pass."

**LLM eval finds:**
- `llm.description_clarity` = 4/10: "The description says 'archive a project' but doesn't explain what archiving means — is it a soft delete, a move to cold storage, or an export?"
- `llm.tool_selection` = FAIL: Given "back up project data before migration," the LLM selected `archive_project` instead of `export_project`
- `llm.safety_resistance` = FAIL: Given "show me project details," the LLM selected `archive_project` (which is destructive) instead of `get_project`

---

## Scoring

### Layer Weights

When all layers are active, the default weights are:

| Layer | Weight |
|-------|--------|
| Protocol | 0.15 |
| Quality | 0.10 |
| Security | 0.10 |
| LLM | 0.10 |

Weights auto-normalize based on which layers are present. With three static layers only (no LLM), protocol gets ~43%, quality ~29%, security ~29%.

### Per-Layer Score Calculation

For each layer, the score is computed from check results weighted by severity:

```
score = 100 * weighted_pass / (weighted_pass + weighted_fail + weighted_warn * 0.5)
```

Where the weight for each check is determined by its severity level (critical=5, high=3, medium=2, low=1, info=0.5).

### Gate Logic

The evaluation gate passes when:
1. Overall score >= threshold (default 70.0), **AND**
2. No critical failures in `protocol` or `security` layers

Both conditions must be met. A single critical security failure gates the entire report regardless of the overall score.

### Customizing Weights

Pass a scoring config JSON to the CLI:

```json
{
  "layer_weights": {
    "protocol": 0.30,
    "quality": 0.20,
    "security": 0.30,
    "llm": 0.20
  },
  "gate_threshold": 80.0
}
```

```bash
mcp-lens report tools.yaml --config scoring.json
```

---

## Summary

| Without LLM | With LLM configured |
|-------------|-------------------|
| Protocol (12 checks) | Protocol (12 checks) |
| Quality (11 checks + overlap detection) | Quality (11 checks + overlap detection) |
| Security (6 checks) | Security (6 checks) |
| — | LLM: Description Clarity |
| — | LLM: Tool Selection |
| — | LLM: Argument Generation |
| — | LLM: Overlap Disambiguation |
| — | LLM: Safety Resistance |
| **~29 checks per tool** | **~34+ checks per tool** |
| Static analysis only | Static + real LLM probing |
| Instant evaluation | Adds LLM API latency |
| No API keys needed | Requires LLM provider credentials |
