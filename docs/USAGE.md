# 使用指南

> 详细的安装、配置、故障排查说明

## 目录

- [客户端接入](#客户端接入)
  - [Claude Desktop](#claude-desktop)
  - [Cursor](#cursor)
  - [Continue (VS Code)](#continue-vs-code)
  - [Cline (VS Code)](#cline-vs-code)
- [配置项详解](#配置项详解)
- [故障排查](#故障排查)
- [Python API](#python-api)

---

## 客户端接入

### Claude Desktop

#### 配置文件位置

| 操作系统 | 路径 |
|---------|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

#### 基础配置（推荐）

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

#### 使用 uvx（无需预装）

```json
{
  "mcpServers": {
    "timeverse-command": {
      "command": "uvx",
      "args": ["timeverse-command-mcp"],
      "env": {}
    }
  }
}
```

#### 开发模式（源码）

```json
{
  "mcpServers": {
    "timeverse-command": {
      "command": "python",
      "args": ["-m", "timeverse_command.server"],
      "cwd": "/path/to/timeverse-command-mcp/src",
      "env": {}
    }
  }
}
```

#### 验证安装

1. 重启 Claude Desktop
2. 在聊天输入框左下角看到 🔧 工具图标，点击查看工具列表
3. 应该能看到 `bash` / `python` / `node` 三个工具（前面带 `timeverse-command` 命名空间）
4. 在对话中试试："用 bash 看看 /tmp 目录下有什么文件"

#### 查看日志

Claude Desktop 的 MCP 日志路径：

- macOS: `~/Library/Logs/Claude/mcp*.log`
- Windows: `%APPDATA%\Claude\Logs\mcp*.log`

或通过菜单：`Claude → Help → Show Logs`。

---

### Cursor

1. 打开 Cursor 设置（`Cmd + ,` / `Ctrl + ,`）
2. 搜索 `MCP` 或进入 `Features → Model Context Protocol`
3. 点击 `+ Add new global MCP server`
4. 填入：

   | 字段 | 值 |
   |------|-----|
   | Name | `timeverse-command` |
   | Type | `command` |
   | Command | `timeverse-command-mcp` |

5. 保存后重启 Cursor

或在 `~/.cursor/mcp.json` 中直接写入：

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

---

### Continue (VS Code)

编辑 `~/.continue/config.json`：

```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "name": "timeverse-command",
        "transport": {
          "type": "stdio",
          "command": "timeverse-command-mcp",
          "args": []
        }
      }
    ]
  }
}
```

重启 VS Code 后生效。

---

### Cline (VS Code)

1. 打开 Cline 面板
2. 点击右上角 `MCP Servers` 图标
3. 选择 `Install MCP Server` → `Install from JSON`
4. 粘贴：

```json
{
  "name": "timeverse-command",
 "command": "timeverse-command-mcp",
  "args": [],
  "env": {}
}
```

---

## 配置项详解

```json
{
  "mcpServers": {
    "timeverse-command": {
      "command": "timeverse-command-mcp",   // 可执行命令
      "args": [],                            // 命令参数（一般留空）
      "env": {                               // 环境变量
        "PYTHONUNBUFFERED": "1",             // 推荐：禁用 Python 输出缓冲
        "SHELL_OVERRIDE": "bash"             // 可选：强制使用指定 shell
      }
    }
  }
}
```

### 常用环境变量

| 变量 | 作用 |
|------|------|
| `PYTHONUNBUFFERED=1` | 确保 Python 输出实时刷新（不缓冲） |
| `SHELL_OVERRIDE=bash` | 强制使用 bash 而非默认 shell（macOS 上默认 zsh） |
| `MCP_TIMEOUT=120` | 自定义工具调用超时（秒） |

---

## 故障排查

### 问题 1：工具列表中找不到 timeverse-command

**可能原因**：

- 配置文件路径不对
- JSON 格式错误（注意尾逗号、注释）
- `timeverse-command-mcp` 不在 PATH 中

**排查步骤**：

```bash
# 1. 验证命令可用
which timeverse-command-mcp
timeverse-command-mcp --help  # 应立即启动（stdio 模式不会输出）

# 2. 验证 JSON 格式
python -c "import json; json.load(open('/path/to/claude_desktop_config.json'))"

# 3. 查看 MCP 日志
tail -f ~/Library/Logs/Claude/mcp*.log  # macOS
```

### 问题 2：命令执行后无输出

**原因**：MCP stdout 不能有日志，所有日志必须走 stderr（包内已处理）。

如果仍无输出，检查：

```bash
# 直接运行看错误
timeverse-command-mcp 2>&1
# 正常情况：进程挂起等待 stdin 输入（这是正常的）
# 异常情况：会输出 Python 错误堆栈到 stderr
```

### 问题 3：Python 工具提示 "No module named"

**原因**：Claude Desktop 使用的 Python 环境与终端不同。

**解决**：

```json
{
  "mcpServers": {
    "timeverse-command": {
      "command": "/usr/local/bin/python3",  // 显式指定 Python 路径
      "args": ["-m", "timeverse_command.server"]
    }
  }
}
```

### 问题 4：macOS 提示 "无法验证开发者"

**解决**：

```bash
# 临时允许（一次性）
xattr -d com.apple.quarantine $(which timeverse-command-mcp)
```

或在 `系统设置 → 隐私与安全性` 中点击"仍要打开"。

### 问题 5：Windows 上 bash 工具不可用

**原因**：Windows 默认没有 bash。

**解决**：

- 安装 [Git for Windows](https://git-scm.com/) 或 [WSL](https://learn.microsoft.com/en-us/windows/wsl/)
- 或者使用 `cmd` / `powershell`（包内已自动适配）

---

## Python API

除了 MCP Server，本包也是可独立 import 的 Python 库。

### 基础用法

```python
import asyncio
from timeverse_command import AsyncCommandSession


async def main():
    session = AsyncCommandSession(
        tool_call_id="demo-1",
        command="ls -la /tmp",
        tool_name="bash",
    )

    async for chunk in session.run():
        match chunk["stream"]:
            case "stdout":
                print(f"[stdout] {chunk['delta']}")
            case "stderr":
                print(f"[stderr] {chunk['delta']}", file=sys.stderr)
            case "exit":
                print(f"[exit] code={chunk['exit_code']} duration={chunk['duration_ms']}ms")


asyncio.run(main())
```

### 全局执行器（用于取消）

```python
import asyncio
from timeverse_command import get_executor, AsyncCommandSession


async def main():
    executor = get_executor()
    session = AsyncCommandSession(
        tool_call_id="long-running",
        command="sleep 60",
        tool_name="bash",
    )
    executor.register(session)

    run_task = asyncio.create_task(_collect(session))
    await asyncio.sleep(2)

    # 取消
    await executor.cancel("long-running")
    await run_task


async def _collect(session):
    chunks = []
    async for chunk in session.run():
        chunks.append(chunk)
    return chunks


asyncio.run(main())
```

### 超时控制

```python
session = AsyncCommandSession(
    tool_call_id="t",
    command="some-long-task",
    tool_name="bash",
    timeout=30,  # 30 秒后强制 kill
)
```

---

## 发布到 PyPI（仅维护者）

```bash
# 1. 安装构建工具
pip install build twine

# 2. 清理 + 构建
rm -rf dist/ build/
python -m build

# 3. 上传到 Test PyPI（先测试）
twine upload --repository testpypi dist/*

# 4. 验证可从 Test PyPI 安装
pip install --index-url https://test.pypi.org/simple/ timeverse-command-mcp

# 5. 正式上传
twine upload dist/*
```

GitHub Actions 自动发布：`.github/workflows/release.yml`

```yaml
name: Release
on:
  push:
    tags: ['v*']
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_TOKEN }}
```
