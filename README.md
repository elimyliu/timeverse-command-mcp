# timeverse-command-mcp

> 跨平台执行 shell / Python / Node 命令的 [MCP (Model Context Protocol)](https://modelcontextprotocol.io) Server

[![PyPI](https://img.shields.io/pypi/v/timeverse-command-mcp)](https://pypi.org/project/timeverse-command-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/timeverse-command-mcp)](https://pypi.org/project/timeverse-command-mcp/)
[![License](https://img.shields.io/github/license/elimyliu/timeverse-command-mcp)](LICENSE)

---

## 它能做什么？

让任意支持 MCP 的 AI 客户端（Timeverse Studio、Claude Desktop、Cursor、Continue 等）通过三个工具**直接操作你的本地机器**：

| 工具 | 作用 | 适用平台 |
|------|------|---------|
| `bash` | 执行 shell 命令 | macOS / Linux / Windows |
| `python` | 执行 Python 代码片段 | 全平台 |
| `node` | 执行 JavaScript 代码片段 | 全平台 |

典型用法（让 Claude 帮你做）：

```
"用 bash 看一下 /tmp 目录下最大的 5 个文件"
"用 python 算一下 1+2+...+100"
"用 node 把这个 JSON 解析后告诉我 user.name"
```

---

## 安装

### 方式 1：pip（推荐）

```bash
pip install timeverse-command-mcp
```

安装完成后会得到一个 `timeverse-command-mcp` 命令。

### 方式 2：源码安装（开发用）

```bash
git clone https://github.com/elimyliu/timeverse-command-mcp.git
cd timeverse-command-mcp
pip install -e ".[dev]"
```

---

## 接入 Claude Desktop

编辑 Claude Desktop 配置文件（位置见下表）：

| 操作系统 | 配置路径 |
|---------|---------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

加入以下内容：

```json
{
  "mcpServers": {
    "timeverse-command": {
      "command": "timeverse-command-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

重启 Claude Desktop，工具列表中会出现 `bash` / `python` / `node` 三个工具。

> 详细配置说明、Cursor / Continue / Cline 等其他客户端的接入方式，请参考 [docs/USAGE.md](docs/USAGE.md)。

## Python API

除了作为 MCP Server，本包也可以作为 Python 库使用：

```python
import asyncio
from timeverse_command import AsyncCommandSession

async def main():
    session = AsyncCommandSession(
        tool_call_id="demo-1",
        command="echo hello && echo world",
        tool_name="bash",
    )

    async for chunk in session.run():
        if chunk["stream"] == "stdout":
            print(f"[out] {chunk['delta']}")
        elif chunk["stream"] == "exit":
            print(f"[exit] code={chunk['exit_code']} status={chunk['status']}")

asyncio.run(main())
```

输出：

```
[out] hello
[out] world
[exit] code=0 status=success
```

更多 API（取消、全局执行器等）见 [docs/USAGE.md](docs/USAGE.md)。

---

## 开发

```bash
# 克隆
git clone https://github.com/elimyliu/timeverse-command-mcp.git
cd timeverse-command-mcp

# 安装依赖（含 dev 工具）
pip install -e ".[dev]"

# 运行测试
pytest

# 代码风格
ruff check src/
ruff format src/

# 类型检查
mypy src/
```

---

## 协议

- **MCP 传输**: stdio（标准）
- **不依赖**任何私有扩展，可在所有支持 MCP stdio 的客户端中使用
- 增强能力（流式 / 取消 / 危险确认）由 TimeVerse Studio 客户端专属提供，其他客户端以"基础能力"运行

---

## 许可证

MIT © TimeVerse Studio
