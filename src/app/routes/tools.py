import logging
from datetime import UTC

import yaml
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from ..auth import clear_oauth_tokens
from ..config import load_config, persist_oauth_tokens
from ..database import (
    delete_ground_truth,
    get_eval_report,
    get_ground_truth,
    save_eval_report,
    save_ground_truth,
)
from ..eval.llm_config import (
    get_adapter_for_config,
    get_available_llm_configs,
    get_default_llm_name,
    load_llm_configs,
)
from ..eval.llm_eval import check_llm_all
from ..eval.models import EvalReport
from ..eval.overlap import detect_overlaps
from ..eval.protocol import check_protocol_all
from ..eval.quality import check_quality_all
from ..eval.quality import evaluate_tools_compat as evaluate_tools
from ..eval.scoring import apply_scoring
from ..eval.security import check_security_all
from ..mcp_client import ReAuthRequiredError, mcp_initialize, mcp_list_tools
from ..tools_store import delete_tools, load_tools, save_tools

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/servers", tags=["tools"])


class FalsePositiveRequest(BaseModel):
    check_key: str
    justification: str | None = None


@router.post("/{name}/test")
async def test_connection(name: str) -> dict:
    logger.info("Testing connection to server '%s'", name)
    config = await load_config()
    if name not in config.mcp_servers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    try:
        result, _ = await mcp_initialize(name, config.mcp_servers[name])
        if "error" in result:
            logger.warning("Connection test failed for '%s': %s", name, result["error"])
            return {"success": False, "message": f"MCP error: {result['error']}"}
        server_info = result.get("result", {}).get("serverInfo", {})
        logger.info("Connection test succeeded for '%s'", name)
        return {
            "success": True,
            "message": "Connection successful",
            "server_info": server_info,
        }
    except ReAuthRequiredError as e:
        logger.warning("Re-auth required for '%s'", name)
        return {"success": False, "message": str(e), "reauth": True}
    except Exception as e:
        logger.error("Connection test error for '%s': %s", name, e)
        return {"success": False, "message": str(e)}


@router.post("/{name}/fetch-tools")
async def fetch_tools(name: str) -> dict:
    logger.info("Fetching tools from server '%s'", name)
    config = await load_config()
    if name not in config.mcp_servers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    server_config = config.mcp_servers[name]
    try:
        tools = await mcp_list_tools(name, server_config)
        path = save_tools(name, tools)
        logger.info("Fetched %d tools from '%s', saved to %s", len(tools), name, path)
        if not persist_oauth_tokens() and server_config.auth_mode in ("oauth", "dcr"):
            await clear_oauth_tokens(name)
        return {
            "success": True,
            "message": f"Fetched {len(tools)} tools, saved to {path}",
            "tools": tools,
            "count": len(tools),
        }
    except ReAuthRequiredError as e:
        logger.warning("Re-auth required while fetching tools for '%s'", name)
        return {
            "success": False,
            "message": str(e),
            "tools": [],
            "count": 0,
            "reauth": True,
        }
    except Exception as e:
        logger.error("Failed to fetch tools from '%s': %s", name, e)
        return {"success": False, "message": str(e), "tools": [], "count": 0}


@router.get("/{name}/tools")
async def get_tools(name: str) -> dict:
    result = load_tools(name)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No tools found for '{name}'. Fetch tools first.",
        )
    return {"server": name, "tools": result["tools"], "count": len(result["tools"]), "source": result["source"]}


@router.get("/{name}/evaluate")
async def evaluate(name: str) -> dict:
    result = load_tools(name)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No tools found for '{name}'. Fetch tools first.",
        )
    return evaluate_tools(result["tools"])


@router.get("/{name}/evaluate/report")
async def get_cached_report(name: str) -> dict:
    report = await get_eval_report(name)
    if report is None:
        raise HTTPException(status_code=404, detail="No evaluation report found")
    return report


