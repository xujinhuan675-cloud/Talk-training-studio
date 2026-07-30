# TalkWise x NewAPI UI Platform Fusion Roadmap

## Decision

2026-07-30 确认：TalkWise 的目标架构是成为 NewAPI web 内的一等训练产品模块。当前独立 Vite 前端只保留为尚未迁移业务逻辑的参考实现和回滚来源，不再承担新的可见 UI 或迁移期页面宿主。

目标判断：

- NewAPI 承接账号、登录、用户菜单、余额/用量、API Keys、公告、计费、系统设置、主题、导航壳和 admin console。
- TalkWise 保留训练产品语义：场景、persona/stakeholder、训练 session、实时提示、复盘、评分、成长报告和训练历史。
- TalkWise 前台不显示 NewAPI 品牌名。可见 UI 使用 TalkWise 自己的信息架构或中性功能名；NewAPI 只作为能力来源、源码参考和后台控制面。
- NewAPI web 是唯一长期前端宿主；TalkWise 在其 authenticated layout 和 sidebar 中注册 `/training` 模块，共享 session、permissions、theme、notifications、billing/usage 和 admin console。
- 新增或改造 UI 直接进入 NewAPI 的 Rsbuild + TanStack Router 宿主；Vite 中不再复制 NewAPI 页面、组件、全局动画或交互。
- 项目 owner 已说明 NewAPI 源码复用有授权，AGPL 不作为阻塞项。实现应直接修改 NewAPI 原组件、原路由和原模块注册点，并保持适配范围清楚。

这项决策解决的是平台归属和长期维护边界，不要求把渠道、令牌、用量等网关后台页面机械复制成训练页面。但只要 NewAPI 已有与 TalkWise 对应的页面结构、组件或全局 UI，实现就应优先原样复用；实时对话、语音和视频等 NewAPI 缺失的训练工作区才允许基于同一套 host primitives 新增组合。

## Target Architecture

1. NewAPI host
   - 拥有登录后 shell、顶栏、侧栏、全局搜索、主题、语言、通知、账号、用量、计费和管理员入口。
   - 通过 TanStack Router route tree 和 sidebar metadata 暴露 TalkWise 训练模块。
2. TalkWise training module
   - 拥有训练首页、场景、训练会话、复盘、成长和训练设置页面。
   - 通过 host adapter 获取当前用户、团队、角色、余额、能力开关和 API base，不复制 NewAPI auth/store。
3. TalkWise backend
   - 继续拥有 TrainingCore、session、scenario、persona、dispatcher、evaluation、growth、live guidance、媒体和训练数据访问边界。
   - 通过稳定 HTTP/WebSocket/SSE contract 被 NewAPI web 中的训练模块调用，不依赖 NewAPI 内部数据库表。
4. Mature runtimes
   - 文本 runtime 继续向 LibreChat-style conversation runtime 收敛。
   - 语音/多模态继续保留经济型 near-realtime 与 Pipecat true realtime 两条 adapter，并汇入同一训练语义。

## UI Source Reuse Contract

目标不是“参考 NewAPI 风格后重新设计 TalkWise”，而是把 NewAPI 已有实现作为目标宿主中的 UI 事实源。复用按以下优先级执行：

1. 全局组件直接共享
   - authenticated layout、header、sidebar、profile menu、notification、theme、Button、Badge、Tabs/Segmented、Dialog、Popover、Table、Card、EmptyState、Toast 等由 NewAPI host 统一提供。
   - TalkWise 模块直接消费同一组件或其薄 adapter，不创建复制后独立演化的 fork。
2. 已有页面或区块原样复用
   - NewAPI 已有对应页面、hero、page header、toolbar、列表、表格、弹层或状态区块时，保留其组件结构、排版、字号、字重、颜色、行高、间距、宽度、断点、响应式换行和交互状态。
   - TalkWise 只替换产品文案、数据、图标语义、路由、权限和业务动作；不因换成训练内容就重新做一套视觉。
3. 训练专属界面新增组合
   - 只有 NewAPI 不存在等价实现的场景配置、实时对话、语音/视频训练、live guidance、训练复盘等产品结构才新增 UI。
   - 新增部分仍使用 NewAPI host 的 primitives、tokens、密度、状态反馈和可访问性规则；沉浸式工作区可以隐藏部分 shell，但不建立另一套设计系统。

落地页标题是基准示例：直接复用 NewAPI hero 标题的组件和样式，字号、颜色、字重、行高、最大宽度与响应式规则保持不变，只把标题、眉题、说明、CTA 和预览内容替换为 TalkWise 语义。新文案在原规则下自然换行是允许的；若长度破坏原版节奏，优先压缩文案，不通过缩小字号、改色或局部 CSS 覆盖来迁就文案。

