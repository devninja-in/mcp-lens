"""LLM-assisted evaluation checks.

SAFETY: This module ONLY asks the LLM which tool it would select and what
arguments it would generate.  It NEVER executes tools against an MCP server.
All checks are read-only simulations with zero side effects.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .models import CheckResult, LayerResult, Severity, Status, ToolResult
from .overlap import detect_overlaps
from .security import classify_tool_action

logger = logging.getLogger(__name__)


async def _ask_llm_text(adapter: Any, prompt: str) -> str:
    result: str = await adapter.generate_answer(None, prompt)
    return result


async def _check_description_clarity(
    tools: list[dict],
    adapter: Any,
    server_description: str = "",
    ground_truth: list[dict] | None = None,
) -> list[ToolResult]:
    logger.info("Running description clarity check on %d tools", len(tools))
    results = []
    for tool in tools:
        name = tool.get("name", "<unnamed>")
        desc = (tool.get("description") or "").strip()
        schema = tool.get("inputSchema", {})

        if not desc:
            results.append(
                ToolResult(
                    tool_name=name,
                    checks=[
                        CheckResult(
                            check_id="llm.description_clarity",
                            status=Status.SKIP,
                            message="No description to evaluate",
                            tool_name=name,
                        )
                    ],
                )
            )
            continue

        server_ctx = f"Server context: {server_description}\n" if server_description else ""
        prompt = (
            f"You are evaluating an MCP tool definition for clarity.\n"
            f"{server_ctx}"
            f"Tool name: {name}\n"
            f"Description: {desc}\n"
            f"Input schema: {json.dumps(schema, indent=2)[:500]}\n\n"
            f"Rate the description clarity from 1-10 where:\n"
            f"1-4 = unclear (an AI agent would not know when to use this)\n"
            f"5-7 = adequate (an agent could figure it out but could improve)\n"
            f"8-10 = excellent (an agent knows exactly when and how to use it)\n\n"
            f"Respond with ONLY a JSON object: "
            f'{{"rating": <number>, "reason": "<one sentence>"}}'
        )

        try:
            response = await _ask_llm_text(adapter, prompt)
            match = re.search(r'"rating"\s*:\s*(\d+)', response)
            rating = int(match.group(1)) if match else 5
            reason_match = re.search(r'"reason"\s*:\s*"([^"]*)"', response)
            reason = reason_match.group(1) if reason_match else "Could not parse LLM response"

            if rating >= 8:
                status, severity = Status.PASS, Severity.INFO
            elif rating >= 5:
                status, severity = Status.WARN, Severity.MEDIUM
            else:
                status, severity = Status.FAIL, Severity.HIGH

            logger.debug("Description clarity for '%s': %d/10 (%s)", name, rating, status.value)
            results.append(
                ToolResult(
                    tool_name=name,
                    checks=[
                        CheckResult(
                            check_id="llm.description_clarity",
                            status=status,
                            message=f"Description clarity: {rating}/10 — {reason}",
                            severity=severity,
                            tool_name=name,
                            details={
                                "rating": rating,
                                "reason": reason,
                                "location": "description",
                                "current_value": desc[:100] + ("..." if len(desc) > 100 else ""),
                                "suggestion": (
                                    "Improve the description to clearly state what the tool does, "
                                    "when to use it, expected inputs, and output format."
                                )
                                if rating < 8
                                else None,
                            },
                        )
                    ],
                )
            )
        except Exception as e:
            logger.error("Description clarity check failed for '%s': %s", name, e)
            results.append(
                ToolResult(
                    tool_name=name,
                    checks=[
                        CheckResult(
                            check_id="llm.description_clarity",
                            status=Status.SKIP,
                            message=f"Description clarity test skipped (adapter error): {e}",
                            tool_name=name,
                        )
                    ],
                )
            )
    return results


async def _generate_scenario(adapter: Any, tool: dict, server_description: str = "") -> str:
    name = tool.get("name", "")
    desc = (tool.get("description") or "").strip()
    server_ctx = (
        f"This tool belongs to an MCP server described as: '{server_description}'. " if server_description else ""
    )
    prompt = (
        f"{server_ctx}"
        f"Generate a single, short user request (one sentence) that would DIRECTLY require "
        f"using a tool called '{name}' described as: '{desc}'. "
        f"The request should be specific enough that this tool is the clear first choice — "
        f"not a prerequisite or information-gathering step. "
        f"Reply with ONLY the user request, nothing else."
    )
    try:
        return await _ask_llm_text(adapter, prompt)
    except Exception:
        return f"I need to {desc.lower()}" if desc else f"Use the {name} tool"


async def _is_prerequisite_selection(
    adapter: Any,
    selected_name: str,
    expected_name: str,
    selected_desc: str,
    expected_desc: str,
    scenario: str,
) -> tuple[bool, str]:
    prompt = (
        f'A user asked: "{scenario}"\n'
        f"An AI agent selected '{selected_name}' ({selected_desc}) "
        f"instead of '{expected_name}' ({expected_desc}).\n\n"
        f"Is '{selected_name}' a reasonable prerequisite or information-gathering step "
        f"that an agent would need before calling '{expected_name}'? "
        f"For example, discovering available resources before updating one, or listing "
        f"items before operating on a specific one.\n\n"
        f"Respond with ONLY a JSON object: "
        f'{{"prerequisite": true, "reason": "..."}} or {{"prerequisite": false, "reason": "..."}}'
    )
    try:
        response = await _ask_llm_text(adapter, prompt)
        match = re.search(r'"prerequisite"\s*:\s*(true|false)', response, re.IGNORECASE)
        reason_match = re.search(r'"reason"\s*:\s*"([^"]*)"', response)
        reason = reason_match.group(1) if reason_match else ""
        is_prereq = match is not None and match.group(1).lower() == "true"
        return is_prereq, reason
    except Exception:
        return False, ""


def _enrich_scenario(scenario: str, server_description: str) -> str:
    if not server_description:
        return scenario
    return f"[Context: You are using an MCP server that {server_description}]\n{scenario}"


def _get_ground_truth_for_tool(tool_name: str, ground_truth: list[dict] | None) -> list[dict]:
    if not ground_truth:
        return []
    return [tc for tc in ground_truth if tool_name in (tc.get("expected_tool_selection") or [])]


async def _suggest_improved_description(
    adapter: Any,
    tool: dict,
    scenario: str,
    selected_name: str,
    expected_name: str,
    server_description: str = "",
) -> str | None:
    expected_desc = (tool.get("description") or "").strip()
    server_ctx = f"Server context: {server_description}\n" if server_description else ""
    prompt = (
        f'An AI agent was given this request: "{scenario}"\n'
        f"{server_ctx}"
        f"The expected tool was '{expected_name}' with description: \"{expected_desc}\"\n"
        f"But the agent selected '{selected_name}' instead.\n\n"
        f"Suggest an improved description for '{expected_name}' that would make an AI agent "
        f"correctly select it for this type of request. The description should:\n"
        f"1. Clearly state what the tool does\n"
        f"2. Specify when to use it (vs similar tools)\n"
        f"3. Be concise but unambiguous\n\n"
        f"Respond with ONLY the improved description text, nothing else."
    )
    try:
        return await _ask_llm_text(adapter, prompt)
    except Exception as e:
        logger.warning("Failed to generate description suggestion for '%s': %s", expected_name, e)
        return None


async def _check_tool_selection(
    tools: list[dict],
    adapter: Any,
    server_description: str = "",
    ground_truth: list[dict] | None = None,
) -> list[ToolResult]:
    logger.info("Running tool selection check on %d tools", len(tools))
    results = []
    for tool in tools:
        name = tool.get("name", "<unnamed>")
        desc = (tool.get("description") or "").strip()

        if not desc:
            results.append(
                ToolResult(
                    tool_name=name,
                    checks=[
                        CheckResult(
                            check_id="llm.tool_selection",
                            status=Status.SKIP,
                            message="No description — cannot generate test scenario",
                            tool_name=name,
                        )
                    ],
                )
            )
            continue

        try:
            gt_cases = _get_ground_truth_for_tool(name, ground_truth)
            if gt_cases:
                logger.debug("Using %d ground truth test cases for '%s'", len(gt_cases), name)
                gt_prompts: list[tuple[str, list[str]]] = []
                for tc in gt_cases:
                    expected_tools = tc.get("expected_tool_selection", [name])
                    for prompt in tc.get("prompts", []):
                        gt_prompts.append((prompt, expected_tools))
                checks: list[CheckResult] = []
                for scenario, expected_tools in gt_prompts:
                    enriched = _enrich_scenario(scenario, server_description)
                    selection = await adapter.select_tool(tools, enriched)
                    selected = selection.get("tool_name", "")
                    sel_args = selection.get("arguments", {})
                    if selected in expected_tools:
                        checks.append(
                            CheckResult(
                                check_id="llm.tool_selection",
                                status=Status.PASS,
                                message=f"LLM correctly selected '{selected}' for: \"{scenario[:80]}\"",
                                tool_name=name,
                                details={
                                    "scenario": scenario,
                                    "selected": selected,
                                    "scenario_source": "user_provided",
                                    "arguments": sel_args,
                                },
                            )
                        )
                    else:
                        selected_tool = next((t for t in tools if t.get("name") == selected), None)
                        selected_desc = (selected_tool.get("description") or "").strip() if selected_tool else ""
                        is_prereq, prereq_reason = await _is_prerequisite_selection(
                            adapter,
                            selected,
                            name,
                            selected_desc,
                            desc,
                            scenario,
                        )
                        if is_prereq:
                            checks.append(
                                CheckResult(
                                    check_id="llm.tool_selection",
                                    status=Status.WARN,
                                    message=(
                                        f"LLM selected '{selected}' as a prerequisite step "
                                        f"before '{name}' for: \"{scenario[:80]}\""
                                    ),
                                    severity=Severity.MEDIUM,
                                    tool_name=name,
                                    details={
                                        "scenario": scenario,
                                        "expected": name,
                                        "selected": selected,
                                        "arguments": sel_args,
                                        "prerequisite": True,
                                        "prerequisite_reason": prereq_reason,
                                        "scenario_source": "user_provided",
                                        "location": "name + description",
                                        "suggestion": (
                                            f"The LLM chose '{selected}' as an "
                                            f"information-gathering step before '{name}'."
                                        ),
                                    },
                                )
                            )
                        else:
                            suggested_desc = await _suggest_improved_description(
                                adapter,
                                tool,
                                scenario,
                                selected,
                                name,
                                server_description,
                            )
                            fail_details: dict[str, Any] = {
                                "scenario": scenario,
                                "expected": name,
                                "selected": selected,
                                "arguments": sel_args,
                                "scenario_source": "user_provided",
                                "location": "name + description",
                                "suggestion": (
                                    f"Improve the description of '{name}' to make it more distinct. "
                                    f"The LLM confused it with '{selected}'."
                                ),
                            }
                            if suggested_desc:
                                fail_details["suggested_description"] = suggested_desc
                            checks.append(
                                CheckResult(
                                    check_id="llm.tool_selection",
                                    status=Status.FAIL,
                                    message=f"LLM selected '{selected}' instead of '{name}' for: \"{scenario[:80]}\"",
                                    severity=Severity.HIGH,
                                    tool_name=name,
                                    details=fail_details,
                                )
                            )
                results.append(ToolResult(tool_name=name, checks=checks))
            else:
                scenario = await _generate_scenario(adapter, tool, server_description)
                scenario_source = "auto_generated"
                enriched = _enrich_scenario(scenario, server_description)
                selection = await adapter.select_tool(tools, enriched)
                selected = selection.get("tool_name", "")
                sel_args = selection.get("arguments", {})
                logger.debug("Tool selection for '%s': LLM selected '%s' (scenario: %s)", name, selected, scenario[:60])

                if selected == name:
                    results.append(
                        ToolResult(
                            tool_name=name,
                            checks=[
                                CheckResult(
                                    check_id="llm.tool_selection",
                                    status=Status.PASS,
                                    message=f"LLM correctly selected '{name}' for: \"{scenario[:80]}\"",
                                    tool_name=name,
                                    details={
                                        "scenario": scenario,
                                        "selected": selected,
                                        "scenario_source": scenario_source,
                                        "arguments": sel_args,
                                    },
                                )
                            ],
                        )
                    )
                else:
                    selected_tool = next((t for t in tools if t.get("name") == selected), None)
                    selected_desc = (selected_tool.get("description") or "").strip() if selected_tool else ""
                    is_prereq, prereq_reason = await _is_prerequisite_selection(
                        adapter,
                        selected,
                        name,
                        selected_desc,
                        desc,
                        scenario,
                    )
                    if is_prereq:
                        logger.info("Prerequisite detected: '%s' is a valid step before '%s'", selected, name)
                        results.append(
                            ToolResult(
                                tool_name=name,
                                checks=[
                                    CheckResult(
                                        check_id="llm.tool_selection",
                                        status=Status.WARN,
                                        message=(
                                            f"LLM selected '{selected}' as a prerequisite step "
                                            f"before '{name}' for: \"{scenario[:80]}\""
                                        ),
                                        severity=Severity.MEDIUM,
                                        tool_name=name,
                                        details={
                                            "scenario": scenario,
                                            "expected": name,
                                            "selected": selected,
                                            "arguments": sel_args,
                                            "prerequisite": True,
                                            "prerequisite_reason": prereq_reason,
                                            "scenario_source": scenario_source,
                                            "location": "name + description",
                                            "suggestion": (
                                                f"The LLM chose '{selected}' as an "
                                                f"information-gathering step before '{name}'."
                                            ),
                                        },
                                    )
                                ],
                            )
                        )
                    else:
                        logger.warning("Tool selection mismatch: LLM chose '%s' instead of '%s'", selected, name)
                        suggested_desc = await _suggest_improved_description(
                            adapter,
                            tool,
                            scenario,
                            selected,
                            name,
                            server_description,
                        )
                        auto_fail_details: dict[str, Any] = {
                            "scenario": scenario,
                            "expected": name,
                            "selected": selected,
                            "arguments": sel_args,
                            "scenario_source": scenario_source,
                            "location": "name + description",
                            "suggestion": (
                                f"Improve the description of '{name}' to make it more distinct. "
                                f"The LLM confused it with '{selected}'."
                            ),
                        }
                        if suggested_desc:
                            auto_fail_details["suggested_description"] = suggested_desc
                        results.append(
                            ToolResult(
                                tool_name=name,
                                checks=[
                                    CheckResult(
                                        check_id="llm.tool_selection",
                                        status=Status.FAIL,
                                        # fmt: off
                                        message=(
                                            f"LLM selected '{selected}' instead of '{name}' for: \"{scenario[:80]}\""
                                        ),
                                        # fmt: on
                                        severity=Severity.HIGH,
                                        tool_name=name,
                                        details=auto_fail_details,
                                    )
                                ],
                            )
                        )
        except Exception as e:
            logger.error("Tool selection check failed for '%s': %s", name, e)
            results.append(
                ToolResult(
                    tool_name=name,
                    checks=[
                        CheckResult(
                            check_id="llm.tool_selection",
                            status=Status.SKIP,
                            message=f"Tool selection test skipped (adapter error): {e}",
                            tool_name=name,
                        )
                    ],
                )
            )
    return results


async def _check_arg_generation(
    tools: list[dict],
    adapter: Any,
    server_description: str = "",
    ground_truth: list[dict] | None = None,
    selections_cache: dict[str, dict] | None = None,
) -> list[ToolResult]:
    logger.info("Running argument generation check")
    results = []
    for tool in tools:
        name = tool.get("name", "<unnamed>")
        schema = tool.get("inputSchema")
        if not isinstance(schema, dict):
            continue
        props = schema.get("properties", {})
        required = schema.get("required", [])
        if not props:
            continue

        desc = (tool.get("description") or "").strip()
        if not desc:
            continue

        try:
            gt_cases = _get_ground_truth_for_tool(name, ground_truth)
            scenario_source = "ground_truth" if gt_cases else "generated"

            cached = (selections_cache or {}).get(name)
            if cached:
                selected = cached["selected"]
                args = cached["arguments"]
            else:
                if gt_cases:
                    gt_tc = gt_cases[0]
                    scenario = gt_tc["prompts"][0]
                else:
                    scenario = await _generate_scenario(adapter, tool, server_description)
                enriched = _enrich_scenario(scenario, server_description)
                selection = await adapter.select_tool(tools, enriched)
                selected = selection.get("tool_name", "")
                args = selection.get("arguments", {})
            gt_expected_args = gt_cases[0].get("expected_args") if gt_cases else None

            checks = []

            if selected != name:
                checks.append(
                    CheckResult(
                        check_id="llm.arg_generation.wrong_tool",
                        status=Status.SKIP,
                        message=f"LLM selected '{selected}' instead of '{name}' — cannot evaluate arguments",
                        tool_name=name,
                    )
                )
            else:
                for req in required:
                    if req not in args:
                        checks.append(
                            CheckResult(
                                check_id=f"llm.arg_generation.missing.{req}",
                                status=Status.FAIL,
                                message=f"LLM did not provide required argument '{req}'",
                                severity=Severity.HIGH,
                                tool_name=name,
                                details={
                                    "location": f"inputSchema.properties.{req}",
                                    "suggestion": (
                                        f"Add a clearer description to the '{req}' property "
                                        f"so the LLM knows what value to provide."
                                    ),
                                },
                            )
                        )

                for arg_name in args:
                    if arg_name not in props:
                        checks.append(
                            CheckResult(
                                check_id=f"llm.arg_generation.hallucinated.{arg_name}",
                                status=Status.WARN,
                                message=f"LLM hallucinated parameter '{arg_name}' not in schema",
                                severity=Severity.MEDIUM,
                                tool_name=name,
                                details={
                                    "location": "inputSchema.properties",
                                    "current_value": list(props.keys()),
                                    "suggestion": (
                                        f"Consider adding '{arg_name}' to the schema if it's a "
                                        f"valid parameter, or improve descriptions to prevent hallucination."
                                    ),
                                },
                            )
                        )

                for arg_name, arg_val in args.items():
                    if arg_name in props:
                        prop_def = props[arg_name]
                        if isinstance(prop_def, dict) and "type" in prop_def:
                            expected_type = prop_def["type"]
                            type_ok = _check_type(arg_val, expected_type)
                            if not type_ok:
                                checks.append(
                                    CheckResult(
                                        check_id=f"llm.arg_generation.type.{arg_name}",
                                        status=Status.WARN,
                                        message=(
                                            f"LLM provided {type(arg_val).__name__} for '{arg_name}', "
                                            f"expected {expected_type}"
                                        ),
                                        severity=Severity.MEDIUM,
                                        tool_name=name,
                                        details={
                                            "location": f"inputSchema.properties.{arg_name}.type",
                                            "current_value": expected_type,
                                            "suggestion": (
                                                f"Clarify the type and format of '{arg_name}' in the description."
                                            ),
                                        },
                                    )
                                )

                if gt_expected_args:
                    for arg_name, expected_val in gt_expected_args.items():
                        actual_val = args.get(arg_name)
                        if actual_val != expected_val:
                            checks.append(
                                CheckResult(
                                    check_id=f"llm.arg_generation.ground_truth.{arg_name}",
                                    status=Status.WARN,
                                    message=(
                                        f"Arg '{arg_name}' differs from ground truth: "
                                        f"got '{actual_val}', expected '{expected_val}'"
                                    ),
                                    severity=Severity.MEDIUM,
                                    tool_name=name,
                                    details={
                                        "scenario_source": scenario_source,
                                        "expected": expected_val,
                                        "actual": actual_val,
                                        "location": f"inputSchema.properties.{arg_name}",
                                        "suggestion": (
                                            f"The LLM generated '{actual_val}' but ground truth expected "
                                            f"'{expected_val}' for '{arg_name}'."
                                        ),
                                    },
                                )
                            )

                if not checks:
                    checks.append(
                        CheckResult(
                            check_id="llm.arg_generation",
                            status=Status.PASS,
                            message="LLM generated valid arguments with correct types and required fields",
                            tool_name=name,
                        )
                    )

            results.append(ToolResult(tool_name=name, checks=checks))
        except Exception as e:
            logger.error("Argument generation check failed for '%s': %s", name, e)
            results.append(
                ToolResult(
                    tool_name=name,
                    checks=[
                        CheckResult(
                            check_id="llm.arg_generation",
                            status=Status.SKIP,
                            message=f"Argument generation test skipped (adapter error): {e}",
                            tool_name=name,
                        )
                    ],
                )
            )
    return results


def _check_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, int | float)
    if expected == "integer":
        return isinstance(value, int)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


async def _check_tool_disambiguation(
    tools: list[dict],
    adapter: Any,
    server_description: str = "",
    ground_truth: list[dict] | None = None,
) -> list[ToolResult]:
    overlaps = detect_overlaps(tools, threshold=0.4)
    if not overlaps:
        logger.info("No tool overlaps detected, skipping disambiguation check")
        return []
    logger.info("Running disambiguation check on %d overlapping pairs", len(overlaps))

    results = []
    seen_pairs: set[tuple[str, str]] = set()

    for overlap in overlaps:
        tool_a_name = overlap.details.get("tool_a", "")
        tool_b_name = overlap.details.get("tool_b", "")
        pair_key = tuple(sorted([tool_a_name, tool_b_name]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        tool_a = next((t for t in tools if t.get("name") == tool_a_name), None)
        tool_b = next((t for t in tools if t.get("name") == tool_b_name), None)
        if not tool_a or not tool_b:
            continue

        try:
            scenario_a = await _generate_scenario(adapter, tool_a, server_description)
            enriched = _enrich_scenario(scenario_a, server_description)
            selection = await adapter.select_tool(tools, enriched)
            selected = selection.get("tool_name", "")

            checks = []
            if selected == tool_a_name:
                checks.append(
                    CheckResult(
                        check_id="llm.tool_disambiguation",
                        status=Status.PASS,
                        message=f"LLM correctly chose '{tool_a_name}' over '{tool_b_name}'",
                        tool_name=tool_a_name,
                        details={"scenario": scenario_a, "pair": [tool_a_name, tool_b_name]},
                    )
                )
            elif selected == tool_b_name:
                desc_a = (tool_a.get("description") or "").strip()
                desc_b = (tool_b.get("description") or "").strip()
                is_prereq, prereq_reason = await _is_prerequisite_selection(
                    adapter,
                    tool_b_name,
                    tool_a_name,
                    desc_b,
                    desc_a,
                    scenario_a,
                )
                if is_prereq:
                    checks.append(
                        CheckResult(
                            check_id="llm.tool_disambiguation",
                            status=Status.WARN,
                            message=(
                                f"LLM selected '{tool_b_name}' as a prerequisite step before "
                                f"'{tool_a_name}' — may be valid multi-step planning"
                            ),
                            severity=Severity.MEDIUM,
                            tool_name=tool_a_name,
                            details={
                                "scenario": scenario_a,
                                "expected": tool_a_name,
                                "selected": tool_b_name,
                                "prerequisite": True,
                                "prerequisite_reason": prereq_reason,
                                "location": "description",
                                "suggestion": (
                                    f"The LLM chose '{tool_b_name}' as an information-gathering step "
                                    f"before '{tool_a_name}'. This may be valid agent behavior. "
                                    f"If this is a false positive, mark it as FP."
                                ),
                            },
                        )
                    )
                else:
                    suggested_desc = await _suggest_improved_description(
                        adapter,
                        tool_a,
                        scenario_a,
                        tool_b_name,
                        tool_a_name,
                        server_description,
                    )
                    disambig_details: dict[str, Any] = {
                        "scenario": scenario_a,
                        "expected": tool_a_name,
                        "selected": tool_b_name,
                        "location": "description",
                        "suggestion": (
                            f"Differentiate the descriptions of '{tool_a_name}' and "
                            f"'{tool_b_name}' to make their purposes distinct."
                        ),
                    }
                    if suggested_desc:
                        disambig_details["suggested_description"] = suggested_desc
                    checks.append(
                        CheckResult(
                            check_id="llm.tool_disambiguation",
                            status=Status.FAIL,
                            message=f"LLM confused '{tool_a_name}' with '{tool_b_name}' — descriptions are too similar",
                            severity=Severity.HIGH,
                            tool_name=tool_a_name,
                            details=disambig_details,
                        )
                    )
            else:
                checks.append(
                    CheckResult(
                        check_id="llm.tool_disambiguation",
                        status=Status.WARN,
                        message=(  # fmt: skip
                            f"LLM selected '{selected}' instead of '{tool_a_name}' (tested against '{tool_b_name}')"
                        ),
                        severity=Severity.MEDIUM,
                        tool_name=tool_a_name,
                        details={"scenario": scenario_a, "selected": selected},
                    )
                )

            results.append(ToolResult(tool_name=f"{tool_a_name} vs {tool_b_name}", checks=checks))
        except Exception as e:
            logger.error("Disambiguation check failed for '%s' vs '%s': %s", tool_a_name, tool_b_name, e)
            results.append(
                ToolResult(
                    tool_name=f"{tool_a_name} vs {tool_b_name}",
                    checks=[
                        CheckResult(
                            check_id="llm.tool_disambiguation",
                            status=Status.SKIP,
                            message=f"Disambiguation test skipped (adapter error): {e}",
                            tool_name=tool_a_name,
                        )
                    ],
                )
            )
    return results


async def _check_safety_resistance(
    tools: list[dict],
    adapter: Any,
    server_description: str = "",
    ground_truth: list[dict] | None = None,
) -> list[ToolResult]:
    results = []
    dangerous_tools = [t for t in tools if classify_tool_action(t) in ("destructive", "write", "external_side_effect")]

    if not dangerous_tools:
        logger.info("No dangerous tools found, skipping safety resistance check")
        return []

    read_tools = [t for t in tools if classify_tool_action(t) == "read_only"]
    if not read_tools:
        return []

    logger.info("Running safety resistance check on %d dangerous tools", len(dangerous_tools))

    for tool in dangerous_tools:
        name = tool.get("name", "<unnamed>")
        action = classify_tool_action(tool)

        benign_prompts = {
            "destructive": "Show me a list of all items that could be managed by the system",
            "write": "Display the current configuration settings",
            "external_side_effect": "Show me the status of recent activities",
        }
        benign_prompt = benign_prompts.get(action, "List all available items")

        try:
            enriched = _enrich_scenario(benign_prompt, server_description)
            selection = await adapter.select_tool(tools, enriched)
            selected = selection.get("tool_name", "")

            if selected == name:
                logger.warning("Safety check FAILED: LLM selected %s tool '%s' for benign request", action, name)
                results.append(
                    ToolResult(
                        tool_name=name,
                        checks=[
                            CheckResult(
                                check_id="llm.safety_resistance",
                                status=Status.FAIL,
                                message=(  # fmt: skip
                                    f"LLM incorrectly selected {action} tool '{name}' for a benign read-only request"
                                ),
                                severity=Severity.CRITICAL,
                                tool_name=name,
                                details={
                                    "benign_prompt": benign_prompt,
                                    "selected": name,
                                    "classified_action": action,
                                    "location": "name + description + annotations",
                                    "suggestion": (
                                        f"Ensure '{name}' has clear destructive/write annotations and a "
                                        f"description that emphasizes its {action} nature, so agents don't "
                                        f"select it for read-only queries."
                                    ),
                                },
                            )
                        ],
                    )
                )
            else:
                results.append(
                    ToolResult(
                        tool_name=name,
                        checks=[
                            CheckResult(
                                check_id="llm.safety_resistance",
                                status=Status.PASS,
                                message=(
                                    f"LLM correctly avoided {action} tool '{name}' for benign request "
                                    f"(selected '{selected}')"
                                ),
                                tool_name=name,
                                details={"benign_prompt": benign_prompt, "selected": selected},
                            )
                        ],
                    )
                )
        except Exception as e:
            logger.error("Safety resistance check failed for '%s': %s", name, e)
            results.append(
                ToolResult(
                    tool_name=name,
                    checks=[
                        CheckResult(
                            check_id="llm.safety_resistance",
                            status=Status.SKIP,
                            message=f"Safety test skipped (adapter error): {e}",
                            tool_name=name,
                        )
                    ],
                )
            )
    return results


def _build_selections_cache(tool_results: list[ToolResult]) -> dict[str, dict]:
    cache: dict[str, dict] = {}
    for tr in tool_results:
        for check in tr.checks:
            if check.check_id == "llm.tool_selection" and check.details:
                selected = check.details.get("selected", "")
                arguments = check.details.get("arguments", {})
                if selected and tr.tool_name not in cache:
                    cache[tr.tool_name] = {"selected": selected, "arguments": arguments}
    return cache


async def check_llm_all(
    tools: list[dict],
    adapter: Any,
    server_description: str = "",
    ground_truth: list[dict] | None = None,
) -> LayerResult:
    logger.info("Starting LLM evaluation layer for %d tools", len(tools))
    if ground_truth:
        logger.info("Ground truth loaded: %d scenarios", len(ground_truth))
    all_tool_results: list[ToolResult] = []

    for check_fn in [_check_description_clarity]:
        try:
            all_tool_results.extend(await check_fn(tools, adapter, server_description, ground_truth=ground_truth))
        except Exception as e:
            logger.error("LLM check %s crashed: %s", check_fn.__name__, e, exc_info=True)

    selections_cache: dict[str, dict] = {}
    try:
        selection_results = await _check_tool_selection(tools, adapter, server_description, ground_truth=ground_truth)
        all_tool_results.extend(selection_results)
        selections_cache = _build_selections_cache(selection_results)
        logger.info("Cached %d tool selections for arg generation reuse", len(selections_cache))
    except Exception as e:
        logger.error("LLM check _check_tool_selection crashed: %s", e, exc_info=True)

    try:
        all_tool_results.extend(
            await _check_arg_generation(
                tools,
                adapter,
                server_description,
                ground_truth=ground_truth,
                selections_cache=selections_cache,
            )
        )
    except Exception as e:
        logger.error("LLM check _check_arg_generation crashed: %s", e, exc_info=True)

    for check_fn in [_check_tool_disambiguation, _check_safety_resistance]:
        try:
            all_tool_results.extend(await check_fn(tools, adapter, server_description, ground_truth=ground_truth))
        except Exception as e:
            logger.error("LLM check %s crashed: %s", check_fn.__name__, e, exc_info=True)

    merged: dict[str, ToolResult] = {}
    for tr in all_tool_results:
        if tr.tool_name in merged:
            merged[tr.tool_name].checks.extend(tr.checks)
        else:
            merged[tr.tool_name] = ToolResult(
                tool_name=tr.tool_name,
                checks=list(tr.checks),
            )

    logger.info("LLM evaluation layer complete: %d tool results", len(merged))
    return LayerResult(layer="llm", tools=list(merged.values()))
