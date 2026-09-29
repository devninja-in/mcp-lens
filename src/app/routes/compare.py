import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import load_config
from ..database import (
    delete_comparison_report,
    get_comparison_report,
    get_eval_report,
    list_comparison_reports,
    save_comparison_report,
)
from ..eval.comparison import run_comparison
from ..eval.llm_config import get_adapter_for_config, get_default_llm_name
from ..mcp_client import mcp_initialize
from ..tools_store import load_tools

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/compare", tags=["compare"])


class CompareRequest(BaseModel):
    server_a: str
    server_b: str


@router.get("")
async def check_comparison(server_a: str, server_b: str) -> dict:
    report = await get_comparison_report(server_a, server_b)
    return {"exists": report is not None, "report": report}


@router.post("")
async def run_compare(body: CompareRequest) -> dict:
    if body.server_a == body.server_b:
        raise HTTPException(status_code=400, detail="Cannot compare a server with itself")

    config = await load_config()
    for name in (body.server_a, body.server_b):
        if name not in config.mcp_servers:
            raise HTTPException(status_code=404, detail=f"Server '{name}' not found")

    tools_a_data = load_tools(body.server_a)
    tools_b_data = load_tools(body.server_b)
    if tools_a_data is None:
        raise HTTPException(status_code=400, detail=f"No tools fetched for '{body.server_a}'. Fetch tools first.")
    if tools_b_data is None:
        raise HTTPException(status_code=400, detail=f"No tools fetched for '{body.server_b}'. Fetch tools first.")

    tools_a = tools_a_data["tools"]
    tools_b = tools_b_data["tools"]

    init_a = None
    init_b = None
    for name, target in [(body.server_a, "a"), (body.server_b, "b")]:
        try:
            result, _ = await mcp_initialize(name, config.mcp_servers[name])
            if "error" not in result:
                if target == "a":
                    init_a = result
                else:
                    init_b = result
        except Exception:
            logger.warning("Could not initialize '%s' for comparison, skipping capabilities", name)

    eval_a = await get_eval_report(body.server_a)
    eval_b = await get_eval_report(body.server_b)

    default_llm = get_default_llm_name()
    if not default_llm:
        raise HTTPException(
            status_code=422,
            detail="LLM configuration required for comparison. Create llm.json with at least one config.",
        )

    try:
        adapter = get_adapter_for_config(default_llm)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not load LLM adapter for '{default_llm}': {e}",
        ) from e

    logger.info("Running comparison: '%s' vs '%s'", body.server_a, body.server_b)
    report = await run_comparison(
        server_a_name=body.server_a,
        server_b_name=body.server_b,
        tools_a=tools_a,
        tools_b=tools_b,
        init_a=init_a,
        init_b=init_b,
        eval_a=eval_a,
        eval_b=eval_b,
        adapter=adapter,
    )

    await save_comparison_report(body.server_a, body.server_b, report)
    logger.info("Comparison complete: '%s' vs '%s'", body.server_a, body.server_b)
    return report


@router.get("/list")
async def list_comparisons() -> dict:
    reports = await list_comparison_reports()
    return {"reports": reports}


@router.delete("/{report_id}")
async def delete_comparison(report_id: int) -> dict:
    deleted = await delete_comparison_report(report_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Comparison report not found")
    return {"success": True}
