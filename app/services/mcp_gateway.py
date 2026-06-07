"""MCP gateway support for model tool execution."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shlex
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from app.config import Settings
from app.services.mcp_runtime import record_mcp_tool_call, record_mcp_validation
from app.schemas.chat import ChatCompletionRequest, ChatMessage, FunctionToolSpec, MCPToolSpec, ToolFunctionSpec

MCP_PROTOCOL_VERSION = "2025-06-18"


class MCPServerConfig(BaseModel):
    transport: str = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class MCPToolBinding:
    synthetic_name: str
    server: str
    tool_name: str


class _StdioMCPClient:
    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._stderr_task: asyncio.Task[None] | None = None

    async def start(self) -> "_StdioMCPClient":
        command, args = self._command_and_args()
        env = os.environ.copy()
        env.update(self.config.env)
        self.process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.config.cwd,
            env=env,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        await self._initialize()
        return self

    async def __aenter__(self) -> "_StdioMCPClient":
        return await self.start()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self.process is None:
            return
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with contextlib.suppress(Exception):
                await self._stderr_task
        self._stderr_task = None
        self.process = None

    def _command_and_args(self) -> tuple[str, list[str]]:
        if self.config.args:
            return self.config.command, list(self.config.args)
        parts = shlex.split(self.config.command)
        if not parts:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid MCP server command.")
        return parts[0], parts[1:]

    async def _drain_stderr(self) -> None:
        if self.process is None or self.process.stderr is None:
            return
        while True:
            line = await self.process.stderr.readline()
            if not line:
                return

    async def _initialize(self) -> None:
        await self._request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "llmproxy", "version": "0.1.0"},
            },
        )
        await self._notify("notifications/initialized")

    async def _notify(self, method: str, params: dict[str, object] | None = None) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def _request(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        request_id = self._next_id
        self._next_id += 1
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )
        response = await self._recv()
        if response.get("id") != request_id:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="MCP server returned an unexpected response id.")
        if "error" in response:
            error = response.get("error")
            detail = error.get("message") if isinstance(error, dict) else "MCP server error."
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(detail))
        result = response.get("result")
        if not isinstance(result, dict):
            return {}
        return result

    async def _send(self, payload: dict[str, object]) -> None:
        if self.process is None or self.process.stdin is None:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="MCP server process is not running.")
        self.process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await asyncio.wait_for(self.process.stdin.drain(), timeout=self.config.timeout_seconds)

    async def _recv(self) -> dict[str, object]:
        if self.process is None or self.process.stdout is None:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="MCP server process is not running.")
        while True:
            line = await asyncio.wait_for(self.process.stdout.readline(), timeout=self.config.timeout_seconds)
            if not line:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="MCP server closed without responding.")
            try:
                message = json.loads(line.decode("utf-8").strip())
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and ("id" in message or "method" in message):
                return message

    async def list_tools(self) -> list[dict[str, object]]:
        result = await self._request("tools/list")
        tools = result.get("tools")
        if not isinstance(tools, list):
            return []
        return [item for item in tools if isinstance(item, dict)]

    async def call_tool(self, *, name: str, arguments: dict[str, object] | None = None) -> dict[str, object]:
        return await self._request("tools/call", {"name": name, "arguments": arguments or {}})


@dataclass
class MCPRequestContext:
    request: ChatCompletionRequest
    bindings: dict[str, MCPToolBinding]
    trace: list[dict[str, object]] = None

    async def execute(self, settings: Settings, provider_invoke) -> dict[str, object]:
        trace = self.trace if isinstance(self.trace, list) else []
        current_request = self.request
        for _ in range(max(1, settings.llmproxy_mcp_max_tool_roundtrips)):
            provider_result = await provider_invoke(current_request)
            tool_calls = provider_result.get("tool_calls")
            finish_reason = str(provider_result.get("finish_reason", "stop"))
            if finish_reason != "tool_calls" or not isinstance(tool_calls, list) or not tool_calls:
                provider_result["mcp_trace"] = trace
                raw_response = provider_result.get("raw_response")
                if isinstance(raw_response, dict):
                    raw_response["mcp_trace"] = trace
                return provider_result
            if not all(_is_mcp_tool_call(item, self.bindings) for item in tool_calls):
                provider_result["mcp_trace"] = trace
                raw_response = provider_result.get("raw_response")
                if isinstance(raw_response, dict):
                    raw_response["mcp_trace"] = trace
                return provider_result
            tool_messages = await _execute_mcp_tool_calls(settings, tool_calls, self.bindings, trace)
            current_request = current_request.model_copy(
                deep=True,
                update={
                    "messages": [
                        *current_request.messages,
                        ChatMessage(
                            role="assistant",
                            content=str(provider_result.get("content", "")),
                            tool_calls=[item for item in tool_calls if isinstance(item, dict)],
                        ),
                        *tool_messages,
                    ]
                },
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MCP tool roundtrip limit exceeded.",
        )


@dataclass
class _SharedMCPServerSession:
    config: MCPServerConfig
    client: _StdioMCPClient | None = None
    lock: asyncio.Lock = None
    tools_cache: list[dict[str, object]] | None = None
    tools_cached_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.lock is None:
            self.lock = asyncio.Lock()

    async def ensure_client(self) -> _StdioMCPClient:
        if self.client is not None and self.client.process is not None and self.client.process.returncode is None:
            return self.client
        self.client = await _StdioMCPClient(self.config).start()
        return self.client

    async def close(self) -> None:
        if self.client is None:
            return
        await self.client.close()
        self.client = None

    def cache_valid(self, *, ttl_seconds: int) -> bool:
        if self.tools_cache is None or self.tools_cached_at is None:
            return False
        return datetime.now(timezone.utc) <= (self.tools_cached_at + timedelta(seconds=max(0, ttl_seconds)))


_SESSION_POOL: dict[str, _SharedMCPServerSession] = {}
_SESSION_POOL_LOCK = asyncio.Lock()


def request_has_mcp_tools(request: ChatCompletionRequest) -> bool:
    return any(isinstance(tool, MCPToolSpec) for tool in (request.tools or []))


def request_requires_tools(request: ChatCompletionRequest) -> bool:
    return bool(request.tools or request.functions)


async def prepare_mcp_request(request: ChatCompletionRequest, settings: Settings) -> MCPRequestContext | None:
    mcp_tools = [tool for tool in (request.tools or []) if isinstance(tool, MCPToolSpec)]
    if not mcp_tools:
        return None
    translated_tools: list[FunctionToolSpec] = []
    bindings: dict[str, MCPToolBinding] = {}
    native_tools = [tool for tool in (request.tools or []) if not isinstance(tool, MCPToolSpec)]
    for index, tool in enumerate(mcp_tools):
        schema = await _resolve_mcp_tool_schema(settings, tool)
        synthetic_name = f"mcp__tool_{index}"
        bindings[synthetic_name] = MCPToolBinding(
            synthetic_name=synthetic_name,
            server=tool.server,
            tool_name=tool.name,
        )
        translated_tools.append(
            FunctionToolSpec(
                type="function",
                function=ToolFunctionSpec(
                    name=synthetic_name,
                    description=schema["description"],
                    parameters=schema["parameters"],
                ),
            )
        )
    translated_request = request.model_copy(
        deep=True,
        update={
            "tools": [*native_tools, *translated_tools],
            "tool_choice": _translate_tool_choice(request.tool_choice, bindings),
        },
    )
    return MCPRequestContext(request=translated_request, bindings=bindings, trace=[])


def _translate_tool_choice(tool_choice: str | dict[str, object] | None, bindings: dict[str, MCPToolBinding]) -> str | dict[str, object] | None:
    if not isinstance(tool_choice, dict):
        return tool_choice
    function = tool_choice.get("function")
    if not isinstance(function, dict):
        return tool_choice
    name = function.get("name")
    if not isinstance(name, str):
        return tool_choice
    for synthetic_name, binding in bindings.items():
        if name == binding.tool_name or name == synthetic_name:
            return {"type": "function", "function": {"name": synthetic_name}}
    return tool_choice


async def _resolve_mcp_tool_schema(settings: Settings, tool: MCPToolSpec) -> dict[str, object]:
    description = tool.description
    parameters = tool.parameters
    if description is not None and parameters is not None:
        return {"description": description, "parameters": parameters}
    tools = await _list_mcp_tools(settings, tool.server)
    for item in tools:
        if str(item.get("name")) != tool.name:
            continue
        return {
            "description": description or str(item.get("description") or f"MCP tool {tool.name} on server {tool.server}."),
            "parameters": parameters or dict(item.get("inputSchema") or {"type": "object"}),
        }
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"MCP tool '{tool.name}' was not found on server '{tool.server}'.",
    )


def _server_config(settings: Settings, server_name: str) -> MCPServerConfig:
    raw = settings.llmproxy_mcp_servers.get(server_name)
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MCP server '{server_name}' is not configured.",
        )
    config = MCPServerConfig.model_validate(raw)
    if config.transport != "stdio":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"MCP transport '{config.transport}' is not supported yet.",
        )
    return config


async def _pooled_session(settings: Settings, server_name: str) -> _SharedMCPServerSession:
    config = _server_config(settings, server_name)
    async with _SESSION_POOL_LOCK:
        current = _SESSION_POOL.get(server_name)
        if current is not None and current.config.model_dump(mode="json") == config.model_dump(mode="json"):
            return current
        if current is not None:
            await current.close()
        session = _SharedMCPServerSession(config=config)
        _SESSION_POOL[server_name] = session
        return session


async def _list_mcp_tools(settings: Settings, server_name: str) -> list[dict[str, object]]:
    session = await _pooled_session(settings, server_name)
    started_at = perf_counter()
    try:
        async with session.lock:
            if session.cache_valid(ttl_seconds=settings.llmproxy_mcp_tool_inventory_ttl_seconds):
                tools = list(session.tools_cache or [])
            else:
                client = await session.ensure_client()
                tools = await client.list_tools()
                session.tools_cache = list(tools)
                session.tools_cached_at = datetime.now(timezone.utc)
        record_mcp_validation(server=server_name, success=True, latency_ms=int((perf_counter() - started_at) * 1000), tool_count=len(tools))
        return tools
    except Exception as exc:
        async with session.lock:
            await session.close()
        record_mcp_validation(server=server_name, success=False, latency_ms=int((perf_counter() - started_at) * 1000), error=str(exc))
        raise


async def _call_mcp_tool(
    settings: Settings,
    server_name: str,
    tool_name: str,
    arguments: dict[str, object] | None,
) -> dict[str, object]:
    session = await _pooled_session(settings, server_name)
    started_at = perf_counter()
    try:
        async with session.lock:
            client = await session.ensure_client()
            result = await client.call_tool(name=tool_name, arguments=arguments)
        record_mcp_tool_call(
            server=server_name,
            tool_name=tool_name,
            success=True,
            latency_ms=int((perf_counter() - started_at) * 1000),
        )
        return result
    except Exception as exc:
        async with session.lock:
            await session.close()
        record_mcp_tool_call(
            server=server_name,
            tool_name=tool_name,
            success=False,
            latency_ms=int((perf_counter() - started_at) * 1000),
            error=str(exc),
        )
        raise


def _is_mcp_tool_call(item: object, bindings: dict[str, MCPToolBinding]) -> bool:
    if not isinstance(item, dict):
        return False
    function = item.get("function")
    if not isinstance(function, dict):
        return False
    name = function.get("name")
    return isinstance(name, str) and name in bindings


async def _execute_mcp_tool_calls(
    settings: Settings,
    tool_calls: list[dict[str, object]],
    bindings: dict[str, MCPToolBinding],
    trace: list[dict[str, object]],
) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for call in tool_calls:
        function = call.get("function")
        if not isinstance(function, dict):
            continue
        name = str(function.get("name", ""))
        binding = bindings[name]
        arguments_text = function.get("arguments")
        arguments = json.loads(arguments_text) if isinstance(arguments_text, str) and arguments_text.strip() else {}
        if not isinstance(arguments, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"MCP tool '{binding.tool_name}' received non-object arguments.",
            )
        result = await _call_mcp_tool(settings, binding.server, binding.tool_name, arguments)
        trace.append(
            {
                "server": binding.server,
                "tool_name": binding.tool_name,
                "tool_call_id": str(call.get("id", "")),
                "arguments": arguments,
                "result": result,
            }
        )
        messages.append(
            ChatMessage(
                role="tool",
                tool_call_id=str(call.get("id", "")),
                name=binding.tool_name,
                content=_tool_result_text(result),
            )
        )
    return messages


def _tool_result_text(result: dict[str, object]) -> str:
    structured = result.get("structuredContent")
    content = result.get("content")
    parts: list[str] = []
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("text"), str):
                parts.append(str(item["text"]))
            elif item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(str(item["text"]))
            else:
                parts.append(json.dumps(item))
    if structured is not None:
        parts.append(json.dumps(structured))
    if not parts:
        return json.dumps(result)
    return "\n".join(parts)


async def inspect_mcp_server(settings: Settings, server_name: str) -> dict[str, object]:
    started_at = perf_counter()
    config = _server_config(settings, server_name)
    session = await _pooled_session(settings, server_name)
    async with session.lock:
        client = await session.ensure_client()
        tools = await client.list_tools()
        session.tools_cache = list(tools)
        session.tools_cached_at = datetime.now(timezone.utc)
    latency_ms = int((perf_counter() - started_at) * 1000)
    record_mcp_validation(server=server_name, success=True, latency_ms=latency_ms, tool_count=len(tools))
    return {
        "server": server_name,
        "transport": config.transport,
        "command": config.command,
        "args": list(config.args),
        "cwd": config.cwd,
        "timeout_seconds": float(config.timeout_seconds),
        "tool_count": len(tools),
        "tools": [
            {
                "name": str(item.get("name", "")),
                "description": item.get("description"),
                "input_schema": item.get("inputSchema"),
            }
            for item in tools
        ],
        "validated": True,
        "latency_ms": latency_ms,
    }


async def clear_mcp_session_pool() -> None:
    async with _SESSION_POOL_LOCK:
        sessions = list(_SESSION_POOL.values())
        _SESSION_POOL.clear()
    for session in sessions:
        await session.close()
