<div align="center">
  <img src="docs/assets/stockllm-icon.svg" width="88" height="88" alt="StockLLM 标志">
  <h1>StockLLM</h1>
  <p><strong>本地运行的 A 股筛选与研究应用。</strong></p>
  <p>
    <a href="README.md">简体中文</a> |
    <a href="README.en.md">English</a>
  </p>
  <p>
    <a href="https://github.com/kevynf/stock-llm/actions/workflows/ci.yml"><img alt="持续集成" src="https://github.com/kevynf/stock-llm/actions/workflows/ci.yml/badge.svg"></a>
    <a href="https://github.com/kevynf/stock-llm/actions/workflows/build-windows-desktop.yml"><img alt="Windows 构建" src="https://github.com/kevynf/stock-llm/actions/workflows/build-windows-desktop.yml/badge.svg"></a>
    <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white">
    <img alt="Node.js 20+" src="https://img.shields.io/badge/Node.js-20%2B-5FA04E?logo=nodedotjs&logoColor=white">
    <img alt="Tauri 2" src="https://img.shields.io/badge/Tauri-2-24C8DB?logo=tauri&logoColor=white">
    <a href="LICENSE"><img alt="MIT 许可证" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
  </p>
</div>

StockLLM 是一个本地运行的 A 股筛选与个股研究应用。它使用规则筛选候选股票，也可以调用 DeepSeek 比较候选并回答与当前研究数据有关的后续问题。项目包含 React/FastAPI Web 应用和 Tauri 2 Windows 桌面版。

> [!CAUTION]
> 本项目仅用于辅助研究和学习，不构成投资建议，不提供自动交易、收益承诺或个性化财富管理服务。

## 功能

- 设置风险承受、投资周期、研究策略和研究日期。
- 使用趋势、质量或稳健低波动规则筛选最多 20 只候选股票。
- 查看行情、基本面和新闻数据的来源、有效日期、抓取时间及可用状态。
- 可选用 DeepSeek 比较候选，并回答与当前研究数据有关的后续问题。
- 查看候选表、价格图、基本面、新闻、风险、历史研究、对话、自选股和数据源状态。
- 研究历史和自选股保存在本机 SQLite，API 密钥保存在操作系统密钥库。

## 使用截图

<table>
  <tr>
    <td width="50%"><img src="docs/assets/research-chat.png" alt="AI 研究对话"></td>
    <td width="50%"><img src="docs/assets/selection-workspace.png" alt="选股研究工作台"></td>
  </tr>
  <tr>
    <td align="center"><strong>AI 研究对话</strong></td>
    <td align="center"><strong>可配置的研究工作台</strong></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/assets/selection-results.png" alt="筛选结果与候选股票"></td>
    <td width="50%"><img src="docs/assets/stock-research.png" alt="带价格图与来源信息的个股研究"></td>
  </tr>
  <tr>
    <td align="center"><strong>筛选结果与候选股票</strong></td>
    <td align="center"><strong>个股行情与数据来源</strong></td>
  </tr>
</table>

## 研究流程

1. 选择风险承受、投资周期、研究策略和数据日期。
2. StockLLM 读取所需的市场与公司数据，并记录来源和日期。
3. 所选规则生成候选列表和逐项检查结果。
4. 如果已经配置 DeepSeek，则由它比较候选并给出带引用的前三项结果。
5. 应用将条件、候选、引用和结果保存为一条本地研究记录。

实现细节单独记录在[架构文档](docs/architecture.md)中。

## 环境要求

- Python 3.12+
- Node.js 20+
- pnpm 9+
- Windows 10/11，用于 Credential Manager 和打包后的桌面应用

## 快速开始

