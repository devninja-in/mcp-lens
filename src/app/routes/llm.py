import logging

from fastapi import APIRouter

from ..eval.llm_config import get_available_llm_configs, get_default_llm_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["llm"])


@router.get("/llm-configs")
async def list_llm_configs() -> dict:
    logger.info("Listing available LLM configurations")
    configs = get_available_llm_configs()
    default = get_default_llm_name()
    return {"configs": configs, "default": default}
