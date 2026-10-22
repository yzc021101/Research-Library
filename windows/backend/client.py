"""Run a real MCP stdio client, not direct Python calls to server functions."""
from paths import ROOT
import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def call(name, args):
    params = StdioServerParameters(command=str(ROOT / ".venv/bin/python"),
        args=["-B", str(ROOT / "src/server.py")], cwd=str(ROOT), env=dict(os.environ))
    with open(ROOT / "logs/client-server.stderr.log", "a") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=180)) as session:
                await session.initialize()
                if name == "list_tools":
                    return (await session.list_tools()).model_dump(mode="json")
                result = await session.call_tool(name, args)
                if result.isError:
                    raise RuntimeError(str(result.content))
                data = result.structuredContent
                if data is None:
                    data = json.loads(next(c.text for c in result.content if c.type == "text"))
                return data

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tool", nargs="?", default="library_status")
    parser.add_argument("arguments", nargs="?", default="{}")
    parser.add_argument("--save", help="JSON output path relative to results/")
    args = parser.parse_args()
    output = asyncio.run(call(args.tool, json.loads(args.arguments)))
    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.save:
        from paths import inside
        destination = inside(ROOT / "results" / args.save, ROOT / "results")
        destination.write_text(text)
        print(destination)
    else: print(text)
