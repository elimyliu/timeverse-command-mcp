"""
timeverse-command-mcp - 命令执行 MCP Server

功能简述:
    跨平台执行 shell / Python / Node 命令的 MCP Server，
    遵守 Model Context Protocol stdio 传输规范，
    可被任何支持 MCP 的客户端调用（Claude Desktop / Cursor / Continue 等）。

主要组件清单:
    - AsyncCommandSession: 单次命令会话（异步执行 + 流式输出）
    - CommandExecutor: 会话管理器（注册 / 取消 / 查询）
    - get_executor: 全局执行器单例

使用示例:
    from timeverse_command import AsyncCommandSession, get_executor

    session = AsyncCommandSession(
        tool_call_id="demo-1",
        command="ls -la /tmp",
        tool_name="bash",
    )
    async for chunk in session.run():
        print(chunk)
"""

from .executor import (
    AsyncCommandSession,
    CommandExecutor,
    build_shell_command,
    get_default_shell,
    get_executor,
)

__version__ = "0.1.0"

__all__ = [
    # 核心类
    "AsyncCommandSession",
    "CommandExecutor",
    # 工具函数
    "get_executor",
    "get_default_shell",
    "build_shell_command",
    # 元信息
    "__version__",
]
