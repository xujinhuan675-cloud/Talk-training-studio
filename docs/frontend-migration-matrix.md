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
- NewAPI Go 不承载 TalkWise 训练业务逻辑或数据表；旧 Vite 前端仅作为迁移参考和回滚来源。
- 本矩阵中的“已迁移”表示已有 NewAPI 原生路由和可运行闭环，不表示旧前端已经整体退场。

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
| `GrowthPage.tsx` | `/training/growth` | 已迁移（真实成长数据） | 使用受保护的场景进度、训练会话时间线和 competency radar；只计算 completed/ready 的真实评分，明确 pending/failed/not-scored 状态。旧前端硬编码 XP、level、session XP 和解锁规则没有迁移，待后端提供持久化成长契约后再评估。 |
| `TrainingStudioPage.tsx` | `/training/studio`、`/training/live-coach` | 已迁移（四类训练模式） | 文本 live coach、回合制 voice、`cascade` 近实时、`speech_to_speech` 真实时与 video 已接入 NewAPI 原生工作台。语音/视频只在用户明确点击后请求设备权限；所有媒体输入、转写、角色回复、消息、emotion 和回放资源继续绑定同一 TrainingSession/room，由 TalkWise FastAPI 做最终授权。真实麦克风/摄像头、MediaRecorder 编码、STT/TTS 供应商和中断体验留给用户侧浏览器验收。 |
| `SettingsPage.tsx` | `/training/settings` + NewAPI 账号/主题/用量/系统设置 | 已迁移（训练配置权限收口） + 平台承接/待决策 | `/training/settings` 使用 TalkWise 场景模板、评分维度、rubric 默认值和 admin 只读/写入边界；模型、渠道、API key、STT/TTS、Pipecat/runtime 等平台配置由 NewAPI/运行时控制面承接，不复制到训练页。旧 Settings 的 room-scenario CRUD 与 persona relationship/context prompt 不是当前训练配置字段的等价迁移，仍待产品决定迁移独立训练关系模块或批准退场。 |

## 3. 当前 NewAPI 训练路由

- 概览与练习：`/training`、`/training/scenarios`、`/training/studio`、`/training/live-coach`
- Persona：`/training/personas`、`/training/personas/new`、`/training/personas/:personaId`
- 对话与复盘：`/training/conversations`、`/training/sessions`、`/training/sessions/:sessionId`
- 成长与团队：`/training/growth`、`/training/team/competencies`、`/training/team/scenarios`
- 准备与设置：`/training/prep/battle`、`/training/prep/defense`、`/training/settings`

## 4. Persona 代理与授权

NewAPI 仅代理以下受认证路径：

- `/api/talkwise/personas`
- `/api/talkwise/personas/*`
- `POST /api/talkwise/persona-builder/detect-speakers`
- `POST /api/talkwise/persona-builder/build`

Persona 列表、详情和 V2 响应由 TalkWise 后端计算 `can_manage` / `read_only`。系统模板始终只读；团队共享资产对普通成员可读但不可修改；Owner、团队管理员或系统管理员按后端策略管理。增强已有 Persona 时，后端必须先验证 `target_persona_id` 的管理权限，再启动异步构建。

## 5. 后续验收顺序

1. 成长与设置：XP/level/session XP 仍不迁移，除非后端新增持久化成长契约；继续确认旧 room-scenario CRUD 与 persona relationship/context prompt 的产品归属。平台能力继续由 NewAPI 承接。
2. 结果媒体与情绪：情绪趋势和历史视频回放已接入真实持久化消息与 session-bound 代理 URL；只有后端提供可比较的多路径报告/评分时才展示分支评分对比。
3. 浏览器媒体验收：由用户验收回合制/实时语音、TTS 播放、摄像头、MediaRecorder、认证回放、停止收尾和错误反馈；代码验收不替代真实设备验收。
4. 旧 shell 退场：完成回滚方案、旧 URL 策略和最终页面核对后，另行获得人工批准；不在迁移过程中直接删除旧 Vite 文件。

