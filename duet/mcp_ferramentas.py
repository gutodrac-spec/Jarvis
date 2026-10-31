"""Servidor MCP (stdio) que entrega as ferramentas do Duet ao Claude Code."""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import mcp.types as types  # noqa: E402
from mcp.server.lowlevel import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402

import agente  # noqa: E402

servidor = Server("duet")


@servidor.list_tools()
async def listar():
    defs, _ = agente.definir_ferramentas()
    return [
        types.Tool(name=d["name"], description=d["description"], inputSchema=d["input_schema"])
        for d in defs
    ]


@servidor.call_tool()
async def chamar(nome, argumentos):
    _, funcs = agente.definir_ferramentas()
    texto, _ = await asyncio.to_thread(agente.executar, funcs, nome, argumentos)
    return [types.TextContent(type="text", text=texto)]


async def principal():
    async with stdio_server() as (leitura, escrita):
        await servidor.run(leitura, escrita, servidor.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(principal())
