# TalkWise x NewAPI UI Platform Fusion Roadmap

## Decision

TalkWise 的短中期 UI 路线不是普通换肤，而是把 TalkWise 训练产品放进 NewAPI 风格的平台控制台中。

默认判断：

- NewAPI 承接账号、登录、用户菜单、余额/用量、API Keys、公告、计费、系统设置、主题、导航壳和 admin console。
- TalkWise 保留训练产品语义：场景、persona/stakeholder、训练 session、实时提示、复盘、评分、成长报告和训练历史。
- TalkWise 前台不显示 NewAPI 品牌名。可见 UI 使用 TalkWise 自己的信息架构或中性功能名；NewAPI 只作为能力来源、源码参考和后台控制面。
- 短中期保留 Vite + React Router，不为了 shell 迁移到 Rsbuild 或 TanStack Router。
- 项目 owner 已说明 NewAPI 源码复用有授权，AGPL 不作为阻塞项。复制源码时仍需记录来源、范围和适配理由。

## Landed Slice

2026-07-29 第一批已落地：

- `frontend/src/styles/tokens.css` 增加 `--shell-*` token，作为 NewAPI-like shell 的主题边界。
- `frontend/src/components/layout/Layout.tsx` / `Layout.css` 标记平台 shell，并统一主区域背景、滚动和移动端底栏高度。
- `TopBar.tsx` / `TopBar.css` 改成平台顶栏：品牌、侧栏收起按钮、团队上下文、命令搜索、余额入口、公告入口、主题/语言和用户菜单；前台不显示 NewAPI 字样。
- `NavRail.tsx` / `NavRail.css` 改成平台侧栏：分组导航、active accent、折叠状态和角色过滤保留；侧栏内部不再重复渲染 TalkWise 品牌卡片。
- `BottomTabBar.tsx` / `BottomTabBar.css` 移除凸起主按钮，移动端改成更克制的平台 tabbar。
- `UserMenu.tsx` / `UserMenu.css` 展示账号摘要、团队、余额、用量、请求数、计划和账号控制台/API Keys/用量入口；菜单不显示 NewAPI 品牌名。
- `frontend/src/components/layout/navigation.tsx` 保留单一导航 schema，移动端不再使用 elevated tab。

## Short To Mid Term Route

### Phase 1: Shell Foundation

目标：全局导航先稳定变成 NewAPI 平台壳。

- 继续从 `outside-project/new-api-main/web/src/components/layout/components/authenticated-layout.tsx`、`app-header.tsx`、`app-sidebar.tsx`、`profile-dropdown.tsx` 提取外观和交互。
- 保持 React Router `<Outlet />`，不要迁移 routeTree。
- 保持当前 `AuthContext`，只使用 NewAPI bridge 已返回的 session/user/team/quota 字段。
- 对沉浸式训练/聊天补桌面 shell 收敛模式，避免实时训练页被侧栏挤压。

### Phase 2: NewAPI Control Entrances

目标：用户能从 TalkWise 清晰进入账号控制面，但 TalkWise 前台不显示 NewAPI 品牌名。

- 公告入口优先接 NewAPI `/api/notice` 或 `/api/status` 返回的公告字段；未接真实 API 前只保留“控制台”链接。
- 余额/用量入口短期跳转 NewAPI `/usage-logs/common` 和 `/wallet`；可见文案使用“账号控制台”“用量”“钱包”等中性名称，不在 TalkWise 前台露出 NewAPI。
- API Keys、Console、Usage 保持外链或同域子路径，后续再按部署方式改为 reverse proxy 子路径。
- Settings 页面只放 TalkWise 训练配置；NewAPI 系统设置不要短期整页复制进 TalkWise。

### Phase 3: Component Adapter

目标：业务页逐步使用 NewAPI-like 组件，不改变业务状态。

- 优先统一 Button、Badge、Tabs/Segmented、Dialog、Popover、Table、Card、EmptyState、Toast。
- 业务页内部 tabs 保留语义，只改视觉；不要把训练步骤、配置 tab、复盘 tab 改成全局 nav。
- 路由内类似组件同样适用“换壳不换信息架构”：保留 TalkWise 的 URL、tab key、权限、API、表单字段和业务命名，只替换外壳、状态、密度和交互。
- 可复制 NewAPI `notification-popover.tsx`、`wallet-stats-card.tsx`、data-table mobile cards 等局部源码，但必须改成 TalkWise 数据契约。

### Phase 4: Page Reskin Order

按风险顺序推进：

1. Home / Growth / TrainingHistory：信息密度较低，适合先统一 page header、stat cards、table/list。
2. TrainingResult：统一复盘结构和 branch-aware metadata 展示。
3. TrainingStudio / ScenarioConfig：再处理复杂表单、provider readiness、训练参数。
4. Settings / Chat / realtime voice：最后做，因为已有脏改动和实时交互风险高。

## Long Term Route

当下列条件同时出现时，进入 NewAPI module migration 评估：

- TalkWise 需要直接复用 NewAPI billing、announcements、permissions、theme/customization、system settings 和 admin console。
- 训练入口需要成为 NewAPI sidebar/top nav 中的正式模块。
- 需要统一 NewAPI 用户、团队、模型组、余额预检、用量归因和审计日志。

候选模块路径：

- `/training`
- `/training/sessions`
- `/training/review`
- `/training/settings`

长期迁移前必须先产出 route migration、API proxy/base URL、role mapping、gateway usage attribution、test matrix 和 rollback plan。

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