@router.get("/{name}/evaluate/full")
async def evaluate_full(name: str) -> dict:
    result = load_tools(name)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No tools found for '{name}'. Fetch tools first.",
        )
    tools = result["tools"]
    from datetime import datetime

    logger.info("Running full evaluation for server '%s' (%d tools)", name, len(tools))

    layers = {
        "protocol": check_protocol_all(tools),
        "quality": check_quality_all(tools),
        "security": check_security_all(tools),
    }
    overlaps = detect_overlaps(tools)
    if overlaps:
        logger.info("Detected %d tool overlaps for '%s'", len(overlaps), name)
        layers["quality"].catalog_checks.extend(overlaps)

    llm_configs = load_llm_configs()
    llm_meta: dict = {"llm_configured": llm_configs is not None}

    report = EvalReport(
        timestamp=datetime.now(UTC).isoformat(),
        server_name=name,
        layers=layers,
        metadata=llm_meta,
    )
    report = apply_scoring(report)
    logger.info(
        "Full evaluation complete for '%s': score=%.1f gate=%s",
        name,
        report.overall_score,
        report.gate_passed,
    )
    result = report.to_dict()
    await save_eval_report(name, result, has_llm=False)
    return result


@router.post("/{name}/ground-truth")
async def upload_ground_truth(name: str, file: UploadFile) -> dict:
    logger.info("Uploading ground truth for server '%s'", name)
    content = await file.read()
    if len(content) > 1_048_576:
        raise HTTPException(status_code=400, detail="File too large (max 1MB)")
    try:
        yaml_text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8 text") from e

    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}") from e

    if not isinstance(data, dict) or "test_cases" not in data:
        raise HTTPException(status_code=400, detail="YAML must contain a 'test_cases' key")

    test_cases = data["test_cases"]
    if not isinstance(test_cases, list):
        raise HTTPException(status_code=400, detail="'test_cases' must be a list")

    warnings = []
    tools_result = load_tools(name)
    tool_names = {t.get("name") for t in tools_result["tools"]} if tools_result else set()
    total_prompts = 0

    for i, tc in enumerate(test_cases):
        if not isinstance(tc, dict):
            raise HTTPException(status_code=400, detail=f"test_cases[{i}] must be an object")
        if "expected_tool_selection" not in tc or "prompts" not in tc:
            raise HTTPException(
                status_code=400,
                detail=f"test_cases[{i}] must have 'expected_tool_selection' and 'prompts' fields",
            )
        ets = tc["expected_tool_selection"]
        if not isinstance(ets, list) or not ets or not all(isinstance(t, str) and t for t in ets):
            raise HTTPException(
                status_code=400,
                detail=f"test_cases[{i}].expected_tool_selection must be a non-empty list of strings",
            )
        prompts = tc["prompts"]
        if not isinstance(prompts, list) or not prompts or not all(isinstance(p, str) and p for p in prompts):
            raise HTTPException(
                status_code=400,
                detail=f"test_cases[{i}].prompts must be a non-empty list of strings",
            )
        total_prompts += len(prompts)
        if tool_names:
            for tool_name in ets:
                if tool_name not in tool_names:
                    warnings.append(f"Tool '{tool_name}' not found in server tools")

    await save_ground_truth(name, yaml_text)
    logger.info("Saved %d ground truth test cases for '%s'", len(test_cases), name)
    return {"success": True, "test_case_count": len(test_cases), "prompt_count": total_prompts, "warnings": warnings}


@router.get("/{name}/ground-truth")
async def get_ground_truth_data(name: str) -> dict:
    data = await get_ground_truth(name)
    if data is None:
        raise HTTPException(status_code=404, detail="No ground truth found")
    test_cases = data.get("test_cases", [])
    prompt_count = sum(len(tc.get("prompts", [])) for tc in test_cases)
    return {
        "server_name": name,
        "test_cases": test_cases,
        "test_case_count": len(test_cases),
        "prompt_count": prompt_count,
    }


@router.delete("/{name}/ground-truth")
async def remove_ground_truth(name: str) -> dict:
    await delete_ground_truth(name)
    logger.info("Deleted ground truth for server '%s'", name)
    return {"success": True}


