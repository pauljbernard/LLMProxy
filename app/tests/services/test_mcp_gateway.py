import pytest

from app.config import Settings
from app.services import mcp_gateway


@pytest.mark.asyncio
async def test_mcp_gateway_reuses_session_and_caches_inventory(monkeypatch) -> None:
    await mcp_gateway.clear_mcp_session_pool()

    stats = {"starts": 0, "lists": 0, "calls": 0, "closed": 0}

    class _Process:
        returncode = None

    class FakeClient:
        def __init__(self, config):
            self.config = config
            self.process = _Process()

        async def start(self):
            stats["starts"] += 1
            return self

        async def close(self):
            stats["closed"] += 1
            self.process.returncode = 0

        async def list_tools(self):
            stats["lists"] += 1
            return [{"name": "status_lookup", "inputSchema": {"type": "object"}}]

        async def call_tool(self, *, name: str, arguments=None):
            stats["calls"] += 1
            return {"content": [{"type": "text", "text": f"{name}:{arguments['query']}"}]}

    monkeypatch.setattr(mcp_gateway, "_StdioMCPClient", FakeClient)
    settings = Settings(
        llmproxy_mcp_servers={
            "cluster": {
                "transport": "stdio",
                "command": "python3",
                "args": ["/tmp/mcp_server.py"],
                "timeout_seconds": 10.0,
            }
        },
        llmproxy_mcp_tool_inventory_ttl_seconds=60,
    )

    tools_first = await mcp_gateway._list_mcp_tools(settings, "cluster")
    tools_second = await mcp_gateway._list_mcp_tools(settings, "cluster")
    result = await mcp_gateway._call_mcp_tool(settings, "cluster", "status_lookup", {"query": "ok"})

    assert tools_first == tools_second
    assert result["content"][0]["text"] == "status_lookup:ok"
    assert stats["starts"] == 1
    assert stats["lists"] == 1
    assert stats["calls"] == 1

    await mcp_gateway.clear_mcp_session_pool()
    assert stats["closed"] == 1