> [!TIP]
> Windows 用户可以直接从 [GitHub Releases](https://github.com/kevynf/stock-llm/releases/latest) 下载最新的 `StockLLM_<版本>_x64-setup.exe`，无需克隆仓库或自行构建。

仓库脚本会准备所需的 Python 与 Node.js 依赖。在 Windows PowerShell 中运行：

```powershell
git clone https://github.com/kevynf/stock-llm.git
cd stock-llm
.\scripts\bootstrap.ps1
```

一键启动后端和前端：

```powershell
.\scripts\dev.ps1
```

访问 <http://127.0.0.1:5173>。按 `Ctrl+C` 可同时停止两个服务。需要单独调试时，仍可分别运行 `dev-backend.ps1` 和 `dev-frontend.ps1`。

安装脚本默认使用清华 PyPI 和 npmmirror，且只作用于本次安装。可以仅为当前命令覆盖镜像，不修改全局包管理器配置：

```powershell
.\scripts\bootstrap.ps1 `
  -PyPiIndex "https://pypi.org/simple" `
  -NpmRegistry "https://registry.npmjs.org"
```

如果机器上有多个 Python，可以用 `-PythonPath` 明确选择 3.12 或更高版本的解释器；已有 `.venv` 不会被脚本自动删除或替换。

## 模型服务配置

StockLLM 默认使用 `https://api.deepseek.com` 和模型 `deepseek-v4-flash`。请求采用 OpenAI 兼容的 Chat Completions 格式。任何实现该格式的第三方服务都可以使用，只需在应用“设置”页填写对应的 Base URL、模型标识和 API 密钥。服务必须支持 Bearer 认证和 `/chat/completions`；候选比较还需要通过 `response_format: {"type": "json_object"}` 支持 JSON Mode。

后端通过 `keyring` 将 API 密钥写入系统密钥库。请妥善保管密钥。未配置密钥时，StockLLM 仍会生成规则候选和证据，并明确标记“AI 待连接”。

配置的模型服务只参与候选比较和只读研究对话，不能修改自选股、研究记录或设置，也不能绕过候选池和证据引用校验。

## 数据来源

StockLLM 支持两种研究视图：

- **最新数据**：日期由各数据源分别确认。AKShare 价格显示抓取时间，BaoStock 日线显示最后有效交易日，基本面显示财报期和发布日期。
- **历史日期**：行情和财报只使用选定日期当时已经可见的信息。

市场数据会自动刷新，完整的历史记录保持固定，因此重新打开历史研究时不会混入后来才出现的信息。

A 股最新行情、公司新闻和公司公告分别来自新浪财经、东方财富和巨潮资讯，并统一通过 AKShare 接入。日线、估值字段、行业分类和已发布财务数据来自 BaoStock。界面会在相应数据旁展示来源和有效日期。

## 技术组成

StockLLM 使用 React 19 与 TypeScript 构建界面，FastAPI 与 SQLite 提供本地服务，DeepSeek 用于 AI 辅助比较和研究对话，Tauri 2 用于 Windows 桌面应用。

## Windows 桌面版构建

Windows 10/11 x64 桌面版使用 Tauri 2 加载 React，并在随机回环端口启动 PyInstaller 打包的 FastAPI sidecar。构建需要 Python 3.12 或更高版本、Rust MSVC target、Visual Studio C++ Build Tools、Node.js、pnpm 和项目虚拟环境。正式构建前可先运行无产物的前置检查：

```powershell
.\scripts\build-desktop.ps1 -PreflightOnly
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build-desktop.ps1
```

安装包输出到 `packaging/dist/StockLLM_<版本>_x64-setup.exe`。当前安装包未签名，采用当前用户安装；卸载不会删除 `%LOCALAPPDATA%\StockLLM` 中的研究记录、设置和缓存。

### 发布 Windows Release

先在 `src-tauri/tauri.conf.json` 中设置桌面版版本号并提交，然后推送匹配的 `v<版本>` 标签。例如，版本 `0.1.1` 必须使用标签 `v0.1.1`：

```powershell
git tag v0.1.1
git push origin v0.1.1
```

**Build Windows Desktop** workflow 会校验标签与桌面版版本号是否一致、构建安装包、将安装包保留为 workflow artifact，并创建带自动生成发行说明和安装包附件的 GitHub Release。也可以在 GitHub Actions 中手动运行该 workflow 并填写匹配的 Release 标签；此时 Release 和标签会指向运行 workflow 时选择的提交。

## 项目文档

- [架构](docs/architecture.md) | [Architecture](docs/architecture.en.md)
- [界面设计系统](docs/design-system.md) | [Design system](docs/design-system.en.md)
- [贡献指南](CONTRIBUTING.md) | [Contributing](CONTRIBUTING.en.md)

## 参与贡献

欢迎提交 Issue 和 Pull Request。提交改动前请先阅读[贡献指南](CONTRIBUTING.md)。

## 许可证

StockLLM 使用 [MIT License](LICENSE) 开源。
