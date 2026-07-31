# TalkWise 前端迁移验收矩阵

更新日期：2026-07-31

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
| `ChatPage.tsx` | `/training/conversations` | 待补齐（已有入口） | 已有 TrainingSession/message tree、文本流、编辑和重试；仍需验收 selected path、分支切换/fork、上下文、教练提示、分析、情绪以及语音/视频汇流。 |
| `TrainingHistoryPage.tsx` | `/training/sessions` | 待补齐（已有入口） | 已有真实会话列表与详情跳转；仍需补齐旧页有价值的搜索、筛选和来源区分。 |
| `TrainingResultPage.tsx` | `/training/sessions/:sessionId` | 待补齐（已有入口） | 已显示 session/report 基础复盘；详细评分证据、路径对比、情绪曲线和改进计划仍需对齐。 |
| `GrowthPage.tsx` | `/training/growth` | 待补齐（已有入口） | 已有概览、能力雷达和进度；XP、个人名片、时间线等旧能力需按真实后端数据逐项验收。 |
| `TrainingStudioPage.tsx` | `/training/studio`、`/training/live-coach` | 待补齐（已有入口） | 当前模式选择和文本 live coach 已接入；录音、语音输出、视频回答、转写持久化、实时提示与复盘闭环尚未全部接通。 |
| `SettingsPage.tsx` | `/training/settings` + NewAPI 账号/主题/用量/系统设置 | 平台承接 + 待补齐 | 平台设置不重复迁移；仅保留训练专属配置，仍需逐字段核对旧设置的业务归属。 |

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

1. 对话工作区：selected path、branch/fork、上下文、教练提示与分析面板。
2. 结果与历史：session/report/progress 来源、详细证据、路径对比和错误/权限态。
3. 多模态：near-realtime 与 Pipecat 两条链路统一写入 TrainingSession、transcript、guidance 和 review。
4. 成长与设置：只迁移真实训练语义；账号、主题、用量、计费和平台模型渠道继续由 NewAPI 承接。
5. 旧 Vite shell 退场：完成浏览器验收、回滚方案和旧 URL 策略后另行人工批准，不在页面迁移过程中直接删除。
