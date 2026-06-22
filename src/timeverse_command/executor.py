"""
异步命令执行器 - 跨平台执行 shell / Python / Node 命令

功能简述:
    提供异步、跨平台的命令执行能力，支持：
    1. bash / zsh / sh / cmd / powershell 任意 shell
    2. Python 代码执行
    3. Node.js 代码执行
    4. 流式 stdout / stderr 输出
    5. 用户中途取消
    6. 超时强制终止

主要类清单:
    - AsyncCommandSession: 单次命令会话
    - CommandExecutor: 会话管理器
    - get_executor: 全局执行器单例
    - get_default_shell / build_shell_command: 跨平台 shell 配置

使用示例:
    executor = get_executor()
    session = AsyncCommandSession(
        tool_call_id="demo-1",
        command="echo hello",
        tool_name="bash",
    )
    executor.register(session)
    try:
        async for chunk in session.run():
            print(chunk)
    finally:
        executor.unregister(session.tool_call_id)
"""
import asyncio
import platform
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

# ==================== 跨平台 Shell 配置 ====================


def get_default_shell() -> str:
    """
    获取当前平台的默认 shell

    Returns:
        str: shell 命令（macOS: zsh, Linux: bash, Windows: cmd）

    Example:
        >>> get_default_shell()  # 在 macOS 上
        'zsh'
    """
    system = platform.system().lower()
    if system == "windows":
        return "cmd"
    elif system == "darwin":
        return "zsh"
    else:
        return "bash"


def build_shell_command(shell: str, command: str) -> List[str]:
    """
    构造跨平台 shell 执行命令

    Args:
        shell: shell 名称（bash / zsh / cmd / powershell）
        command: 要执行的命令

    Returns:
        List[str]: 可直接传给 asyncio.create_subprocess_exec 的参数列表

    Example:
        >>> build_shell_command("bash", "ls -la")
        ['bash', '-c', 'ls -la']
        >>> build_shell_command("cmd", "dir")
        ['cmd', '/c', 'dir']
    """
    system = platform.system().lower()
    if system == "windows":
        if shell == "cmd":
            return ["cmd", "/c", command]
        elif shell in ("powershell", "pwsh"):
            return ["powershell", "-NoProfile", "-Command", command]
        else:
            return ["bash", "-c", command]
    else:
        return [shell, "-c", command]


# ==================== 异步命令会话 ====================