@router.get("/{name}/ground-truth/template")
async def download_ground_truth_template(name: str) -> Response:
    result = load_tools(name)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No tools found for '{name}'. Fetch tools first.",
        )
    tools = result["tools"]
    test_cases = []
    for tool in tools:
        tool_name = tool.get("name", "")
        desc = (tool.get("description") or "").strip()
        hint = f"TODO: Add a prompt that should trigger {tool_name}"
        if desc:
            hint += f" ({desc[:80]})"
        test_cases.append(
            {
                "expected_tool_selection": [tool_name],
                "prompts": [hint],
            }
        )
    yaml_text = yaml.dump({"test_cases": test_cases}, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return Response(
        content=yaml_text,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{name}-test-cases.yaml"'},
    )


@router.get("/{name}/evaluate/llm")
async def evaluate_llm(name: str, llms: str | None = None) -> dict:
    tools_data = load_tools(name)
    if tools_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No tools found for '{name}'. Fetch tools first.",
        )
    tools = tools_data["tools"]

    from datetime import datetime

    config = await load_config()
    server_description = ""
    if name in config.mcp_servers:
        server_description = config.mcp_servers[name].description or ""
    if server_description:
        logger.info("Using server description as LLM context for '%s'", name)

    gt_data = await get_ground_truth(name)
    ground_truth_scenarios = gt_data.get("test_cases", []) if gt_data else None
    if ground_truth_scenarios:
        logger.info("Loaded %d ground truth test cases for '%s'", len(ground_truth_scenarios), name)

    llm_names: list[str] = []
    if llms:
        llm_names = [n.strip() for n in llms.split(",") if n.strip()]
    else:
        default_name = get_default_llm_name()
        if default_name:
            llm_names = [default_name]

    if not llm_names:
        raise HTTPException(
            status_code=404,
            detail="LLM evaluation not configured. Create llm.json with at least one config. See llm.json.example.",
        )

    logger.info("LLM evaluation for '%s' with configs: %s", name, llm_names)
    per_llm: dict[str, dict] = {}
    primary_layer = None
    primary_meta: dict = {}

    for llm_name in llm_names:
        try:
            adapter = get_adapter_for_config(llm_name)
        except (ValueError, ImportError) as e:
            logger.error("Failed to create adapter for '%s': %s", llm_name, e)
            per_llm[llm_name] = {"error": str(e), "metadata": {"llm_error": str(e)}}
            continue

        available = get_available_llm_configs()
        cfg_info = available.get(llm_name, {})

        try:
            llm_layer = await check_llm_all(tools, adapter, server_description, ground_truth=ground_truth_scenarios)
            layer_dict = llm_layer.to_dict()
            meta = {
                "llm_provider": cfg_info.get("provider", llm_name),
                "llm_model": cfg_info.get("model", "default"),
            }
            per_llm[llm_name] = {"layer": layer_dict, "metadata": meta}
            if primary_layer is None:
                primary_layer = llm_layer
                primary_meta = meta
        except Exception as e:
            logger.error("LLM evaluation failed for config '%s': %s", llm_name, e, exc_info=True)
            per_llm[llm_name] = {
                "error": str(e),
                "metadata": {"llm_provider": cfg_info.get("provider", llm_name), "llm_error": str(e)},
            }

    layers = {
        "protocol": check_protocol_all(tools),
        "quality": check_quality_all(tools),
        "security": check_security_all(tools),
    }
    overlaps = detect_overlaps(tools)
    if overlaps:
        layers["quality"].catalog_checks.extend(overlaps)
    if primary_layer:
        layers["llm"] = primary_layer

    report = EvalReport(
        timestamp=datetime.now(UTC).isoformat(),
        server_name=name,
        layers=layers,
    )
    report = apply_scoring(report)
    logger.info(
        "Multi-LLM evaluation complete for '%s': score=%.1f gate=%s",
        name,
        report.overall_score,
        report.gate_passed,
    )

    result: dict = {
        "layer": primary_layer.to_dict() if primary_layer else None,
        "overall_score": report.overall_score,
        "gate_passed": report.gate_passed,
        "metadata": {
            **primary_meta,
            "ground_truth_loaded": bool(ground_truth_scenarios),
        },
        "per_llm": per_llm,
    }
    full_report = report.to_dict()
    full_report["metadata"] = full_report.get("metadata", {})
    full_report["metadata"]["per_llm"] = per_llm
    await save_eval_report(name, full_report, has_llm=True)
    return result


