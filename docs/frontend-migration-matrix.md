# TalkWise 前端迁移验收矩阵

更新日期：2026-08-01

## 1. 架构边界

长期形态保持两个后端和一个前端宿主：

```text
Browser
  -> NewAPI 原生 React Web
  -> NewAPI 同源受认证代理 /api/talkwise/*
  -> 独立 TalkWise FastAPI
  -> TalkWise 数据库与训练业务
```

- NewAPI 负责账号、团队、角色、平台 Shell、导航、主题、用量、余额、计费、公告、管理控制面和同源代理。
- TalkWise FastAPI 继续负责 Persona、场景、TrainingSession、conversation tree、评分、复盘、成长、实时教练和媒体训练语义，并做最终资源授权。
- NewAPI Go 不承载 TalkWise 训练业务逻辑或业务数据表；只新增独立的平台侧 `training_teams` / `training_team_memberships`，用于训练团队身份投影，且不修改 gateway group、模型访问、额度或计费。
- 本矩阵中的“已迁移”表示已有 NewAPI 原生路由和可运行闭环。旧 Vite 源码、运行、部署与验证入口均已退场；没有可靠持久化或授权契约的旧 UI 推导能力被明确退役，而不是用伪数据补齐。

## 2. 旧页面映射

| 旧页面 | NewAPI 路由或平台能力 | 状态 | 验收结论 / 剩余缺口 |
| --- | --- | --- | --- |
| `PublicLandingPage.tsx` | `/` | 平台承接 | 使用 NewAPI 原公开页结构注入 TalkWise 内容；不再维护独立落地页。 |
| `LoginPage.tsx` | `/sign-in` | 平台承接 | 登录、会话和账号恢复由 NewAPI 负责；不迁移旧登录 UI。 |
| `HomePage.tsx` | `/training` | 已迁移 | NewAPI 原生训练概览已接入。 |
| `ScenarioTrainingPage.tsx` | `/training/scenarios` | 已迁移 | 场景列表、筛选和 TrainingSession 启动已接入。 |
| `BattlePrepPage.tsx` | `/training/prep/battle` | 已迁移 | 创建所有权受控 TrainingSession 与 conversation 后进入原生会话工作区。 |
| `DefensePrepPage.tsx` | `/training/prep/defense` | 已迁移 | Defense session 已绑定 TrainingSession 与 conversation，启动后进入同一工作区。 |
| `PersonaBuilderPage.tsx` | `/training/personas/new` | 已迁移 | 原生材料输入、说话人检测、多 Persona 顺序构建、SSE 进度与错误状态已接入。 |
| `PersonaEditorPage.tsx` | `/training/personas/:personaId` | 已迁移 | 原生列表/查看/创建/编辑/归档、五层画像、证据排除、增强/回滚、权限只读态和训练启动已接入。 |
| `ScenarioConfigPage.tsx` | `/training/settings` | 已迁移 | 训练专属配置由该路由承接；平台模型渠道配置不进入训练设置。 |
| `ScenarioLeaderboardPage.tsx` | `/training/team/scenarios` | 已迁移 | 团队管理员场景排行已接入；旧 `/training/growth/leaderboard` 仅保留重定向。 |
| `ChatPage.tsx` | `/training/conversations` + `/training/studio` | 已迁移（文本与多模态关键闭环） | 文本会话已有 TrainingSession/message tree、文本流、编辑、重试、selected path、受认证分支切换、URL 路径恢复、训练安全 fork、真实场景上下文、selected-path 指导和报告分析。训练工作台已接入回合制语音的录音/STT/消息写入与 SSE TTS 播放，以及视频采集、上传、受认证回放和 `[video-answer]` 消息持久化。房间时间线与结果页只展示后端持久化的 persona `emotion_score` / `emotion_label`；不推测摄像头分析或复制旧 UI。 |
| `TrainingHistoryPage.tsx` | `/training/sessions` | 已迁移（高级筛选完成） | 真实会话列表、详情跳转、报告状态和按 `training_session_id` 关联的真实进度评分已接入；全文、活动时间、模式、来源和场景筛选均由 FastAPI 在 ACL 约束下执行，筛选状态保存在 URL，列表按最近活动时间服务端分页。搜索只覆盖白名单可见字段，不扫描任意 metadata。 |
| `TrainingResultPage.tsx` | `/training/sessions/:sessionId` | 已迁移（报告与媒体复盘闭环） | 已区分 session/report/progress 来源，读取 message-tree 报告并展示 `with_text`、`id_only`、`reference_only` 三种 selected-path 状态；真实展示评分维度、阻力、有效论点、建议、证据复盘、替代表达、改写、微练习、高信号时刻和消息锚点，并只对可证明的 selected-path 引用计算证据覆盖。现在还读取受 ACL 保护的房间持久化消息，提供对话回放、真实 persona 情绪趋势和 session/room 绑定的视频回放；无数据时显示空状态，不推测趋势。完整多分支评分对比仍待补齐。 |
| `GrowthPage.tsx` | `/training/growth` + `/training/growth/profile` | 已迁移（真实成长、TP 与沟通名片） | 使用受保护的场景进度、训练会话时间线和 competency radar；完成 TrainingSession 会幂等写入持久化 Training Points 账本，当前为每次完成 `100 TP`，按服务端阈值计算等级与进度。沟通名片支持真实数据预览、PNG、系统分享，并可选附带 NewAPI 原生账号邀请链接/二维码；默认关闭，不生成公开训练资源 URL。样本不足、权限失败或上游失败均显式反馈，不伪造数据。 |
| `TrainingStudioPage.tsx` | `/training/studio`、`/training/live-coach` | 已迁移（四类训练模式） | 文本 live coach、回合制 voice、`cascade` 近实时、`speech_to_speech` 真实时与 video 已接入 NewAPI 原生工作台。语音/视频只在用户明确点击后请求设备权限；所有媒体输入、转写、角色回复、消息、emotion 和回放资源继续绑定同一 TrainingSession/room，由 TalkWise FastAPI 做最终授权。真实麦克风/摄像头、MediaRecorder 编码、STT/TTS 供应商和中断体验留给用户侧浏览器验收。 |
| `SettingsPage.tsx` | `/training/settings` + NewAPI 账号/主题/用量/系统设置 | 已迁移 + 平台承接 | `/training/settings` 使用 TalkWise 场景模板、评分维度、rubric 默认值和 admin 只读/写入边界；模型、渠道、API key、STT/TTS、Pipecat/runtime 等平台配置由 NewAPI/运行时控制面承接。旧 room-scenario CRUD 与 persona relationship/context prompt UI 被明确退役：其 legacy backend 语义不等同于当前训练配置，且缺少长期 owner/team 管理契约，不混入新设置页。 |

