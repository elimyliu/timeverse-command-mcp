"""
timeverse-command MCP Server 入口

功能简述:
    作为独立的 MCP Server 进程运行，对外暴露三个工具：
    - bash: 执行 shell 命令
    - python: 执行 Python 代码
    - node: 执行 Node.js 代码

所有工具通过 stdio 协议与 LLM 通信，遵守 MCP 1.0 规范。
可在 Claude Desktop / Cursor / Continue / Cline 等客户端中使用。

使用示例:
    # 方式 1：直接启动（开发 / 调试用）
    python -m timeverse_command.server

    # 方式 2：使用控制台脚本（pip install 后）
    timeverse-command-mcp

    # 方式 3：在 MCP 客户端配置中
    # claude_desktop_config.json:
    # {
    #   "mcpServers": {
    #     "timeverse-command": {
    #       "command": "timeverse-command-mcp"
    #     }
    #   }
    # }
"""

import asyncio
import json
import logging
import sys
import time
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .executor import AsyncCommandSession, get_executor

# ==================== 日志配置 ====================

# MCP 协议要求所有 stdout 输出都是 JSON-RPC 消息，
# 日志必须走 stderr，否则会破坏协议。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("timeverse-command")

# ==================== 创建 MCP Server 实例 ====================

# 名称会作为 MCP 客户端工具名的前缀：mcp__timeverse-command__bash
app = Server("timeverse-command")


# ==================== 工具定义 ====================


@app.list_tools()  # type: ignore[untyped-decorator,no-untyped-call]
async def list_tools() -> list[Tool]:
    """
    注册三个工具到 MCP Server

    每个工具的 inputSchema 描述了 LLM 调用时需要传入的参数。
    返回值会被 MCP 客户端缓存到工具列表。
    """
    return [
        Tool(
            name="bash",
            description=(
                "在本地 shell（macOS/Linux: zsh/bash, Windows: cmd/powershell）中执行命令。"
                "支持流式输出。常用场景：文件操作、查看系统信息、运行 CLI 工具。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "工作目录（可选，默认为调用进程的当前目录）",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数（可选，默认 60）",
                        "default": 60,
                    },
                },
                "required": ["command"],
            },
        ),
        Tool(
            name="python",
            description=(
                "在本地 Python 3 解释器中执行单段代码（python -c）。"
                "适合快速计算、数据处理、调用 Python 库。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的 Python 代码（-c 参数形式）",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数（可选，默认 60）",
                        "default": 60,
                    },
                },
                "required": ["code"],
            },
        ),
        Tool(
            name="node",
            description=(
                "在本地 Node.js 中执行单段代码（node -e）。适合 JavaScript 计算、JSON 处理。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的 JavaScript 代码",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数（可选，默认 60）",
                        "default": 60,
                    },
                },
                "required": ["code"],
            },
        ),
    ]


# ==================== 工具调用处理 ====================


async def _run_and_collect(name: str, args: dict[str, Any]) -> str:
    """
    执行命令并把流式输出累积为最终文本返回给 LLM

    Args:
        name: 工具名（bash / python / node）
        args: 工具参数

    Returns:
        str: 累积的输出（JSON 格式，包含 stdout、stderr、退出码）
    """
    # 统一参数：bash 用 command，python / node 用 code
    if name == "bash":
        command = args.get("command", "")
        cwd = args.get("cwd")
        timeout = args.get("timeout", 60)
    else:
        command = args.get("code") or args.get("command", "")
        cwd = None
        timeout = args.get("timeout", 60)

    if not command:
        return json.dumps(
            {"error": "empty_command", "message": "命令不能为空"},
            ensure_ascii=False,
        )

    # 创建会话
    session = AsyncCommandSession(
        tool_call_id=f"mcp-{id(time)}",  # MCP 模式下不直接关联 tool_call_log
        command=command,
        tool_name=name,
        cwd=cwd,
        timeout=timeout,
    )

    # 注册到全局执行器（用于可能的取消）
    executor = get_executor()
    executor.register(session)

    # 流式累积
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    exit_code = -1
    status = "unknown"

    try:
        async for chunk in session.run():
            if chunk["stream"] == "stdout":
                stdout_lines.append(chunk["delta"])
            elif chunk["stream"] == "stderr":
                stderr_lines.append(chunk["delta"])
            elif chunk["stream"] == "exit":
                exit_code = chunk["exit_code"]
                status = chunk["status"]
                if "error" in chunk:
                    stderr_lines.append(f"[error] {chunk['error']}")
    except Exception as e:
        logger.exception("Command execution failed")
        return json.dumps(
            {"error": "execution_failed", "message": str(e)},
            ensure_ascii=False,
        )
    finally:
        executor.unregister(session.tool_call_id)

    # 构造返回给 LLM 的文本
    result = {
        "stdout": "\n".join(stdout_lines),
        "stderr": "\n".join(stderr_lines),
        "exit_code": exit_code,
        "status": status,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@app.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """
    处理 LLM 的工具调用

    MCP 协议要求返回 list[TextContent]，LLM 会把每个 TextContent 的 text
    字段作为工具结果。

    Args:
        name: 工具名
        arguments: LLM 传入的参数

    Returns:
        list[TextContent]: 包含命令执行结果的文本内容
    """
    logger.info("call_tool: %s args=%s", name, arguments)
    result_text = await _run_and_collect(name, arguments)
    return [TextContent(type="text", text=result_text)]


# ==================== 启动入口 ====================


async def _run() -> None:
    """MCP Server 启动协程：使用 stdio 传输"""
    logger.info("timeverse-command MCP Server starting...")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )
    logger.info("timeverse-command MCP Server stopped")


def main() -> None:
    """
    控制台入口函数（由 `timeverse-command-mcp` 命令调用）

    使用示例:
        timeverse-command-mcp
    """
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception("Server crashed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    # 支持 `python -m timeverse_command.server` 启动
    main()
