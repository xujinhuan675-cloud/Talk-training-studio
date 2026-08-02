# TalkWise

TalkWise 是运行在 NewAPI web 内的多模态 AI 沟通训练模块。NewAPI 提供账号、平台 Shell、导航、主题、用量、计费和管理控制面；独立 TalkWise FastAPI 保留训练场景、Persona、TrainingSession、对话树、评分、复盘、成长和实时训练语义。

## 当前架构

```text
Browser
  -> NewAPI 原生 React web（唯一前端宿主）
  -> NewAPI 同源受认证代理 /api/talkwise/*
  -> 独立 TalkWise FastAPI
  -> TalkWise 自己的数据库与 Alembic 迁移
```

关键边界：

- NewAPI Go 只保存平台侧训练团队 membership 并代理受限训练 API，不承载 TalkWise 训练业务表、评分或复盘逻辑。
- 训练团队独立于 NewAPI `User.Group`；成员增删不修改模型访问、额度、余额或计费。
- FastAPI 只信任 NewAPI 验证后的身份桥，并对训练资源做最终授权。
- 旧 `frontend/` Vite 应用已经退役并从当前源码移除；历史实现仍可从 Git 历史和 `docs/archive` 追溯。

## 训练路由

- 概览与练习：`/training`、`/training/scenarios`、`/training/studio`、`/training/live-coach`
- Persona：`/training/personas`、`/training/personas/new`、`/training/personas/:personaId`
- 对话与复盘：`/training/conversations`、`/training/sessions`、`/training/sessions/:sessionId`
- 成长：`/training/growth`、`/training/growth/profile`
- 团队：`/training/team/competencies`、`/training/team/scenarios`、`/training/team/members`
- 准备与设置：`/training/prep/battle`、`/training/prep/defense`、`/training/settings`

`/training/team/members` 仅对平台管理员开放。完整旧页面映射和退场判断见 [前端迁移矩阵](docs/frontend-migration-matrix.md)。

## 本地开发

Windows 默认入口会启动 NewAPI Go、NewAPI Rsbuild web 和 TalkWise FastAPI，并把当前 FastAPI 地址注入 `TALKWISE_TRAINING_UPSTREAM_URL`：

```powershell
.\start-dev.cmd
```

默认地址：

```text
NewAPI web / TalkWise 模块: http://127.0.0.1:5177/training
TalkWise FastAPI:          http://127.0.0.1:8012
FastAPI docs:              http://127.0.0.1:8012/docs
NewAPI Go:                 http://127.0.0.1:18080
```

只检查现有环境：

```powershell
.\scripts\check-dev.ps1
```

若 `/api/talkwise/*` 返回 `TalkWise training proxy is not configured`，检查 NewAPI 进程或容器是否设置了 `TALKWISE_TRAINING_UPSTREAM_URL`。该值应是 FastAPI 根地址，不包含训练 API 子路径。

## 验证

```powershell
# TalkWise FastAPI
Push-Location backend
..\.venv-backend\Scripts\python.exe -m pytest tests
Pop-Location

# 唯一前端宿主
Push-Location outside-project\new-api-main\web
bun test src\features\training
bun run typecheck
bun run build
Pop-Location

# NewAPI Go
wsl -d Ubuntu-22.04 -- bash -lc 'cd /mnt/f/AnchorOS/6-项目仓库/Talk-training-studio/outside-project/new-api-main && go test ./controller ./router'

git diff --check
git -C outside-project\new-api-main diff --check
```

## 关键能力

- Persona 列表、材料构建、五层画像编辑、证据与训练启动。
- 场景训练、Battle Prep、Defense Prep 和统一 TrainingSession/conversation tree。
- 文本分支、编辑、重试、fork、selected path 指导、结束训练和复盘证据。
- 回合制语音、低成本 near-realtime、Pipecat 风格 true realtime、视频回答和认证媒体回放。
- 真实评分、能力雷达、训练历史、持久化 Training Points/等级和沟通名片。
- 沟通名片可选附带 NewAPI 原生账号邀请链接与二维码；默认关闭，不公开训练资源。
- 独立训练团队、管理员成员搜索/增删和团队训练分析。

## 工程事实源

- 开发与架构规则：[AGENTS.md](AGENTS.md)
- 代码图谱入口：[项目目录结构索引](docs/项目目录结构索引.md)
- 页面迁移事实：[前端迁移矩阵](docs/frontend-migration-matrix.md)
- 当前部署流程：[服务器部署操作手册](docs/development/server-deployment-runbook.md)

本仓库的代码影响分析使用 code-review-graph；Graphify 只用于 AnchorOS / OpenEvolve 跨文档知识关系。
