# StockLLM 界面设计系统

[English](design-system.en.md) · [简体中文](design-system.md)

StockLLM 是桌面优先的个人投资研究工具。界面强调稳定、紧凑、可扫描和可追溯，不模拟专业量化终端。

## 组件基座

- 所有基础界面组件来自 [shadcn/ui](https://ui.shadcn.com/) 官方 registry。
- 当前 preset 固定为 `base-nova`，底层 primitives 使用 Base UI，主题使用官方 `neutral` 默认值。
- Sidebar、Button、ToggleGroup、Select、Input、Card、Table、Tabs、Badge、Alert、Empty、ScrollArea、Tooltip、Separator、Skeleton 和 Spinner 不得在项目内重新实现。
- `frontend/src/components/ui/` 只存放 shadcn CLI 生成的官方组件文件，不手动修改其视觉样式。
- TanStack Query/Table 只负责数据请求和表格模型；可见结构使用 shadcn Table。
- Lightweight Charts 负责行情图，Lucide 使用 shadcn 配置的官方图标库。
- 业务组件只能组合数据和页面流程，例如候选表、研究对话和行情图；不得形成第二套基础组件库。
- 新需求先通过 shadcn CLI 查询和添加官方组件，不自行构建替代品。

## 官方默认值

- 字体使用 shadcn preset 默认 Geist。
- 圆角使用 `radius: default`，不得在业务 CSS 或业务 `className` 中覆盖。
- 颜色使用 neutral 语义 token，不维护项目自定义色板。
- 边框、阴影、悬停、选中、按压、焦点和禁用状态全部使用组件内置值。
- 当前应用只启用深色模式，但不改写 shadcn 的暗色 token。
- 组件字号、行高、控件高度和内部 padding 使用官方默认值。

## 页面结构

- Sidebar 负责桌面侧栏和 `collapsible="icon"` 收回行为，收回后保留官方图标栏。
- Header 与页面主体使用一致的水平间距，主体不设置独立最大宽度。
- 开始选股使用固定参数栏与可滚动结果区；较矮窗口中参数内容滚动，主操作固定在参数栏底部。
- 历史研究、自选股和候选列表统一使用 `Card + Table`。
- 个股摘要左侧证券信息占主要空间，右侧显示搜索和来源。
- 页面不嵌套装饰性卡片；Card 只用于独立工具、表格、结果和设置。

## 交互

- 所有交互状态使用 shadcn 内置行为，不使用 CSS 模拟按钮按压、滑块、选择器箭头或焦点环。
- 纯图标命令使用 Button 的 `size="icon"`，并提供 Tooltip 与 `aria-label`。
- Button 内图标使用 `data-icon`；不在业务代码中设置图标尺寸。
- 2–5 个单选档位使用 ToggleGroup，预定义长列表使用 Select，页面视图使用 Tabs。
- 表单使用 `FieldGroup + Field`，输入内操作使用 InputGroup。
- SelectItem 必须放在 SelectGroup 内，TabsTrigger 必须放在 TabsList 内。

## CSS 边界

### 空间受限与内容溢出

- 所有 flex/grid 内容列必须允许收缩，业务容器使用 `min-w-0`，页面不得产生全局横向滚动。
- 导航、状态、数字和按钮文字保持单行；可变名称使用 `truncate`，并通过 `title` 或 Tooltip 保留完整内容。
- 描述、来源、证据、错误、新闻、AI 回复和工具轨迹允许换行；连续 URL、证据 ID 等使用安全断词。
- CardHeader 的 CardAction 最多占标题容器一半宽度，不能把标题或描述挤出卡片。
- Table 保持可读的最小列宽，由 shadcn Table 容器横向滚动；长理由单元格可换行，不压缩操作列。
- TabsList 保持单行，空间不足时在列表内部横向滚动，不换行成不规则的多层标签。
- 工具栏和 CardFooter 在操作较多时允许换行；图标按钮、状态 Badge 和固定尺寸控件不得收缩变形。
- 多列业务布局按桌面窗口宽度降为单列；内容降级只改变排版，不隐藏证据或关键操作。

`frontend/src/styles.css` 在 shadcn 初始化生成的 token 之外，只负责：

- 应用与滚动区域的稳定尺寸；
- 页面级 grid、列宽和间距；
- 行情图容器；
- 桌面宽度下的布局降级。

业务 CSS 不得定义或覆盖按钮、输入框、选择器、ToggleGroup、Tabs、Badge、Card、Table、Sidebar 或导航的颜色、字体、圆角、阴影、边框与交互状态。

## 验收

- 页面不得产生全局横向溢出。
- 侧栏收回后保留图标并能恢复展开。
- Header 与主体保持一致的左右边界。
- `1280×720` 下开始选股按钮完整可见，参数内容可滚动。
- 所有基础控件均能追溯到 shadcn 官方生成文件。
- 业务源码不得依赖 Mantine，也不得存在自建基础控件。
- 浏览器控制台无应用警告或错误，生产构建与 TypeScript 检查通过。
