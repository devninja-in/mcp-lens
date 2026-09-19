"""Model adapters for LLM-assisted evaluation.

SAFETY: select_tool() asks the LLM which tool it would choose — it does NOT
execute the tool.  The returned dict contains the tool name and proposed
arguments, which are validated against the schema but never sent to any
MCP server.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ModelAdapter(Protocol):
    async def select_tool(self, tools: list[dict], user_prompt: str) -> dict:
        """Return {"tool_name": ..., "arguments": ...} — selection only, no execution."""
        ...

    async def generate_answer(self, tool_result: Any, user_prompt: str) -> str: ...


class MockAdapter:
    def __init__(self, responses: dict[str, dict] | None = None):
        self.responses = responses or {}
        self.calls: list[dict] = []

    async def select_tool(self, tools: list[dict], user_prompt: str) -> dict:
        self.calls.append({"method": "select_tool", "prompt": user_prompt})
        if user_prompt in self.responses:
            return self.responses[user_prompt]
        return {"tool_name": tools[0]["name"] if tools else "", "arguments": {}}

    async def generate_answer(self, tool_result: Any, user_prompt: str) -> str:
        self.calls.append({"method": "generate_answer", "prompt": user_prompt})
        return str(tool_result)


def _build_tools_for_api(tools: list[dict]) -> list[dict]:
    result = []
    for t in tools:
        entry: dict[str, Any] = {
            "name": t.get("name", ""),
            "description": t.get("description", ""),
        }
        if "inputSchema" in t:
            entry["input_schema"] = t["inputSchema"]
        result.append(entry)
    return result


class AnthropicAdapter:
    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: str | None = None):
        try:
            import anthropic
        except ImportError as err:
            raise ImportError("anthropic package required. Install with: pip install anthropic") from err
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else anthropic.AsyncAnthropic()
        logger.debug("Initialized AnthropicAdapter with model=%s", model)

    async def select_tool(self, tools: list[dict], user_prompt: str) -> dict:
        logger.debug("Anthropic select_tool: %d tools, prompt=%s", len(tools), user_prompt[:80])
        api_tools = _build_tools_for_api(tools)
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            tools=api_tools,
            messages=[{"role": "user", "content": user_prompt}],
        )
        for block in response.content:
            if block.type == "tool_use":
                return {"tool_name": block.name, "arguments": block.input}
        return {"tool_name": "", "arguments": {}}

    async def generate_answer(self, tool_result: Any, user_prompt: str) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": f"Based on the tool result: {tool_result}"},
            ],
        )
        return response.content[0].text if response.content else ""


class OpenAIAdapter:
    def __init__(self, model: str = "gpt-4o", api_key: str | None = None, base_url: str | None = None):
        try:
            import openai
        except ImportError as err:
            raise ImportError("openai package required. Install with: pip install openai") from err
        self.model = model
        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self.client = openai.AsyncOpenAI(**kwargs)
        logger.debug("Initialized OpenAIAdapter with model=%s", model)

    async def select_tool(self, tools: list[dict], user_prompt: str) -> dict:
        logger.debug("OpenAI select_tool: %d tools, prompt=%s", len(tools), user_prompt[:80])
        functions = []
        for t in tools:
            fn: dict[str, Any] = {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
            }
            fn["parameters"] = t.get("inputSchema", {"type": "object", "properties": {}})
            functions.append(fn)

        import json

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": user_prompt}],
            functions=functions,
            function_call="auto",
        )
        msg = response.choices[0].message
        if msg.function_call:
            args = json.loads(msg.function_call.arguments) if msg.function_call.arguments else {}
            return {"tool_name": msg.function_call.name, "arguments": args}
        return {"tool_name": "", "arguments": {}}

    async def generate_answer(self, tool_result: Any, user_prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": f"Tool result: {tool_result}. Let me provide the answer."},
            ],
        )
        return response.choices[0].message.content or ""


class AnthropicVertexAdapter:
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        project: str | None = None,
        location: str = "us-east5",
    ):
        try:
            from anthropic import AsyncAnthropicVertex
        except ImportError as err:
            raise ImportError(
                "anthropic[vertex] package required. Install with: pip install 'anthropic[vertex]'"
            ) from err
        kwargs: dict[str, Any] = {}
        if project:
            kwargs["project_id"] = project
        if location:
            kwargs["region"] = location
        self.model = model
        self.client = AsyncAnthropicVertex(**kwargs)
        logger.debug("Initialized AnthropicVertexAdapter with model=%s project=%s", model, project)

    async def select_tool(self, tools: list[dict], user_prompt: str) -> dict:
        logger.debug("AnthropicVertex select_tool: %d tools, prompt=%s", len(tools), user_prompt[:80])
        api_tools = _build_tools_for_api(tools)
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            tools=api_tools,
            messages=[{"role": "user", "content": user_prompt}],
        )
        for block in response.content:
            if block.type == "tool_use":
                return {"tool_name": block.name, "arguments": block.input}
        return {"tool_name": "", "arguments": {}}

    async def generate_answer(self, tool_result: Any, user_prompt: str) -> str:
        content = f"Tool result: {tool_result}\n\n{user_prompt}" if tool_result is not None else user_prompt
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )
        return response.content[0].text if response.content else ""


_GEMINI_UNSUPPORTED_KEYS = {
    "additionalProperties",
    "examples",
    "$schema",
    "default",
    "title",
    "$id",
    "$ref",
    "$comment",
    "const",
    "contentMediaType",
    "contentEncoding",
    "if",
    "then",
    "else",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
}


def _strip_unsupported_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_unsupported_keys(v) for k, v in obj.items() if k not in _GEMINI_UNSUPPORTED_KEYS}
    if isinstance(obj, list):
        return [_strip_unsupported_keys(item) for item in obj]
    return obj


class VertexAIAdapter:
    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        project: str | None = None,
        location: str = "us-central1",
        api_key: str | None = None,
    ):
        try:
            from google import genai
        except ImportError as err:
            raise ImportError("google-genai package required. Install with: pip install google-genai") from err
        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        else:
            if project:
                client_kwargs["project"] = project
            if location:
                client_kwargs["location"] = location
            client_kwargs["vertexai"] = True
        self.client = genai.Client(**client_kwargs)
        self.model = model
        logger.debug("Initialized VertexAIAdapter with model=%s project=%s location=%s", model, project, location)

    async def select_tool(self, tools: list[dict], user_prompt: str) -> dict:
        logger.debug("VertexAI select_tool: %d tools, prompt=%s", len(tools), user_prompt[:80])
        from google.genai import types

        api_tools = []
        for t in tools:
            schema = t.get("inputSchema", {"type": "object", "properties": {}})
            clean_schema = _strip_unsupported_keys(schema)
            fn = types.FunctionDeclaration(
                name=t.get("name", ""),
                description=t.get("description", ""),
                parameters=clean_schema,
            )
            api_tools.append(types.Tool(function_declarations=[fn]))

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                tools=api_tools,  # type: ignore[arg-type]
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
            ),
        )

        for part in response.candidates[0].content.parts:  # type: ignore[index,union-attr]
            if part.function_call:
                args = dict(part.function_call.args) if part.function_call.args else {}
                return {"tool_name": part.function_call.name, "arguments": args}
        return {"tool_name": "", "arguments": {}}

    async def generate_answer(self, tool_result: Any, user_prompt: str) -> str:
        from google.genai import types

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=f"Based on the tool result: {tool_result}\n\nAnswer: {user_prompt}",
            config=types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
            ),
        )
        return response.text or ""


def get_adapter(
    name: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    project: str | None = None,
    location: str | None = None,
) -> ModelAdapter:
    if name == "mock":
        return MockAdapter()
    elif name == "anthropic":
        kwargs: dict[str, Any] = {}
        if model:
            kwargs["model"] = model
        if api_key:
            kwargs["api_key"] = api_key
        return AnthropicAdapter(**kwargs)
    elif name == "openai":
        kwargs = {}
        if model:
            kwargs["model"] = model
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAIAdapter(**kwargs)
    elif name == "vertexai":
        kwargs = {}
        if model:
            kwargs["model"] = model
        if api_key:
            kwargs["api_key"] = api_key
        if project:
            kwargs["project"] = project
        if location:
            kwargs["location"] = location
        return VertexAIAdapter(**kwargs)
    elif name == "anthropic-vertex":
        kwargs = {}
        if model:
            kwargs["model"] = model
        if project:
            kwargs["project"] = project
        if location:
            kwargs["location"] = location
        return AnthropicVertexAdapter(**kwargs)
    else:
        raise ValueError(f"Unknown adapter: '{name}'. Available: mock, anthropic, openai, vertexai, anthropic-vertex")
