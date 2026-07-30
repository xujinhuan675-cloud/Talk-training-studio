# TalkWise x NewAPI UI Platform Fusion Roadmap

## Decision

2026-07-30 确认：TalkWise 的目标架构是成为 NewAPI web 内的一等训练产品模块。当前独立 Vite 前端只承担迁移期宿主，不再被视为长期并行产品。

目标判断：

- NewAPI 承接账号、登录、用户菜单、余额/用量、API Keys、公告、计费、系统设置、主题、导航壳和 admin console。
- TalkWise 保留训练产品语义：场景、persona/stakeholder、训练 session、实时提示、复盘、评分、成长报告和训练历史。
- TalkWise 前台不显示 NewAPI 品牌名。可见 UI 使用 TalkWise 自己的信息架构或中性功能名；NewAPI 只作为能力来源、源码参考和后台控制面。
- NewAPI web 是唯一长期前端宿主；TalkWise 在其 authenticated layout 和 sidebar 中注册 `/training` 模块，共享 session、permissions、theme、notifications、billing/usage 和 admin console。
- 迁移期保留 Vite + React Router，不为了单轮 shell 调整一次性迁到 Rsbuild 或 TanStack Router；所有新增平台适配都应能服务最终 host migration。
- 项目 owner 已说明 NewAPI 源码复用有授权，AGPL 不作为阻塞项。复制源码时仍需记录来源、范围和适配理由。

这项决策解决的是平台归属和长期维护边界，不要求把网关后台视觉机械复制到每个训练页面。实时对话、语音和视频训练仍应保持沉浸式工作区，只共享平台身份、导航、状态和基础组件。

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

非目标：

- 不把 TalkWise 训练业务表迁入 NewAPI 网关核心表。
- 不把训练页改成渠道、令牌和用量后台的视觉复制品。
- 不使用 iframe 作为正式模块集成方案。
- 不长期维护两套 shell、登录态、主题、公告和平台导航。

## Landed Slice

2026-07-29 第一批已落地：

- `frontend/src/styles/tokens.css` 增加 `--shell-*` token，作为 NewAPI-like shell 的主题边界。
- `frontend/src/components/layout/Layout.tsx` / `Layout.css` 标记平台 shell，并统一主区域背景、滚动和移动端底栏高度。
- `TopBar.tsx` / `TopBar.css` 改成平台顶栏：品牌、侧栏收起按钮、团队上下文、命令搜索、余额入口、公告入口、主题/语言和用户菜单；前台不显示 NewAPI 字样。
- `NavRail.tsx` / `NavRail.css` 改成平台侧栏：分组导航、active accent、折叠状态和角色过滤保留；侧栏内部不再重复渲染 TalkWise 品牌卡片。
- `BottomTabBar.tsx` / `BottomTabBar.css` 移除凸起主按钮，移动端改成更克制的平台 tabbar。
- `UserMenu.tsx` / `UserMenu.css` 展示账号摘要、团队、余额、用量、请求数、计划和账号控制台/API Keys/用量入口；菜单不显示 NewAPI 品牌名。
- `frontend/src/components/layout/navigation.tsx` 保留单一导航 schema，移动端不再使用 elevated tab。

## Migration Route

### Phase 0: Product Surface Convergence

目标：先消除独立 AI demo 的产品表面，同时避免制造只能留在 Vite 前端的临时基础设施。

- 继续从 `outside-project/new-api-main/web/src/components/layout/components/authenticated-layout.tsx`、`app-header.tsx`、`app-sidebar.tsx`、`profile-dropdown.tsx` 提取外观和交互。
- 登录后的第一屏直接是训练工作台，不使用 hero、能力宣讲、模拟产品截图或 CTA 作为应用入口。公开获客页如需保留，应与登录后产品宿主分离。
- Home / Growth / TrainingHistory 先统一 page header、toolbar、table/list、empty state 和信息密度；减少等权统计卡、装饰性模块和大面积空白。
- 实时训练、Chat 和 voice 页面保留沉浸模式，不强制套用网关 dashboard 卡片布局。
- 统一 Button、Badge、Tabs/Segmented、Dialog、Popover、Table、Card、EmptyState、Toast 的 host-compatible 组件契约。

### Phase 1: Host Contract

目标：在搬页面前冻结 NewAPI host 与 TalkWise module 的边界。

- 定义 `TrainingHostContext` 或等价 adapter：user、team、role、quota、feature flags、locale、theme、API base、navigation 和 telemetry。
- 定义 route migration map、API proxy/base URL、cookie/session topology、role mapping、gateway usage attribution 和 error boundary。
- 保持 TalkWise 后端 API 和训练语义稳定，禁止前端直接读取 NewAPI 数据库或复制 NewAPI auth store。
- 当前 React Router `<Outlet />` 继续运行，但新增 route metadata 应能映射到 NewAPI TanStack Router 和 sidebar schema。
- 建立双宿主测试：同一训练页面逻辑在迁移期 Vite host 和目标 NewAPI host 下使用相同服务契约。

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