硬约束：可见 UI、全局动画、主题行为、响应式规则和交互状态只能由 NewAPI 原组件拥有。迁移中间态也不允许在 Vite 或其他宿主中复制对应实现；需要替换 TalkWise 内容时，为原组件增加数据 props、render slot、薄 adapter 或模块配置，默认值必须保持 NewAPI 原行为不变。

非目标：

- 不把 TalkWise 训练业务表迁入 NewAPI 网关核心表。
- 不把训练页改成渠道、令牌和用量后台的视觉复制品。
- 不使用 iframe 作为正式模块集成方案。
- 不长期维护两套 shell、登录态、主题、公告和平台导航。

## Landed Slice

2026-07-29 第一批已落地：

- `frontend/src/styles/tokens.css` 增加 `--shell-*` token，作为 NewAPI-like shell 的主题边界。
- `frontend/src/components/layout/Layout.tsx` / `Layout.css` 标记平台 shell，并统一主区域背景、滚动和移动端底栏高度。

以上 Vite 侧实现现在只作为迁移参考和回滚来源，不再继续扩展可见 UI。

2026-07-30 NewAPI 原生纵向切片已落地：

- `outside-project/new-api-main/web/src/features/home` 的原 Hero、Stats、Features、HowItWorks、CTA 和终端预览组件通过内容 props / render slot 接收 TalkWise 文案与数据，默认值仍保持 NewAPI 原行为。
- `outside-project/new-api-main/web/src/features/training` 和 `_authenticated/training` 使用 NewAPI 原 `SectionPageLayout`、Tabs、Card、EmptyState、route tree 与 sidebar 配置注册 `/training` 模块。
- 全局主题、tab 下划线、自动轮播、Counter、滚动入场动画和 responsive 行为仍由 NewAPI 原组件拥有；TalkWise 没有复制对应实现或新增私有 CSS。
- 当前 `/training` 只完成可验证的 overview 与空状态边界，后续场景、会话、复盘和成长页按业务簇迁移，旧 Vite 页面只提供业务语义参考。
- `TopBar.tsx` / `TopBar.css` 改成平台顶栏：品牌、侧栏收起按钮、团队上下文、命令搜索、余额入口、公告入口、主题/语言和用户菜单；前台不显示 NewAPI 字样。
- `NavRail.tsx` / `NavRail.css` 改成平台侧栏：分组导航、active accent、折叠状态和角色过滤保留；侧栏内部不再重复渲染 TalkWise 品牌卡片。
- `BottomTabBar.tsx` / `BottomTabBar.css` 移除凸起主按钮，移动端改成更克制的平台 tabbar。
- `UserMenu.tsx` / `UserMenu.css` 展示账号摘要、团队、余额、用量、请求数、计划和账号控制台/API Keys/用量入口；菜单不显示 NewAPI 品牌名。
- `frontend/src/components/layout/navigation.tsx` 保留单一导航 schema，移动端不再使用 elevated tab。

## Migration Route

### Phase 0: Product Surface Convergence

目标：先消除独立 AI demo 的产品表面，同时停止在 Vite 前端制造新的可见 UI 和临时基础设施。

- 直接扩展 `outside-project/new-api-main/web/src/components/layout/components/authenticated-layout.tsx`、`app-header.tsx`、`app-sidebar.tsx`、`profile-dropdown.tsx` 及其模块注册点，不提取或复制外观与交互。
- 登录后的第一屏直接是训练工作台，不使用 hero、能力宣讲、模拟产品截图或 CTA 作为应用入口。公开获客页如需保留，应与登录后产品宿主分离。
- Home / Growth / TrainingHistory 先统一 page header、toolbar、table/list、empty state 和信息密度；减少等权统计卡、装饰性模块和大面积空白。
- 实时训练、Chat 和 voice 页面保留沉浸模式，不强制套用网关 dashboard 卡片布局。
- 统一 Button、Badge、Tabs/Segmented、Dialog、Popover、Table、Card、EmptyState、Toast 的 host-compatible 组件契约。

### Phase 1: Host Contract

目标：在搬页面前冻结 NewAPI host 与 TalkWise module 的边界。

- 定义 `TrainingHostContext` 或等价 adapter：user、team、role、quota、feature flags、locale、theme、API base、navigation 和 telemetry。
- 定义 route migration map、API proxy/base URL、cookie/session topology、role mapping、gateway usage attribution 和 error boundary。
- 保持 TalkWise 后端 API 和训练语义稳定，禁止前端直接读取 NewAPI 数据库或复制 NewAPI auth store。
- 当前 React Router 只维护尚未迁移的旧页面；新增 route metadata 直接注册到 NewAPI TanStack Router 和 sidebar schema。
- 建立 host contract 测试，保证 NewAPI 原生模块与 TalkWise 后端使用稳定服务契约；不再以双宿主视觉实现为目标。