## 5. 第 4 轮审计结论

- Growth 的旧 stakeholder 聚合接口现在要求显式 `StakeholderRoomAccessScope`，并只聚合身份可见 room/evaluation；NewAPI Growth 页不调用未代理的旧 LLM profile 接口。
- NewAPI Growth 页展示真实 competency profile 和最近 TrainingSession 时间线，时间线最多展示最近 6 条；没有把旧前端客户端 XP、等级阈值或解锁规则伪装成服务端数据。
- 旧 stakeholder Growth 聚合仍固定读取最多 500 个 room/evaluation，超过规模时会遗漏较早数据但不会越权；无 owner metadata 的历史 room 依赖 persona/team fallback，可能被保守隐藏，后续应改为仓储层 scope 查询或迁移历史 ownership。
- `/training/settings` 的读权限允许已认证训练用户，写权限与 FastAPI 当前 admin/leader 合同一致；当前 NewAPI 身份桥只映射 admin/staff，因此生产写入实际由管理员承担。
- `GET /scenario-templates` 当前在 NewAPI 代理层受认证，但独立 FastAPI 路由仍可匿名读取全局模板；需要明确它是否是有意公开的目录 metadata。前端 `TrainingScenarioCategory` 也尚未包含后端的 `product_management`，未来启用该类别前必须扩展合同，避免归一化为 `sales`。
- 结果详情读取现有受保护 room messages，过滤 live-guidance 复制消息；情绪图只使用 `sender_type=persona` 且范围为 -5..5 的持久化分数。视频回放只接受同源、session/room 绑定的 canonical 或旧版内部路径，并重写到 `/api/talkwise/training/video-answers/*`。
- 认证视频回放响应设置 `Cache-Control: private, no-store`，防止带相同 session/room URL 的敏感媒体被共享缓存复用。
- 旧 Growth LLM 风格标签/导出卡片、客户端 XP/解锁、旧 room-scenario 与 persona relationship/context prompt 尚未迁移；它们需要新的窄代理/持久化契约或产品退场决定，不能用前端推导补齐。

## 6. 第 5 轮宿主切换与待迁移边界

- 本地默认可见前端已从独立 Vite 切换为 NewAPI web 的 Rsbuild 宿主；Rsbuild 的同源 `/api` 代理指向本地 NewAPI Go，Go 继续只代理 TalkWise 的受限命名空间。`start-dev.cmd -LegacyViteFrontend` 是明确的临时回滚入口，不是新的可见 UI 开发路径。
- NewAPI Rsbuild 启动固定使用 `--strict-port`。端口被占用时脚本会明确失败，而不会让 Rsbuild 漂移到未被后续健康检查和浏览器地址使用的端口。
- `/scenario-templates` 现在在 TalkWise FastAPI 直连路径也要求已认证的训练角色；NewAPI Training Settings 的分类契约已补齐 `product_management`，不会再把后端该分类静默归一成 `sales`。
- `PersonaEditorPage.tsx` 的个体 `user_context` 已由 NewAPI Persona Editor 的 V2 API 承接，不需要重复迁移。
- 旧 room-scenario CRUD 不等同于全局 training scenario config：它会绑定既有 ChatRoom 并在运行时注入 `context_prompt`。旧组织 `context_prompt` 和 directed persona relationship 也属于独立的训练运行时语义。它们应在后端补齐 owner/team scope 和 focused tests 后，作为候选 `/training/team/context` 模块迁移；不得混入平台设置、Persona Editor 或宽泛 conversations 代理。
- 多分支评分对比仍待补齐：当前后端只为服务端选定路径生成一个评分/报告，没有可比较的多分支评分契约。现有 NewAPI 复盘继续展示真实 selected-path、报告、评分和回放，不伪造其他分支的分数。