@dataclass
class AsyncCommandSession:
    """
    异步命令会话

    表示一次具体的命令执行过程。
    支持流式输出、超时终止、用户中途取消。

    Attributes:
        tool_call_id: 调用方传入的唯一 ID（用于关联 tool_call_log）
        command: 要执行的命令 / 代码
        tool_name: 工具名（bash / python / node）
        cwd: 工作目录（None = 继承当前目录）
        timeout: 超时秒数（None = 不限时）
        env: 额外环境变量
        use_pty: 是否使用 PTY 模式（仅在 TimeVerse 客户端生效，MCP 模式固定为 pipe）
    """
    tool_call_id: str
    command: str
    tool_name: str = "bash"
    cwd: Optional[str] = None
    timeout: Optional[int] = None
    env: Optional[Dict[str, str]] = None
    use_pty: bool = False
    _process: Optional[asyncio.subprocess.Process] = field(default=None, init=False, repr=False)
    _started_at: Optional[float] = field(default=None, init=False, repr=False)
    _cancelled: bool = field(default=False, init=False, repr=False)

    async def run(self) -> AsyncIterator[Dict[str, Any]]:
        """
        异步执行命令，yield 流式输出块

        Yields:
            Dict[str, Any]: 输出块
                - {"stream": "stdout", "delta": "..."}
                - {"stream": "stderr", "delta": "..."}
                - {"stream": "exit", "exit_code": int, "duration_ms": int,
                   "status": "success"|"error"|"cancelled"}

        Example:
            async for chunk in session.run():
                if chunk["stream"] == "stdout":
                    print(chunk["delta"], end="")
                elif chunk["stream"] == "exit":
                    print(f"\\nexit={chunk['exit_code']}")
        """
        self._started_at = time.time()
        self._cancelled = False

        # 构造执行命令
        if self.tool_name == "python":
            python_bin = "python3" if platform.system() != "Windows" else "python"
            args = [python_bin, "-c", self.command]
        elif self.tool_name == "node":
            args = ["node", "-e", self.command]
        else:
            # bash / zsh / sh 等
            shell_override = self.env.get("SHELL_OVERRIDE") if self.env else None
            shell = shell_override or get_default_shell()
            args = build_shell_command(shell, self.command)

        # 启动子进程
        try:
            self._process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
                env={**__import__("os").environ, **(self.env or {})} if self.env else None,
            )
        except FileNotFoundError as e:
            yield {
                "stream": "exit",
                "exit_code": 127,
                "duration_ms": 0,
                "status": "error",
                "error": f"命令未找到: {e}",
            }
            return

        # 启动两个读取协程（stdout / stderr 并行读取）
        async def read_stream(stream: asyncio.StreamReader, stream_name: str):
            """逐行读取子进程的 stdout 或 stderr"""
            while True:
                line = await stream.readline()
                if not line:
                    break
                try:
                    decoded = line.decode("utf-8", errors="replace")
                except Exception:
                    decoded = line.decode("latin-1", errors="replace")
                # 去掉行尾换行符
                decoded = decoded.rstrip("\n").rstrip("\r")
                if decoded:
                    yield {"stream": stream_name, "delta": decoded}

        # 合并 stdout / stderr 的流
        async def merge_streams():
            """合并两个 stream 的输出到统一队列"""
            queue: asyncio.Queue = asyncio.Queue()

            async def pump(stream: asyncio.StreamReader, name: str):
                async for chunk in read_stream(stream, name):
                    await queue.put(chunk)
                await queue.put({"_eof": name})

            tasks = [
                asyncio.create_task(pump(self._process.stdout, "stdout")),  # type: ignore
                asyncio.create_task(pump(self._process.stderr, "stderr")),  # type: ignore
            ]

            eof_count = 0
            while eof_count < 2:
                item = await queue.get()
                if "_eof" in item:
                    eof_count += 1
                else:
                    yield item

            await asyncio.gather(*tasks, return_exceptions=True)

        # 流式产出
        async for chunk in merge_streams():
            yield chunk

        # 等待进程结束
        try:
            if self.timeout:
                exit_code = await asyncio.wait_for(
                    self._process.wait(), timeout=self.timeout  # type: ignore
                )
            else:
                exit_code = await self._process.wait()  # type: ignore
        except asyncio.TimeoutError:
            if self._process and self._process.returncode is None:
                self._process.kill()
                await self._process.wait()
            yield {"stream": "stderr", "delta": f"[执行超时 {self.timeout}s，已强制终止]"}
            exit_code = 124

        # 计算耗时
        duration_ms = int((time.time() - (self._started_at or time.time())) * 1000)

        # 判断状态
        if self._cancelled:
            status = "cancelled"
        elif exit_code == 0:
            status = "success"
        else:
            status = "error"

        yield {
            "stream": "exit",
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "status": status,
        }

    async def cancel(self) -> None:
        """
        取消正在执行的命令

        调用后子进程会被 SIGKILL（POSIX）/ TerminateProcess（Windows），
        后续 run() 协程会收到 cancelled 状态的 exit 块。
        """
        self._cancelled = True
        if self._process and self._process.returncode is None:
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                # 进程已退出，无需处理
                pass


# ==================== 会话管理器 ====================


class CommandExecutor:
    """
    命令执行器 - 管理所有活跃的命令会话

    用于在 MCP Server 进程内跟踪正在执行的命令，
    方便外部 API 取消指定 tool_call_id 的命令。
    """

    def __init__(self) -> None:
        """初始化执行器（空会话表）"""
        self._sessions: Dict[str, AsyncCommandSession] = {}

    def register(self, session: AsyncCommandSession) -> None:
        """
        注册会话到管理器

        Args:
            session: 异步命令会话实例
        """
        self._sessions[session.tool_call_id] = session

    def unregister(self, tool_call_id: str) -> None:
        """
        从管理器移除会话

        Args:
            tool_call_id: 工具调用 ID
        """
        self._sessions.pop(tool_call_id, None)

    def get(self, tool_call_id: str) -> Optional[AsyncCommandSession]:
        """
        查询会话

        Args:
            tool_call_id: 工具调用 ID

        Returns:
            Optional[AsyncCommandSession]: 找到则返回会话实例，否则 None
        """
        return self._sessions.get(tool_call_id)

    def list_active(self) -> List[str]:
        """
        列出所有活跃会话的 tool_call_id

        Returns:
            List[str]: tool_call_id 列表
        """
        return list(self._sessions.keys())

    async def cancel(self, tool_call_id: str) -> bool:
        """
        取消指定会话

        Args:
            tool_call_id: 工具调用 ID

        Returns:
            bool: 是否成功取消（会话存在时返回 True）
        """
        session = self._sessions.get(tool_call_id)
        if not session:
            return False
        await session.cancel()
        return True


# ==================== 全局单例 ====================

_executor: Optional[CommandExecutor] = None


def get_executor() -> CommandExecutor:
    """
    获取全局执行器单例

    Returns:
        CommandExecutor: 进程内唯一的执行器实例
    """
    global _executor
    if _executor is None:
        _executor = CommandExecutor()
    return _executor
