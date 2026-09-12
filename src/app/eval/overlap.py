from __future__ import annotations

import logging
import re
import string

from .models import CheckResult, Severity, Status

logger = logging.getLogger(__name__)

_CAMEL_SPLIT = re.compile(r"[a-z]+|[A-Z][a-z]*")


def _tokenize_name(name: str) -> set[str]:
    if "_" in name:
        return {s.lower() for s in name.split("_") if s}
    segments = _CAMEL_SPLIT.findall(name)
    return {s.lower() for s in segments} if segments else {name.lower()}


def _name_similarity(a: str, b: str) -> float:
    ta = _tokenize_name(a)
    tb = _tokenize_name(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _desc_similarity(a: str, b: str) -> float:
    table = str.maketrans("", "", string.punctuation)
    wa = set(a.lower().translate(table).split())
    wb = set(b.lower().translate(table).split())
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _schema_overlap(a: dict, b: dict) -> float:
    pa = set(a.get("inputSchema", {}).get("properties", {}).keys()) if isinstance(a.get("inputSchema"), dict) else set()
    pb = set(b.get("inputSchema", {}).get("properties", {}).keys()) if isinstance(b.get("inputSchema"), dict) else set()
    if not pa and not pb:
        return 0.0
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)


def detect_overlaps(tools: list[dict], threshold: float = 0.6) -> list[CheckResult]:
    logger.debug("Checking overlaps among %d tools (threshold=%.2f)", len(tools), threshold)
    results: list[CheckResult] = []
    for i in range(len(tools)):
        for j in range(i + 1, len(tools)):
            a, b = tools[i], tools[j]
            na = a.get("name", "")
            nb = b.get("name", "")
            da = a.get("description", "") or ""
            db = b.get("description", "") or ""

            ns = _name_similarity(na, nb)
            ds = _desc_similarity(da, db)
            ss = _schema_overlap(a, b)
            combined = 0.3 * ns + 0.4 * ds + 0.3 * ss

            if combined > threshold:
                results.append(
                    CheckResult(
                        check_id="overlap.tool_pair",
                        status=Status.WARN,
                        message=f"Tools '{na}' and '{nb}' may overlap (similarity: {combined:.2f})",
                        severity=Severity.MEDIUM,
                        details={
                            "tool_a": na,
                            "tool_b": nb,
                            "name_similarity": round(ns, 3),
                            "desc_similarity": round(ds, 3),
                            "schema_overlap": round(ss, 3),
                            "combined": round(combined, 3),
                        },
                    )
                )
    return results
