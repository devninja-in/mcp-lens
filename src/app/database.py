import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Boolean, DateTime, String, Text, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import get_database_url

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class McpSecret(Base):
    __tablename__ = "mcp_secrets"

    server_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    secret_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    secret_data: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class McpServer(Base):
    __tablename__ = "mcp_servers"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    config_data: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class EvalResult(Base):
    __tablename__ = "eval_results"

    server_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    report_data: Mapped[str] = mapped_column(Text, nullable=False)
    has_llm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class GroundTruth(Base):
    __tablename__ = "ground_truth"

    server_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    yaml_data: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    global _engine, _session_factory
    url = get_database_url()
    _engine = create_async_engine(url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_tokens_json()
    await _migrate_mcp_json()


async def dispose_db() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def check_db_health() -> bool:
    try:
        async with _get_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("Database health check failed")
        return False


def _get_session() -> AsyncSession:
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory()


async def get_secret(server_name: str, secret_type: str) -> dict | None:
    async with _get_session() as session:
        result = await session.get(McpSecret, (server_name, secret_type))
        if result is None:
            return None
        return json.loads(result.secret_data)


async def set_secret(server_name: str, secret_type: str, data: dict) -> None:
    async with _get_session() as session:
        async with session.begin():
            existing = await session.get(McpSecret, (server_name, secret_type))
            now = datetime.now(timezone.utc)
            if existing:
                existing.secret_data = json.dumps(data)
                existing.updated_at = now
            else:
                session.add(McpSecret(
                    server_name=server_name,
                    secret_type=secret_type,
                    secret_data=json.dumps(data),
                    updated_at=now,
                ))


async def delete_secret(server_name: str, secret_type: str) -> None:
    async with _get_session() as session:
        async with session.begin():
            existing = await session.get(McpSecret, (server_name, secret_type))
            if existing:
                await session.delete(existing)


async def get_all_servers() -> dict[str, dict]:
    async with _get_session() as session:
        result = await session.execute(select(McpServer))
        rows = result.scalars().all()
        return {row.name: json.loads(row.config_data) for row in rows}


async def get_server_config(name: str) -> dict | None:
    async with _get_session() as session:
        result = await session.get(McpServer, name)
        if result is None:
            return None
        return json.loads(result.config_data)


async def set_server_config(name: str, config_data: dict) -> None:
    async with _get_session() as session:
        async with session.begin():
            existing = await session.get(McpServer, name)
            now = datetime.now(timezone.utc)
            if existing:
                existing.config_data = json.dumps(config_data)
                existing.updated_at = now
            else:
                session.add(McpServer(
                    name=name,
                    config_data=json.dumps(config_data),
                    updated_at=now,
                ))


async def delete_server_config(name: str) -> None:
    async with _get_session() as session:
        async with session.begin():
            existing = await session.get(McpServer, name)
            if existing:
                await session.delete(existing)


async def get_eval_report(server_name: str) -> dict | None:
    async with _get_session() as session:
        result = await session.get(EvalResult, server_name)
        if result is None:
            return None
        return json.loads(result.report_data)


async def save_eval_report(server_name: str, report_data: dict, has_llm: bool = False) -> None:
    async with _get_session() as session:
        async with session.begin():
            existing = await session.get(EvalResult, server_name)
            now = datetime.now(timezone.utc)
            if existing:
                existing.report_data = json.dumps(report_data)
                existing.has_llm = has_llm
                existing.updated_at = now
            else:
                session.add(EvalResult(
                    server_name=server_name,
                    report_data=json.dumps(report_data),
                    has_llm=has_llm,
                    updated_at=now,
                ))


async def get_ground_truth(server_name: str) -> dict | None:
    async with _get_session() as session:
        result = await session.get(GroundTruth, server_name)
        if result is None:
            return None
        import yaml
        return yaml.safe_load(result.yaml_data)


async def save_ground_truth(server_name: str, yaml_content: str) -> None:
    async with _get_session() as session:
        async with session.begin():
            existing = await session.get(GroundTruth, server_name)
            now = datetime.now(timezone.utc)
            if existing:
                existing.yaml_data = yaml_content
                existing.updated_at = now
            else:
                session.add(GroundTruth(
                    server_name=server_name,
                    yaml_data=yaml_content,
                    updated_at=now,
                ))


async def delete_ground_truth(server_name: str) -> None:
    async with _get_session() as session:
        async with session.begin():
            existing = await session.get(GroundTruth, server_name)
            if existing:
                await session.delete(existing)


async def _migrate_tokens_json() -> None:
    tokens_path = Path("tokens.json")
    if not tokens_path.exists():
        return

    async with _get_session() as session:
        result = await session.execute(select(McpSecret).limit(1))
        if result.first() is not None:
            return

    with open(tokens_path) as f:
        tokens = json.load(f)

    for key, value in tokens.items():
        if key.endswith("_bearer"):
            server_name = key[:-7]
            secret_type = "bearer"
        elif key.endswith("_apikey"):
            server_name = key[:-7]
            secret_type = "apikey"
        elif key.endswith("_dcr"):
            server_name = key[:-4]
            secret_type = "dcr"
        elif key.endswith("_sso"):
            server_name = key[:-4]
            secret_type = "bearer"
            value = {"token": value.get("token", "")} if isinstance(value, dict) else {"token": value}
        else:
            server_name = key
            secret_type = "oauth"
        await set_secret(server_name, secret_type, value)

    logger.info("Migrated %d entries from tokens.json to database", len(tokens))


async def _migrate_mcp_json() -> None:
    config_path = Path("mcp.json")
    if not config_path.exists():
        return

    async with _get_session() as session:
        result = await session.execute(select(McpServer).limit(1))
        if result.first() is not None:
            return

    with open(config_path) as f:
        data = json.load(f)

    servers = data.get("mcpServers", {})
    for name, config in servers.items():
        await set_server_config(name, config)

    logger.info("Migrated %d servers from mcp.json to database", len(servers))
