# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-15

### Added
- 初始发布
- `bash` 工具：跨平台执行 shell 命令（macOS / Linux / Windows）
- `python` 工具：执行 Python 3 代码片段
- `node` 工具：执行 JavaScript 代码片段
- 流式 stdout / stderr 输出
- 命令超时与强制终止
- 8 类高危命令模式检测（rm -rf /, mkfs, dd, fork bomb 等）
- Python API：`AsyncCommandSession` / `CommandExecutor` / `get_executor`
- PyPI 发布：可通过 `pip install timeverse-command-mcp` 安装
- 控制台入口脚本：`timeverse-command-mcp`
