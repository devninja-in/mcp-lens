from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

MCP_KNOWN_CAPABILITIES = [
    "tools",
    "resources",
    "prompts",
    "logging",
    "completions",
    "experimental",
]

CATEGORIZATION_PROMPT = """Analyze these MCP server tools and categorize them into functional groups.

Tools:
{tool_list}

Return ONLY a JSON object with this exact structure (no markdown, no explanation):
{{"categories": {{"Category Name": ["tool_name_1", "tool_name_2"]}}}}

Rules:
- Every tool must appear in exactly one category
- Use clear, concise category names (e.g. "User Management", "Data Access", "File Operations")
- Group by functional purpose, not by naming convention
- Aim for 3-8 categories depending on tool count"""


DETAILED_CATEGORIZATION_PROMPT = """\
Analyze these MCP server tools and categorize them into functional capability groups.
For each category, provide a clear description of what that capability covers
and which tools belong to it.

Tools:
{tool_list}

Return ONLY a JSON object with this exact structure (no markdown, no explanation):
{{"categories": {{
  "Category Name": {{
    "description": "A 1-2 sentence description of what this capability group does and when you would use these tools.",
    "tools": ["tool_name_1", "tool_name_2"]
  }}
}}}}

Rules:
- Every tool must appear in exactly one category
- Use clear, descriptive category names (e.g. "User Management", "Data Access", "File Operations")
- Group by functional purpose, not by naming convention
- Aim for 3-8 categories depending on tool count
- Descriptions should explain the business capability, not just list what the tools do
- Mention key use cases or workflows in the description"""


def diff_tool_inventories(tools_a: list[dict], tools_b: list[dict]) -> dict:
    names_a = {t.get("name", "") for t in tools_a}
    names_b = {t.get("name", "") for t in tools_b}
    return {
        "only_a": sorted(names_a - names_b),
        "only_b": sorted(names_b - names_a),
        "common": sorted(names_a & names_b),
        "count_a": len(names_a),
        "count_b": len(names_b),
    }


def compare_capabilities(init_a: dict | None, init_b: dict | None) -> dict | None:
    if init_a is None or init_b is None:
        return None

    result_a = init_a.get("result", {})
    result_b = init_b.get("result", {})
    caps_a = result_a.get("capabilities", {})
    caps_b = result_b.get("capabilities", {})

    all_caps = sorted(set(list(caps_a.keys()) + list(caps_b.keys()) + MCP_KNOWN_CAPABILITIES))
    matrix = []
    for cap in all_caps:
        matrix.append(
            {
                "capability": cap,
                "server_a": cap in caps_a,
                "server_b": cap in caps_b,
            }
        )

    return {
        "server_a": {
            "serverInfo": result_a.get("serverInfo", {}),
            "capabilities": caps_a,
        },
        "server_b": {
            "serverInfo": result_b.get("serverInfo", {}),
            "capabilities": caps_b,
        },
        "capability_matrix": matrix,
    }


async def categorize_tools(tools: list[dict], adapter: Any) -> dict[str, list[str]]:
    tool_lines = []
    for t in tools:
        name = t.get("name", "")
        desc = (t.get("description") or "").strip()
        tool_lines.append(f"- {name}: {desc}" if desc else f"- {name}")
    tool_list = "\n".join(tool_lines)
    prompt = CATEGORIZATION_PROMPT.format(tool_list=tool_list)

    response = await adapter.generate_answer(None, prompt)
    try:
        start = response.index("{")
        end = response.rindex("}") + 1
        parsed = json.loads(response[start:end])
        categories: dict[str, list[str]] = parsed.get("categories", {})
        return categories
    except (ValueError, json.JSONDecodeError):
        logger.warning("Failed to parse LLM categorization response")
        return {}


async def categorize_tools_detailed(tools: list[dict], adapter: Any) -> dict[str, dict]:
    tool_lines = []
    for t in tools:
        name = t.get("name", "")
        desc = (t.get("description") or "").strip()
        tool_lines.append(f"- {name}: {desc}" if desc else f"- {name}")
    tool_list = "\n".join(tool_lines)
    prompt = DETAILED_CATEGORIZATION_PROMPT.format(tool_list=tool_list)

    response = await adapter.generate_answer(None, prompt)
    try:
        start = response.index("{")
        end = response.rindex("}") + 1
        parsed = json.loads(response[start:end])
        categories: dict[str, dict] = parsed.get("categories", {})
        return categories
    except (ValueError, json.JSONDecodeError):
        logger.warning("Failed to parse LLM detailed categorization response")
        return {}