## 3. 当前 NewAPI 训练路由

- 概览与练习：`/training`、`/training/scenarios`、`/training/studio`、`/training/live-coach`
- Persona：`/training/personas`、`/training/personas/new`、`/training/personas/:personaId`
- 对话与复盘：`/training/conversations`、`/training/sessions`、`/training/sessions/:sessionId`
- 成长与团队：`/training/growth`、`/training/growth/profile`、`/training/team/competencies`、`/training/team/scenarios`、`/training/team/members`（admin）
- 准备与设置：`/training/prep/battle`、`/training/prep/defense`、`/training/settings`

## 4. Persona 代理与授权

NewAPI 仅代理以下受认证路径：

- `/api/talkwise/personas`
- `/api/talkwise/personas/*`
- `POST /api/talkwise/persona-builder/detect-speakers`
- `POST /api/talkwise/persona-builder/build`

Persona 列表、详情和 V2 响应由 TalkWise 后端计算 `can_manage` / `read_only`。系统模板始终只读；团队共享资产对普通成员可读但不可修改；Owner、团队管理员或系统管理员按后端策略管理。增强已有 Persona 时，后端必须先验证 `target_persona_id` 的管理权限，再启动异步构建。

## 5. 后续验收顺序

1. 浏览器媒体验收：由用户验收回合制/实时语音、TTS 播放、摄像头、MediaRecorder、认证回放、停止收尾和错误反馈；代码验收不替代真实设备验收。
2. 产品增强：只有后端提供可比较的多路径报告/评分时才展示分支评分对比；这不是旧前端宿主退场的阻塞项。
3. 运行观测：验证生产 NewAPI 注入 `TALKWISE_TRAINING_UPSTREAM_URL`，并观察 TP 首次回填、团队 membership 身份投影和旧数据 owner metadata。
4. 前端宿主迁移已完成：旧 `frontend/` 源码、运行、部署和验证依赖已移除，回滚使用前后端版本与数据库备份，不恢复旧 Vite shell。

## 6. 第 4 轮审计结论

