import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Boolean, DateTime, Integer, String, Text, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import get_database_url

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None
_encryption_key = os.environ.get("MCP_LENS_ENCRYPTION_KEY")
if _encryption_key:
    _fernet = Fernet(_encryption_key.encode())


def _encrypt(plaintext: str) -> str:
    if _fernet is None:
        return plaintext
    return _fernet.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    if _fernet is None:
        return ciphertext
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return ciphertext


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


class RuleConfigRow(Base):
    __tablename__ = "rule_configs"

    rule_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    severity_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    config_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class CapabilityAnalysisResult(Base):
    __tablename__ = "capability_analysis"

    server_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    analysis_data: Mapped[str] = mapped_column(Text, nullable=False)
    llm_name: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ComparisonReport(Base):
    __tablename__ = "comparison_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_a: Mapped[str] = mapped_column(String(255), nullable=False)
    server_b: Mapped[str] = mapped_column(String(255), nullable=False)
    report_data: Mapped[str] = mapped_column(Text, nullable=False)
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
        data: dict = json.loads(_decrypt(result.secret_data))
        return data


async def set_secret(server_name: str, secret_type: str, data: dict) -> None:
    async with _get_session() as session, session.begin():
        existing = await session.get(McpSecret, (server_name, secret_type))
        now = datetime.now(UTC)
        encrypted = _encrypt(json.dumps(data))
        if existing:
            existing.secret_data = encrypted
            existing.updated_at = now
        else:
            session.add(
                McpSecret(
                    server_name=server_name,
                    secret_type=secret_type,
                    secret_data=encrypted,
                    updated_at=now,
                )
            )


async def delete_secret(server_name: str, secret_type: str) -> None:
    async with _get_session() as session, session.begin():
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
        data: dict = json.loads(result.config_data)
        return data


async def set_server_config(name: str, config_data: dict) -> None:
    async with _get_session() as session, session.begin():
        existing = await session.get(McpServer, name)
        now = datetime.now(UTC)
        if existing:
            existing.config_data = json.dumps(config_data)
            existing.updated_at = now
        else:
            session.add(
                McpServer(
                    name=name,
                    config_data=json.dumps(config_data),
                    updated_at=now,
                )
            )


async def delete_server_config(name: str) -> None:
    async with _get_session() as session, session.begin():
        existing = await session.get(McpServer, name)
        if existing:
            await session.delete(existing)


async def get_eval_report(server_name: str) -> dict | None:
    async with _get_session() as session:
        result = await session.get(EvalResult, server_name)
        if result is None:
            return None
        data: dict = json.loads(result.report_data)
        return data


async def save_eval_report(server_name: str, report_data: dict, has_llm: bool = False) -> None:
    async with _get_session() as session, session.begin():
        existing = await session.get(EvalResult, server_name)
        now = datetime.now(UTC)
        if existing:
            existing.report_data = json.dumps(report_data)
            existing.has_llm = has_llm
            existing.updated_at = now
        else:
            session.add(
                EvalResult(
                    server_name=server_name,
                    report_data=json.dumps(report_data),
                    has_llm=has_llm,
                    updated_at=now,
                )
            )


async def get_ground_truth(server_name: str) -> dict | None:
    async with _get_session() as session:
        result = await session.get(GroundTruth, server_name)
        if result is None:
            return None
        import yaml

        data: dict = yaml.safe_load(result.yaml_data)
        return data


async def save_ground_truth(server_name: str, yaml_content: str) -> None:
    async with _get_session() as session, session.begin():
        existing = await session.get(GroundTruth, server_name)
        now = datetime.now(UTC)
        if existing:
            existing.yaml_data = yaml_content
            existing.updated_at = now
        else:
            session.add(
                GroundTruth(
                    server_name=server_name,
                    yaml_data=yaml_content,
                    updated_at=now,
                )
            )


async def delete_ground_truth(server_name: str) -> None:
    async with _get_session() as session, session.begin():
        existing = await session.get(GroundTruth, server_name)
        if existing:
            await session.delete(existing)


async def get_all_rule_configs() -> dict[str, dict]:
    async with _get_session() as session:
        result = await session.execute(select(RuleConfigRow))
        rows = result.scalars().all()
        configs = {}
        for row in rows:
            configs[row.rule_id] = {
                "enabled": row.enabled,
                "severity_override": row.severity_override,
                "config_data": json.loads(row.config_data) if row.config_data else None,
            }
        return configs


async def get_rule_config(rule_id: str) -> dict | None:
    async with _get_session() as session:
        result = await session.get(RuleConfigRow, rule_id)
        if result is None:
            return None
        return {
            "enabled": result.enabled,
            "severity_override": result.severity_override,
            "config_data": json.loads(result.config_data) if result.config_data else None,
        }


