# 架构

[简体中文](architecture.md) | [English](architecture.en.md)

## 职责边界

`frontend` 只渲染 API 状态，不计算候选准入、研究检查、排序、模型提示或 Provider 回退行为。

`backend/stockllm/engine.py` 负责确定性的候选准入与研究清单。`providers/` 负责数据源归一化和可追溯信息：`base.py` 定义稳定契约，`demo.py` 隔离开发示例数据，`live.py` 实现 AKShare 与 BaoStock 市场研究，`content.py` 管理资讯抓取和缓存，`status.py` 管理数据源探测，包入口只负责兼容导出和模式装配。`ai.py` 负责模型访问，并校验模型选择的股票代码和证据引用仍然位于当前研究任务范围内。

AKShare 调用通过进程级锁串行执行，并对瞬时异常进行一次有界重试；重试仍失败时保留数据源级错误，不伪造内容。这样可避免第三方库的全局 Pandas/进度状态在并发研究中互相干扰。

SQLite 保存事务元数据和 JSON 快照。实时 Provider 在应用数据目录中写入 Parquet 市场缓存；缓存先写同目录临时文件再原子替换，损坏或 schema 不兼容的文件按缓存未命中处理并回源。

## 服务端分层与任务执行

- `main.py` 通过显式 `ApplicationServices` 依赖图装配 FastAPI、桌面鉴权中间件和进程级依赖；`create_app` 可在测试中创建隔离的应用实例，同时模块保留生产入口。`routers/` 按系统、市场、自选股、模型设置、研究任务和聊天边界暴露 API。
- `MarketService` 负责 Provider 调用、数据源状态缓存和 Provider 诊断。`WatchlistService` 负责证券校验和全有或全无的自选股变更。`ModelSettingsService` 负责模型配置、连接状态迁移和模型健康检查。`SystemService` 负责临时存储、日志、诊断和导出编排。`ChatService` 独立负责会话、上下文装配、模型交互和技能目录；`ResearchService` 只负责研究任务生命周期编排、读取、删除和事件重放，并通过显式组合的兼容代理保留旧聊天方法。这些服务均不直接执行 SQL。`main.py` 在 `ApplicationServices` 中共享一个 `ModelGateway`，再分别注入聊天和研究服务。`storage.py` 负责数据目录、跨进程安全的缓存锁、原子缓存替换、容错 JSON 缓存读取、连接策略、schema 初始化、迁移、显式提交/回滚和 SQLite 锁等待配置；`repositories/` 分别封装自选股、设置、聊天、研究任务和诊断业务快照 SQL；`Database` 组合这些仓储并作为稳定门面。数据库通过 `schema_meta` 记录 schema 版本，并拒绝打开比当前应用更新的数据库。
- `ChatService` 通过依赖注入复用同一个 `MarketService`，不直接装配 Provider。发送给模型的个股历史点、资讯条数与摘要、外部正文、历史消息和总上下文均有独立上限；应用截断正文时会保留显式标记，避免模型把部分内容当作全文。
- `ResearchTaskRunner` 使用有限 worker 和有限等待队列执行研究任务。API 创建任务后立即返回 `pending`；客户端通过 REST/SSE 观察状态。sidecar 重启时，数据库中仍为 `pending` 或 `running` 的任务会恢复为待执行并重新排队。
- 研究事件带有递增 SSE `id`。客户端重连时发送 `Last-Event-ID`，服务端只重放尚未确认的事件。可见的任务状态转换及其事件在同一个 SQLite 事务中提交，因此客户端不会观察到缺少对应终态事件的终态快照。
- 应用服务先把 Provider 和持久化异常翻译为应用层异常，路由只把这些异常映射为 HTTP，并且不直接导入 Provider 或 engine 实现。`ResearchService` 同时拥有策略目录、队列准入和带状态校验的删除规则。

## API 契约

后端 OpenAPI schema 是前端 API 类型的单一来源。`scripts/export-openapi.py` 导出 schema，`openapi-typescript` 生成 `frontend/src/generated/openapi.ts`；前端领域类型直接引用生成的 Pydantic schema。市场研究、数据源、健康检查、模型配置、技能、存储、日志、系统诊断和批量操作均使用命名响应模型，不再由前端重复维护响应结构。CI 会重新生成并检查文件差异，防止前后端契约漂移。

Pydantic 契约按领域位于 `models/`：`common.py` 保存共享枚举和元数据，`market.py`、`research.py`、`system.py`、`watchlist.py`、`chat.py` 分别管理对应 API 模型。包入口保留稳定导出，因此内部拆分不会改变现有服务导入或 OpenAPI schema 名称。

FastAPI 入口仅负责生命周期、中间件、健康检查、路由装配和静态资源挂载。业务端点按 `market`、`watchlist`、`model_settings`、`research`、`chats`、`system` 模块组织；结构测试保证除健康检查外的 API 不会重新回流到入口模块。

路由是传输适配器：校验请求模型、调用应用服务，并把结果或类型化异常映射为 HTTP；聊天技能目录也遵循同一服务边界。结构测试同时保护 Provider/engine 依赖边界，并确保缓存适配器依赖 storage 而非 diagnostics。

## 信任模型

- Provider 文本和新闻均视为不可信数据。
- 模型输出必须经过 Pydantic 校验以及候选/证据白名单校验，不能直接信任。
- 工具执行由服务端内置 Skills 决定；模型不能执行 SQL、文件系统、Shell、网络、MCP 或交易命令。
- 示例数据使用独立且可见的模式，不作为实时请求的自动回退。

## Windows 桌面运行时

Tauri 2 桌面壳会在随机回环端口启动 PyInstaller 打包的 API sidecar，等待 `/api/v1/health` 就绪，将 API 地址注入前端，并在应用退出时终止 sidecar。浏览器开发模式和桌面模式共享同一套 REST/SSE 契约。

- 每次启动都会生成独立 token 并通过 sidecar 环境变量传递。JSON 请求使用 `X-StockLLM-Token`；只有事件接口的 SSE 连接通过查询参数传递 token。
- Windows 无控制台 sidecar 将标准输出和错误流重定向到空设备，避免第三方进度条写入无效句柄；应用诊断继续写入结构化轮转日志。
- 打包后的数据保存在 `%LOCALAPPDATA%\StockLLM`，NSIS 卸载程序不会删除该目录。
- sidecar 健康检查通过前主窗口保持隐藏；第二个应用实例会聚焦已经打开的窗口。
- Python 3.12+、Rust MSVC 和 Visual C++ 工具链可用时，`scripts/build-desktop.ps1 -PreflightOnly` 会先验证解释器、打包依赖和 Tauri CLI；完整脚本会生成 `packaging/dist/StockLLM_<version>_x64-setup.exe`。
- PyInstaller 只收集运行时子模块，排除依赖包中的测试、示例和基准模块；打包后仍通过真实 AKShare、BaoStock、Parquet 和资讯调用验收。