@router.post("/{name}/evaluate/false-positive")
async def mark_false_positive(name: str, body: FalsePositiveRequest) -> dict:
    report = await get_eval_report(name)
    if report is None:
        raise HTTPException(status_code=404, detail="No evaluation report found")

    meta = report.setdefault("metadata", {})
    fps: dict = meta.setdefault("false_positives", {})

    if body.justification:
        fps[body.check_key] = body.justification
    else:
        fps.pop(body.check_key, None)

    await save_eval_report(name, report, has_llm="llm" in report.get("layers", {}))
    return {"success": True, "false_positives": fps}


@router.post("/{name}/tools/upload")
async def upload_tools(name: str, file: UploadFile) -> dict:
    logger.info("Uploading tool definitions for server '%s'", name)
    content = await file.read()
    if len(content) > 2_097_152:
        raise HTTPException(status_code=400, detail="File too large (max 2MB)")
    try:
        yaml_text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8 text") from e

    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}") from e

    if not isinstance(data, dict) or "tools" not in data:
        raise HTTPException(status_code=400, detail="YAML must contain a 'tools' key")

    raw_tools = data["tools"]
    if not isinstance(raw_tools, list) or not raw_tools:
        raise HTTPException(status_code=400, detail="'tools' must be a non-empty list")

    warnings: list[str] = []
    validated: list[dict] = []
    for i, tool in enumerate(raw_tools):
        if not isinstance(tool, dict):
            raise HTTPException(status_code=400, detail=f"tools[{i}] must be an object")
        name_val = tool.get("name")
        if not isinstance(name_val, str) or not name_val.strip():
            raise HTTPException(status_code=400, detail=f"tools[{i}].name must be a non-empty string")
        if not tool.get("description"):
            warnings.append(f"tools[{i}] '{name_val}' is missing a description")
        schema = tool.get("inputSchema")
        if schema is not None:
            if not isinstance(schema, dict):
                raise HTTPException(status_code=400, detail=f"tools[{i}].inputSchema must be an object")
            if schema.get("type") != "object":
                warnings.append(f"tools[{i}] '{name_val}' inputSchema.type should be 'object'")
        validated.append(
            {
                "name": name_val.strip(),
                "description": tool.get("description", ""),
                "inputSchema": schema or {"type": "object", "properties": {}},
            }
        )

    save_tools(name, validated, source="uploaded")
    logger.info("Uploaded %d tool definitions for '%s'", len(validated), name)
    return {
        "success": True,
        "message": f"Uploaded {len(validated)} tool definitions",
        "tools": validated,
        "count": len(validated),
        "warnings": warnings,
    }


@router.get("/{name}/tools/template")
async def download_tools_template(name: str) -> Response:
    result = load_tools(name)
    if result:
        tools = result["tools"]
        template_tools = []
        for tool in tools:
            entry: dict = {"name": tool.get("name", "")}
            if tool.get("description"):
                entry["description"] = tool["description"]
            if tool.get("inputSchema"):
                entry["inputSchema"] = tool["inputSchema"]
            template_tools.append(entry)
    else:
        template_tools = [
            {
                "name": "example_tool_1",
                "description": "TODO: Describe what this tool does",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "A string parameter"},
                        "param2": {"type": "integer", "description": "A numeric parameter"},
                    },
                    "required": ["param1"],
                },
            },
            {
                "name": "example_tool_2",
                "description": "TODO: Describe what this tool does",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "description": "Max results"},
                        "verbose": {"type": "boolean", "description": "Enable verbose output"},
                    },
                },
            },
        ]

    yaml_text = yaml.dump(
        {"tools": template_tools},
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    return Response(
        content=yaml_text,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{name}-tools-template.yaml"'},
    )


@router.delete("/{name}/tools/uploaded")
async def remove_uploaded_tools(name: str) -> dict:
    result = load_tools(name)
    if result is None:
        raise HTTPException(status_code=404, detail="No tools found")
    if result["source"] != "uploaded":
        raise HTTPException(status_code=400, detail="Can only delete uploaded tools, not fetched tools")
    delete_tools(name)
    logger.info("Deleted uploaded tools for server '%s'", name)
    return {"success": True}
