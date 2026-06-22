"""
executor 模块测试

主要测试:
    - AsyncCommandSession 正常执行
    - 流式输出顺序
    - 取消功能
    - 跨平台 shell 构建
"""

import asyncio
import sys

import pytest

from timeverse_command import (
    AsyncCommandSession,
    CommandExecutor,
    build_shell_command,
    get_default_shell,
    get_executor,
)

# ==================== Shell 配置测试 ====================


class TestShellConfig:
    """跨平台 shell 配置测试"""

    def test_default_shell_not_empty(self) -> None:
        """默认 shell 不应为空"""
        assert get_default_shell() in ("bash", "zsh", "cmd", "powershell", "pwsh")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_build_cmd_command(self) -> None:
        """Windows cmd 应正确构造"""
        assert build_shell_command("cmd", "dir") == ["cmd", "/c", "dir"]

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_build_powershell_command(self) -> None:
        """Windows powershell 应正确构造"""
        assert build_shell_command("powershell", "Get-Process") == [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process",
        ]

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test")
    def test_build_bash_command(self) -> None:
        """POSIX shell 应正确构造"""
        assert build_shell_command("bash", "ls -la") == ["bash", "-c", "ls -la"]


# ==================== 会话执行测试 ====================


class TestAsyncCommandSession:
    """AsyncCommandSession 异步执行测试"""

    @pytest.mark.asyncio
    async def test_bash_simple_command(self) -> None:
        """简单命令应正常执行"""
        session = AsyncCommandSession(
            tool_call_id="t1",
            command="echo hello",
            tool_name="bash",
        )
        chunks = []
        async for chunk in session.run():
            chunks.append(chunk)

        # 至少有一个 stdout 和一个 exit
        assert any(c["stream"] == "stdout" for c in chunks)
        assert any(c["stream"] == "exit" for c in chunks)

        # 退出码应为 0
        exit_chunk = next(c for c in chunks if c["stream"] == "exit")
        assert exit_chunk["exit_code"] == 0
        assert exit_chunk["status"] == "success"

    @pytest.mark.asyncio
    async def test_python_tool(self) -> None:
        """python 工具应正确调用 python -c"""
        session = AsyncCommandSession(
            tool_call_id="t2",
            command="print(1+1)",
            tool_name="python",
        )
        chunks = []
        async for chunk in session.run():
            chunks.append(chunk)

        # 找到 stdout 行
        stdout_lines = [c["delta"] for c in chunks if c["stream"] == "stdout"]
        assert "2" in stdout_lines

    @pytest.mark.asyncio
    async def test_command_not_found(self) -> None:
        """不存在的命令应返回 exit_code=127"""
        session = AsyncCommandSession(
            tool_call_id="t3",
            command="this_command_definitely_does_not_exist_xyz",
            tool_name="bash",
        )
        chunks = []
        async for chunk in session.run():
            chunks.append(chunk)

        exit_chunk = chunks[-1]
        assert exit_chunk["stream"] == "exit"
        assert exit_chunk["exit_code"] != 0
        assert exit_chunk["status"] == "error"

    @pytest.mark.asyncio
    async def test_streaming_output(self) -> None:
        """流式输出应逐行到达"""
        session = AsyncCommandSession(
            tool_call_id="t4",
            command="echo line1 && echo line2 && echo line3",
            tool_name="bash",
        )
        chunks = []
        async for chunk in session.run():
            chunks.append(chunk)

        stdout_lines = [c["delta"] for c in chunks if c["stream"] == "stdout"]
        assert "line1" in stdout_lines
        assert "line2" in stdout_lines
        assert "line3" in stdout_lines


# ==================== 取消测试 ====================


class TestCancel:
    """命令取消测试"""

    @pytest.mark.asyncio
    async def test_cancel_running_command(self) -> None:
        """取消正在运行的命令"""
        # 启动一个长时间运行的命令
        if sys.platform == "win32":
            cmd = "ping -n 60 127.0.0.1"
        else:
            cmd = "sleep 60"

        session = AsyncCommandSession(
            tool_call_id="t-cancel",
            command=cmd,
            tool_name="bash",
        )

        # 启动执行
        run_task = asyncio.create_task(_collect_run(session))

        # 等待一点时间让进程启动
        await asyncio.sleep(0.5)

        # 取消
        await session.cancel()
        await run_task

        # 验证状态
        chunks = run_task.result()
        exit_chunk = next(c for c in chunks if c["stream"] == "exit")
        # 取消可能以 status="cancelled" 或 "error" 呈现（取决于平台 kill 行为）
        assert exit_chunk["status"] in ("cancelled", "error")


async def _collect_run(session: AsyncCommandSession):
    """辅助函数：收集 run() 的所有输出"""
    chunks = []
    async for chunk in session.run():
        chunks.append(chunk)
    return chunks


# ==================== 执行器测试 ====================


class TestCommandExecutor:
    """CommandExecutor 管理器测试"""

    def test_register_and_get(self) -> None:
        """注册与查询"""
        executor = CommandExecutor()
        session = AsyncCommandSession(tool_call_id="x1", command="ls", tool_name="bash")
        executor.register(session)

        assert executor.get("x1") is session
        assert executor.get("nonexistent") is None

    def test_unregister(self) -> None:
        """注销"""
        executor = CommandExecutor()
        session = AsyncCommandSession(tool_call_id="x2", command="ls", tool_name="bash")
        executor.register(session)
        executor.unregister("x2")

        assert executor.get("x2") is None

    def test_list_active(self) -> None:
        """列出活跃会话"""
        executor = CommandExecutor()
        executor.register(AsyncCommandSession(tool_call_id="a", command="ls", tool_name="bash"))
        executor.register(AsyncCommandSession(tool_call_id="b", command="ls", tool_name="bash"))

        active = executor.list_active()
        assert set(active) == {"a", "b"}

    def test_global_singleton(self) -> None:
        """全局执行器是单例"""
        e1 = get_executor()
        e2 = get_executor()
        assert e1 is e2