- Growth 的旧 stakeholder 聚合接口要求显式 `StakeholderRoomAccessScope`，并只聚合身份可见 room/evaluation；第 6 轮已将其中窄范围、受认证的 LLM 沟通名片生成接入 NewAPI Growth 子路由。
- NewAPI Growth 页展示真实 competency profile、最近 TrainingSession 时间线和服务端 Training Points；旧客户端 XP/解锁规则已由持久化 TP/等级合同替代，不再由浏览器推导。
- 旧 stakeholder Growth 聚合仍固定读取最多 500 个 room/evaluation，超过规模时会遗漏较早数据但不会越权；无 owner metadata 的历史 room 依赖 persona/team fallback，可能被保守隐藏，后续应改为仓储层 scope 查询或迁移历史 ownership。
- `/training/settings` 的读权限允许已认证训练用户，全局语音和场景配置写入仅允许产品管理员。团队范围资源管理不使用第三种 `system_role`，而由 NewAPI 身份桥显式传递的 `team_role=owner/admin` 决定。
- `GET /scenario-templates` 当前在 NewAPI 代理层受认证，但独立 FastAPI 路由仍可匿名读取全局模板；需要明确它是否是有意公开的目录 metadata。前端 `TrainingScenarioCategory` 也尚未包含后端的 `product_management`，未来启用该类别前必须扩展合同，避免归一化为 `sales`。
- 结果详情读取现有受保护 room messages，过滤 live-guidance 复制消息；情绪图只使用 `sender_type=persona` 且范围为 -5..5 的持久化分数。视频回放只接受同源、session/room 绑定的 canonical 或旧版内部路径，并重写到 `/api/talkwise/training/video-answers/*`。
- 认证视频回放响应设置 `Cache-Control: private, no-store`，防止带相同 session/room URL 的敏感媒体被共享缓存复用。
- 客户端 XP/解锁已由持久化 TP/等级替代。旧 room-scenario 与 persona relationship/context prompt 的可见 UI 已批准退役；legacy backend 能力保留不等于可绕开 owner/team scope 重新暴露。

## 7. 第 5 轮宿主切换与待迁移边界

- 本地可见前端已固定为 NewAPI web 的 Rsbuild 宿主；Rsbuild 的同源 `/api` 代理指向本地 NewAPI Go，Go 继续只代理 TalkWise 的受限命名空间。旧 Vite 目录已经移除，`start-dev.cmd` 不再提供旧前端入口。
- NewAPI Rsbuild 启动固定使用 `--strict-port`。端口被占用时脚本会明确失败，而不会让 Rsbuild 漂移到未被后续健康检查和浏览器地址使用的端口。
- `/scenario-templates` 现在在 TalkWise FastAPI 直连路径也要求已认证的训练角色；NewAPI Training Settings 的分类契约已补齐 `product_management`，不会再把后端该分类静默归一成 `sales`。
- `PersonaEditorPage.tsx` 的个体 `user_context` 已由 NewAPI Persona Editor 的 V2 API 承接，不需要重复迁移。
- 旧 room-scenario CRUD 不等同于全局 training scenario config；旧组织 `context_prompt` 和 directed persona relationship 也属于独立的 legacy 运行时语义。本轮批准其旧 UI 退役；未来若有新产品需求，必须在补齐 owner/team scope 和 focused tests 后作为新的 `/training/team/context` 能力设计，不视为恢复旧页面。
- 多分支评分对比仍待补齐：当前后端只为服务端选定路径生成一个评分/报告，没有可比较的多分支评分契约。现有 NewAPI 复盘继续展示真实 selected-path、报告、评分和回放，不伪造其他分支的分数。

## 8. 第 6 轮沟通名片与旧前端退场

- `/training/growth/profile` 是 NewAPI 原生训练子路由；界面使用 NewAPI Card、Alert、Empty、Progress、Button 和多语言机制，不复制旧 `GrowthPage` 样式。
- NewAPI Go 仅新增固定映射 `POST /api/talkwise/growth/profile-card` -> TalkWise FastAPI `POST /api/v1/stakeholder/growth/card`；身份桥和 FastAPI 仍负责最终资源授权，成长聚合与 LLM 生成逻辑没有进入 Go。
- 分享仍以本地 PNG 与系统分享为基础；用户可在生成名片时选择附带 NewAPI 原生账号邀请链接/二维码。该开关默认关闭，邀请链接只用于账号注册，不授予训练资源权限，也不等同于公开训练 URL。
- `LegacyViteFrontend`、旧 Vite 源码、启动分支、代理健康检查、部署产物和旧前端测试/构建均已删除。历史实现通过 Git 历史和 `docs/archive/server-deployment-runbook-legacy-vite.md` 追溯。

## 9. 最终收口结论

- **已迁移**：所有旧业务页面在上表中都有 NewAPI 原生路由，包含 Persona、会话树、历史、复盘、多模态训练、成长、沟通名片、训练设置和团队分析。
- **平台承接**：公开页、登录、账号、主题、通知、余额、用量、API Keys、计费和系统管理不重复实现。
- **明确退役**：独立 Vite shell、旧客户端 XP/解锁推导、旧 room-scenario/persona relationship 设置 UI，以及缺少服务端事实合同的视觉占位。
- **持续增强而非迁移缺口**：真实设备浏览器验收、完整多分支评分比较、更多 Pipecat/LibreChat 能力和 legacy owner metadata 数据治理。
- **权限角色收口**：本地 `X-Mock-User: leader` 和不可达的 `system_role=leader` 已移除；未知命名 mock 返回 401，真实团队管理权限只来自 `team_role=owner/admin`，不改写 NewAPI gateway group、配额或计费。