def build_category_coverage(
    categories_a: dict[str, list[str]],
    categories_b: dict[str, list[str]],
) -> list[dict]:
    all_cats = sorted(set(list(categories_a.keys()) + list(categories_b.keys())))
    result = []
    for cat in all_cats:
        a_tools = categories_a.get(cat, [])
        b_tools = categories_b.get(cat, [])
        result.append(
            {
                "category": cat,
                "server_a_tools": sorted(a_tools),
                "server_b_tools": sorted(b_tools),
                "server_a_count": len(a_tools),
                "server_b_count": len(b_tools),
            }
        )
    return result


def _diff_dicts(a: Any, b: Any, path: str = "$") -> list[dict]:
    diffs: list[dict] = []
    if type(a) is not type(b) and not (isinstance(a, bool | int) and isinstance(b, bool | int)):
        diffs.append({"path": path, "server_a": a, "server_b": b})
        return diffs
    if isinstance(a, dict):
        all_keys = sorted(set(list(a.keys()) + list(b.keys())))
        for key in all_keys:
            child_path = f"{path}.{key}"
            if key not in a:
                diffs.append({"path": child_path, "server_a": None, "server_b": b[key]})
            elif key not in b:
                diffs.append({"path": child_path, "server_a": a[key], "server_b": None})
            else:
                diffs.extend(_diff_dicts(a[key], b[key], child_path))
    elif isinstance(a, list):
        if a != b:
            diffs.append({"path": path, "server_a": a, "server_b": b})
    elif a != b:
        diffs.append({"path": path, "server_a": a, "server_b": b})
    return diffs


def diff_schemas(tools_a: list[dict], tools_b: list[dict], common_names: list[str]) -> list[dict]:
    map_a = {t["name"]: t.get("inputSchema", {}) for t in tools_a}
    map_b = {t["name"]: t.get("inputSchema", {}) for t in tools_b}

    results = []
    for name in sorted(common_names):
        schema_a = map_a.get(name, {})
        schema_b = map_b.get(name, {})
        differences = _diff_dicts(schema_a, schema_b)
        results.append(
            {
                "tool_name": name,
                "identical": len(differences) == 0,
                "differences": differences,
                "schema_a": schema_a,
                "schema_b": schema_b,
            }
        )
    return results


def compare_eval_scores(report_a: dict | None, report_b: dict | None) -> dict:
    def _extract(report: dict | None) -> tuple[float | None, dict[str, float | None]]:
        if report is None:
            return None, {}
        overall = report.get("overall_score")
        layers_data = report.get("layers", {})
        layer_scores = {}
        for layer_name, layer_data in layers_data.items():
            layer_scores[layer_name] = layer_data.get("score")
        return overall, layer_scores

    score_a, layers_a = _extract(report_a)
    score_b, layers_b = _extract(report_b)

    all_layers = sorted(set(list(layers_a.keys()) + list(layers_b.keys())))
    layers = {}
    for layer in all_layers:
        layers[layer] = {
            "server_a": layers_a.get(layer),
            "server_b": layers_b.get(layer),
        }

    return {
        "server_a_score": score_a,
        "server_b_score": score_b,
        "layers": layers,
    }


async def run_comparison(
    server_a_name: str,
    server_b_name: str,
    tools_a: list[dict],
    tools_b: list[dict],
    init_a: dict | None,
    init_b: dict | None,
    eval_a: dict | None,
    eval_b: dict | None,
    adapter: Any | None,
) -> dict:
    inventory = diff_tool_inventories(tools_a, tools_b)
    capabilities = compare_capabilities(init_a, init_b)
    eval_scores = compare_eval_scores(eval_a, eval_b)
    schema_diffs = diff_schemas(tools_a, tools_b, inventory["common"])

    categories: list[dict] = []
    if adapter is not None:
        try:
            cats_a = await categorize_tools(tools_a, adapter)
            cats_b = await categorize_tools(tools_b, adapter)
            categories = build_category_coverage(cats_a, cats_b)
        except Exception:
            logger.exception("LLM categorization failed")

    return {
        "server_a": server_a_name,
        "server_b": server_b_name,
        "timestamp": datetime.now(UTC).isoformat(),
        "tool_inventory": inventory,
        "capabilities": capabilities,
        "categories": categories,
        "eval_scores": eval_scores,
        "schema_diffs": schema_diffs,
    }
