# 架构

[简体中文](architecture.md) | [English](architecture.en.md)

## 职责边界

`frontend` 只渲染 API 状态，不计算候选准入、研究检查、排序、模型提示或 Provider 回退行为。

`backend/stockllm/engine.py` 负责确定性的候选准入与研究清单。`providers.py` 负责数据源归一化和可追溯信息。`ai.py` 负责模型访问，并校验模型选择的股票代码和证据引用仍然位于当前研究任务范围内。

SQLite 保存事务元数据和 JSON 快照。将来接入经过验证的实时 Provider 后，市场历史缓存适配器可以在应用数据目录中写入分区 Parquet 文件。

## 信任模型

- Provider 文本和新闻均视为不可信数据。
- 模型输出必须经过 Pydantic 校验以及候选/证据白名单校验，不能直接信任。
- 工具执行由服务端内置 Skills 决定；模型不能执行 SQL、文件系统、Shell、网络、MCP 或交易命令。
- 示例数据使用独立且可见的模式，不作为实时请求的自动回退。

## Windows 桌面运行时

Tauri 2 桌面壳会在随机回环端口启动 PyInstaller 打包的 API sidecar，等待 `/api/v1/health` 就绪，将 API 地址注入前端，并在应用退出时终止 sidecar。浏览器开发模式和桌面模式共享同一套 REST/SSE 契约。

- 每次启动都会生成独立 token 并通过 sidecar 环境变量传递。JSON 请求使用 `X-StockLLM-Token`；只有事件接口的 SSE 连接通过查询参数传递 token。
- 打包后的数据保存在 `%LOCALAPPDATA%\StockLLM`，NSIS 卸载程序不会删除该目录。
- sidecar 健康检查通过前主窗口保持隐藏；第二个应用实例会聚焦已经打开的窗口。
- Rust MSVC 和 Visual C++ 工具链可用时，`scripts/build-desktop.ps1` 会生成 `packaging/dist/StockLLM_<version>_x64-setup.exe`。
