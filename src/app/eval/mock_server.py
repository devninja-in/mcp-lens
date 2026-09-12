from __future__ import annotations

from typing import Any

GOOD_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_customers",
        "description": "Search for customers by name, email, or account number",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Customer name to search for"},
                "email": {"type": "string", "description": "Email address"},
                "limit": {"type": "integer", "description": "Max results to return", "default": 10},
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "get_customer",
        "description": "Get a single customer by their unique identifier",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Unique customer ID"},
            },
            "required": ["customer_id"],
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "create_invoice",
        "description": "Create a new invoice for a customer with line items and payment terms",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer to invoice"},
                "amount": {"type": "number", "description": "Invoice amount"},
                "currency": {
                    "type": "string",
                    "description": "Currency code",
                    "enum": ["USD", "EUR", "GBP"],
                },
                "due_days": {"type": "integer", "description": "Days until due", "default": 30},
            },
            "required": ["customer_id", "amount"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "search_documents",
        "description": "Search for documents by content, title, or metadata tags",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title to match"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"},
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
]

BAD_TOOLS: list[dict[str, Any]] = [
    {
        "name": "",
        "description": "Does something",
        "inputSchema": {"type": "object"},
    },
    {
        "name": "data_processor",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string"},
                "mode": {"type": "string"},
            },
        },
    },
    {
        "name": "delete_everything",
        "description": "Delete all records from the system permanently",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean", "description": "Must be true"},
            },
            "required": ["confirm"],
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "find_customers",
        "description": "Find customers by name, email, or account number",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Customer name"},
                "email": {"type": "string", "description": "Email address"},
                "limit": {"type": "integer", "description": "Max results"},
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
]


def get_mock_tools(include_bad: bool = False) -> list[dict[str, Any]]:
    tools = list(GOOD_TOOLS)
    if include_bad:
        tools.extend(BAD_TOOLS)
    return tools


async def mock_call_fn(tool_name: str, args: dict) -> tuple[dict, float]:
    responses = {
        "search_customers": {"content": [{"id": "c1", "name": "Alice Smith"}]},
        "get_customer": {"id": args.get("customer_id", ""), "name": "Alice Smith", "email": "alice@example.com"},
        "create_invoice": {"id": "inv-001", "status": "created"},
        "search_documents": {"content": [{"title": "Doc 1", "id": "d1"}]},
    }
    if tool_name in responses:
        return responses[tool_name], 50.0
    raise ValueError(f"Unknown tool: {tool_name}")
