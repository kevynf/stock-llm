# 参与 StockLLM 贡献

[简体中文](CONTRIBUTING.md) | [English](CONTRIBUTING.en.md)

改动需要保持来源记录、数据新鲜度、历史时间边界、模型限制和本地存储行为。

## 开始之前

- 新建 Issue 前先搜索已有问题。
- 大范围产品改动、新 Provider、数据结构变化或研究语义变化，请先通过 Issue 讨论再实现。
- 不要在 Issue、日志、测试数据或截图中包含 API 密钥、系统密钥库内容、私人研究历史或诊断导出。
- Pull Request 应保持聚焦；无关重构与行为变化请拆开提交。

## 开发环境

环境要求为 Python 3.12+、Node.js 20+ 和 pnpm 9+。在 Windows PowerShell 中运行：

```powershell
git clone https://github.com/kevynf/stock-llm.git
cd stock-llm
.\scripts\bootstrap.ps1
```

在两个终端分别运行后端和前端：

```powershell
.\scripts\dev-backend.ps1
.\scripts\dev-frontend.ps1
```

应用地址为 <http://127.0.0.1:5173>，OpenAPI 页面位于 <http://127.0.0.1:8768/docs>。

## 工程约束

- 准入、研究检查和排序逻辑保留在后端引擎中。前端只渲染 API 状态，不得重新实现研究规则。
- 保留 Provider 级来源、有效日期、抓取时间和新鲜度元数据，不根据字段名或数值推断来源。
- 历史研究不得使用请求日期之后才发布的信息。
- Provider 文本和模型输出均视为不可信输入。模型选择的股票与证据 ID 必须位于服务端白名单中。
- 示例快照必须显式设置 `STOCKLLM_ENABLE_DEMO=1` 才能使用，且不得成为生产环境回退。
- 密钥通过系统密钥库保存，不得写入 SQLite、日志、测试数据或已提交的环境文件。
- 共享界面使用 shadcn/ui 官方组件，并遵守[界面设计系统](docs/design-system.md)。

## 测试

提交 Pull Request 前运行完整检查：

```powershell
.\scripts\check.ps1
```

该命令会运行后端测试和前端 TypeScript 生产构建。自动化测试必须可重复，不能依赖实时行情或模型服务。

行为变化应增加聚焦测试，尤其是 Provider 归一化、历史截断、证据校验、数据库事务和 API 契约。界面变化应在项目支持的 `1280×720` 桌面基线下核验相关流程，并检查浏览器控制台。

## Pull Request 要求

Pull Request 应包括：

- 简洁说明用户可见或架构层面的变化；
- 说明改动原因及其对信任边界的影响；
- 列出已运行的测试和结果；
- 可见界面变化附带截图；
- 存储数据或 API 契约变化附带迁移与兼容性说明。

不要提交生成的安装包、本地数据库、缓存、真实诊断或密钥。改动同时影响中英文文档时，应保持两个版本同步。

提交贡献即表示你同意该贡献按照仓库的 [MIT License](LICENSE) 授权。
