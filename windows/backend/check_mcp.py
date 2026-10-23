"""Read-only connection check using exactly the advertised STDIO command."""
from paths import ROOT, worker_command
import asyncio
import json
import os
from datetime import timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def check():
    # Do not implicitly start a separate indexer if the app is stopped or unconfigured.
    from settings import load_settings
    if not load_settings()["app_managed"] or not (ROOT/"data/service.json").exists():
        raise RuntimeError("请先打开 App 并启动本地服务。")
    command = worker_command("server")
    if os.name=='nt' and getattr(__import__('sys'), 'frozen', False):
        from runtime_pin import write_windows_launcher
        command=[os.environ.get('COMSPEC','cmd.exe'), '/d', '/c', str(write_windows_launcher())]
    env=dict(os.environ)
    env["RESEARCH_LIBRARY_ENGINE"]=__import__("sys").executable
    params = StdioServerParameters(command=command[0], args=command[1:], cwd=str(ROOT), env=env)
    with open(ROOT/"logs/mcp-check-server.stderr.log", "w") as err:
        async with stdio_client(params, errlog=err) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=20)) as session:
                await session.initialize()
                listing = await session.list_tools()
                result = await session.call_tool("library_status", {})
                if result.isError: raise RuntimeError("MCP 已启动，但资料库服务不可用；请检查 App 服务状态。")
                return {"ok": True, "tool_count": len(listing.tools), "status_readable": True}

async def main():
    try: return await asyncio.wait_for(check(), timeout=30)
    except Exception as exc:
        return {"ok": False, "error": "连接检查失败，请确认本地服务运行且客户端允许本机连接。", "detail": type(exc).__name__}

if __name__ == "__main__":
    result = asyncio.run(main())
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)