### Phase 2: Low-Risk Module Migration

目标：先把读取型、低实时风险页面迁进 NewAPI web，验证宿主合同。

1. `/workspace` -> `/training`
2. `/growth` -> `/training/growth`
3. `/growth/leaderboard` -> `/training/team`
4. `/review/sessions` -> `/training/sessions`
5. `/review/sessions/:sessionId` -> `/training/sessions/$sessionId`

验收重点：NewAPI 登录态、团队 scope、权限过滤、主题、移动端侧栏、深链、返回路径和 branch-aware review 不发生语义变化。

### Phase 3: Core Workflow Migration

目标：迁移会写状态、依赖实时链路或拥有复杂表单的核心页面。

1. `/practice/scenarios` -> `/training/scenarios`
2. `/practice/custom` -> `/training/studio`
3. `/conversations/:roomId` -> `/training/conversations/$roomId`
4. `/config/*` -> `/training/settings/*`
5. realtime voice/live coach -> `/training/live/$sessionId` 或等价沉浸式路由

TrainingStudio、Chat 和 realtime voice 最后迁移，因为它们同时依赖 provider readiness、WebSocket/SSE、音频权限、transcript persistence 和训练状态恢复。

### Phase 4: Independent Shell Retirement

目标：完成单一宿主收口。

- NewAPI web 成为 TalkWise 唯一登录后入口。
- 停止独立 TalkWise shell、重复 auth context、主题、公告、账号菜单和导航的功能开发。
- 对旧 URL 提供可观测的永久或应用级重定向，保留 session/result 深链兼容。
- 独立 Vite host 仅在明确回滚窗口内保留；满足测试矩阵和生产观察期后退出主部署。
- 删除动作另行审批；本路线只定义退场条件，不直接删除旧前端代码。

## Target Route Map

| Product capability | Target NewAPI route | Sidebar group |
| --- | --- | --- |
| 训练概览与下一步 | `/training` | 训练 |
| 场景库与快速开始 | `/training/scenarios` | 训练 |
| 自定义训练工作台 | `/training/studio` | 训练 |
| 文本训练对话 | `/training/conversations/$roomId` | 训练 |
| 实时语音/多模态 | `/training/live/$sessionId` | 沉浸式子路由 |
| 训练记录与复盘 | `/training/sessions`、`/training/sessions/$sessionId` | 复盘 |
| 成长与团队表现 | `/training/growth`、`/training/team` | 追踪 |
| 场景/persona/provider 配置 | `/training/settings/*` | 管理 |

## Migration Gates

这些是迁移实施门槛，不再是是否迁移的决策门槛：

- route redirect/deep-link 兼容表完成。
- NewAPI host context 与 TalkWise API adapter 有契约测试。
- user/team/role scope 和 admin-only 页面有边界测试。
- gateway 用量能按 app/user/team/training session 归因且不记录训练隐私正文。
- realtime 页面有真实浏览器的音频、权限、turn/interruption、恢复和错误验收。
- 每个页面簇都有回滚开关或可逆路由切换。
- 旧 shell 的退场条件、观察期和恢复路径明确。

## Source Map

NewAPI 参考源码：

- `outside-project/new-api-main/web/src/components/layout/components/authenticated-layout.tsx`
- `outside-project/new-api-main/web/src/components/layout/components/app-header.tsx`
- `outside-project/new-api-main/web/src/components/layout/components/app-sidebar.tsx`
- `outside-project/new-api-main/web/src/components/profile-dropdown.tsx`
- `outside-project/new-api-main/web/src/components/notification-popover.tsx`
- `outside-project/new-api-main/web/src/features/wallet/components/wallet-stats-card.tsx`
- `outside-project/new-api-main/web/src/styles/theme.css`
- `outside-project/new-api-main/web/src/styles/theme-presets.css`
- `outside-project/new-api-main/controller/talkwise.go`
- `outside-project/new-api-main/web/src/features/auth/lib/talkwise-handoff.ts`

TalkWise 当前落地入口：

- `frontend/src/components/layout/Layout.tsx`
- `frontend/src/components/layout/TopBar.tsx`
- `frontend/src/components/layout/NavRail.tsx`
- `frontend/src/components/layout/BottomTabBar.tsx`
- `frontend/src/components/layout/UserMenu.tsx`
- `frontend/src/components/layout/navigation.tsx`
- `frontend/src/styles/tokens.css`
- `frontend/src/services/auth.ts`
