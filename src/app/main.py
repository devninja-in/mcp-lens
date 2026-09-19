import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_frontend_port
from .database import check_db_health, dispose_db, init_db, seed_rule_configs
from .middleware import ApiKeyMiddleware
from .routes import auth_routes, llm, rules, servers, tools

_VERSION = "0.1.0"

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    log_format = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from .eval.registry import get_all_rule_defs

    seeded = await seed_rule_configs(get_all_rule_defs())
    if seeded:
        logger.info("Seeded %d new rule configs", seeded)
    logger.info("MCP Lens %s started", _VERSION)
    yield
    await dispose_db()
    logger.info("MCP Lens shutdown")


app = FastAPI(title="MCP Lens", version=_VERSION, lifespan=lifespan)

app.add_middleware(ApiKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{get_frontend_port()}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(servers.router)
app.include_router(auth_routes.router)
app.include_router(auth_routes.oauth_callback_router)
app.include_router(tools.router)
app.include_router(llm.router)
app.include_router(rules.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/api/health")
async def health():
    db_ok = await check_db_health()
    status = "ok" if db_ok else "degraded"
    return {"status": status, "version": _VERSION, "database": "ok" if db_ok else "error"}


static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
