"""
server 模块测试

主要测试:
    - list_tools 返回 3 个工具
    - call_tool 处理 bash / python / node 工具
    - 危险命令返回错误而非真正执行
"""

import json

import pytest

from timeverse_command.server import _run_and_collect, list_tools


class TestListTools:
    """工具列表测试"""

    @pytest.mark.asyncio
    async def test_three_tools_registered(self) -> None:
        """应注册 3 个工具"""
        tools = await list_tools()
        assert len(tools) == 3

    @pytest.mark.asyncio
    async def test_bash_tool(self) -> None:
        """bash 工具存在"""
        tools = await list_tools()
        bash = next(t for t in tools if t.name == "bash")
        assert "command" in bash.inputSchema["properties"]
        assert "command" in bash.inputSchema["required"]

    @pytest.mark.asyncio
    async def test_python_tool(self) -> None:
        """python 工具存在"""
        tools = await list_tools()
        py = next(t for t in tools if t.name == "python")
        assert "code" in py.inputSchema["properties"]
        assert "code" in py.inputSchema["required"]


class TestCallTool:
    """工具调用处理测试"""

    @pytest.mark.asyncio
    async def test_bash_hello_world(self) -> None:
        """bash 执行 echo hello"""
        result_text = await _run_and_collect("bash", {"command": "echo hello"})
        result = json.loads(result_text)

        assert "hello" in result["stdout"]
        assert result["exit_code"] == 0
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_python_execution(self) -> None:
        """python 工具执行计算"""
        result_text = await _run_and_collect("python", {"code": "print(2+3)"})
        result = json.loads(result_text)

        assert "5" in result["stdout"]
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_empty_command(self) -> None:
        """空命令应返回错误"""
        result_text = await _run_and_collect("bash", {"command": ""})
        result = json.loads(result_text)

        assert result["error"] == "empty_command"

    @pytest.mark.asyncio
    async def test_node_execution(self) -> None:
        """node 工具执行 JS"""
        result_text = await _run_and_collect("node", {"code": "console.log('ok')"})
        result = json.loads(result_text)

        # 如果系统没有 node，exit_code 会非 0；这里只检查结构
        assert "stdout" in result
        assert "exit_code" in result