async def set_rule_config(
    rule_id: str,
    enabled: bool = True,
    severity_override: str | None = None,
    config_data: dict | None = None,
) -> None:
    async with _get_session() as session, session.begin():
        existing = await session.get(RuleConfigRow, rule_id)
        now = datetime.now(UTC)
        if existing:
            existing.enabled = enabled
            existing.severity_override = severity_override
            existing.config_data = json.dumps(config_data) if config_data else None
            existing.updated_at = now
        else:
            session.add(
                RuleConfigRow(
                    rule_id=rule_id,
                    enabled=enabled,
                    severity_override=severity_override,
                    config_data=json.dumps(config_data) if config_data else None,
                    updated_at=now,
                )
            )


async def delete_all_rule_configs() -> int:
    async with _get_session() as session, session.begin():
        result = await session.execute(select(RuleConfigRow))
        rows = result.scalars().all()
        count = len(rows)
        for row in rows:
            await session.delete(row)
        return count


async def seed_rule_configs(rule_defs: list[dict]) -> int:
    async with _get_session() as session:
        result = await session.execute(select(RuleConfigRow))
        existing = {row.rule_id for row in result.scalars().all()}

    seeded = 0
    for rd in rule_defs:
        if rd["rule_id"] not in existing:
            await set_rule_config(
                rule_id=rd["rule_id"],
                enabled=rd.get("default_enabled", True),
                severity_override=None,
                config_data=None,
            )
            seeded += 1
    return seeded


async def get_capability_analysis(server_name: str) -> dict | None:
    async with _get_session() as session:
        result = await session.get(CapabilityAnalysisResult, server_name)
        if result is None:
            return None
        data: dict = json.loads(result.analysis_data)
        return data


async def save_capability_analysis(server_name: str, analysis_data: dict) -> None:
    async with _get_session() as session, session.begin():
        existing = await session.get(CapabilityAnalysisResult, server_name)
        now = datetime.now(UTC)
        if existing:
            existing.analysis_data = json.dumps(analysis_data)
            existing.llm_name = analysis_data.get("llm_name", "")
            existing.updated_at = now
        else:
            session.add(
                CapabilityAnalysisResult(
                    server_name=server_name,
                    analysis_data=json.dumps(analysis_data),
                    llm_name=analysis_data.get("llm_name", ""),
                    updated_at=now,
                )
            )


def _canonical_pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


async def get_comparison_report(server_a: str, server_b: str) -> dict | None:
    ca, cb = _canonical_pair(server_a, server_b)
    async with _get_session() as session:
        result = await session.execute(
            select(ComparisonReport).where(
                ComparisonReport.server_a == ca,
                ComparisonReport.server_b == cb,
            )
        )
        row = result.scalars().first()
        if row is None:
            return None
        data: dict = json.loads(row.report_data)
        return data


async def save_comparison_report(server_a: str, server_b: str, report_data: dict) -> int:
    ca, cb = _canonical_pair(server_a, server_b)
    async with _get_session() as session, session.begin():
        result = await session.execute(
            select(ComparisonReport).where(
                ComparisonReport.server_a == ca,
                ComparisonReport.server_b == cb,
            )
        )
        existing = result.scalars().first()
        now = datetime.now(UTC)
        if existing:
            existing.report_data = json.dumps(report_data)
            existing.updated_at = now
            return existing.id
        row = ComparisonReport(
            server_a=ca,
            server_b=cb,
            report_data=json.dumps(report_data),
            updated_at=now,
        )
        session.add(row)
        await session.flush()
        return row.id


async def list_comparison_reports() -> list[dict]:
    async with _get_session() as session:
        result = await session.execute(select(ComparisonReport))
        rows = result.scalars().all()
        return [
            {
                "id": row.id,
                "server_a": row.server_a,
                "server_b": row.server_b,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ]


async def delete_comparison_report(report_id: int) -> bool:
    async with _get_session() as session, session.begin():
        existing = await session.get(ComparisonReport, report_id)
        if existing:
            await session.delete(existing)
            return True
        return False


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
            secret_type = "bearer"  # noqa: S105
        elif key.endswith("_apikey"):
            server_name = key[:-7]
            secret_type = "apikey"  # noqa: S105
        elif key.endswith("_dcr"):
            server_name = key[:-4]
            secret_type = "dcr"  # noqa: S105
        elif key.endswith("_sso"):
            server_name = key[:-4]
            secret_type = "bearer"  # noqa: S105
            value = {"token": value.get("token", "")} if isinstance(value, dict) else {"token": value}
        else:
            server_name = key
            secret_type = "oauth"  # noqa: S105
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
