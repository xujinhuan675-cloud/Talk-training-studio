# TalkWise 服务器部署操作手册

本文档描述当前唯一受支持的生产拓扑。旧的独立 Vite/Nginx 前端发布流程已归档到 `docs/archive/server-deployment-runbook-legacy-vite.md`，仅用于历史追溯，不得用于新发布。

## 1. 目标拓扑

```text
Browser
  -> NewAPI Go（内嵌 NewAPI web/dist，唯一前端宿主）
  -> /api/talkwise/* 同源受认证代理
  -> 独立 TalkWise FastAPI
  -> TalkWise 自己的数据库与迁移
```

- NewAPI 保持账号、登录、平台 Shell、导航、主题、用量、计费和管理控制面。
- TalkWise FastAPI 保持训练场景、Persona、TrainingSession、conversation tree、评分、复盘、成长、语音和视频语义。
- 不部署 `frontend/dist`，不启动独立 TalkWise Nginx/Vite 容器。

## 2. 发布前验证

在仓库根目录执行：

```powershell
Push-Location backend
..\.venv-backend\Scripts\python.exe -m pytest tests
Pop-Location

Push-Location outside-project\new-api-main\web
bun test src\features\training
bun run typecheck
bun run build
Pop-Location

wsl -d Ubuntu-22.04 -- bash -lc 'cd /mnt/f/AnchorOS/6-项目仓库/Talk-training-studio/outside-project/new-api-main && go test ./controller ./router'

git diff --check
git -C outside-project\new-api-main diff --check
```

如果 `bun run typecheck` 出现仓库既有、与训练模块无关的错误，需要记录基线并确认本轮没有新增错误；不得跳过 `bun run build`。

## 3. 构建 NewAPI 唯一宿主

NewAPI 根目录 `Dockerfile` 会先构建 `web/dist`，再把它复制进 Go 镜像并由 `//go:embed web/dist` 内嵌。发布时使用该 Dockerfile 或等价流水线：

```powershell
docker build -t talkwise-newapi:<release> outside-project\new-api-main
```

不要单独上传或挂载 web 产物，也不要把旧 `frontend/dist` 挂载到 Nginx。

## 4. 必需配置

NewAPI Go 容器至少需要：

```dotenv
TALKWISE_TRAINING_UPSTREAM_URL=http://talkwise-api:8000
TALKWISE_CLIENT_ID=talkwise
TALKWISE_CLIENT_SECRET=<shared-secret>
TALKWISE_REDIRECT_URIS=https://<host>/training
TALKWISE_GATEWAY_BASE_URL=https://<host>/v1
SESSION_SECRET=<strong-session-secret>
```

TalkWise FastAPI 容器至少需要：

```dotenv
NEWAPI_BASE_URL=http://new-api:3000
NEWAPI_AUTH_ENABLED=true
NEWAPI_AUTH_ALLOW_MOCK_FALLBACK=false
NEWAPI_TALKWISE_CLIENT_ID=talkwise
NEWAPI_TALKWISE_CLIENT_SECRET=<same-shared-secret>
NEWAPI_TALKWISE_REDIRECT_URI=https://<host>/training
DATABASE__URL=<talkwise-database-dsn>
SECRET_KEY=<strong-backend-secret>
```

`TALKWISE_TRAINING_UPSTREAM_URL` 必须从 NewAPI 容器网络中可达。缺失时 `/api/talkwise/*` 会返回 `TalkWise training proxy is not configured`；这不是前端设置数据错误。

仓库 staging 示例已在 `.env.newapi-staging.example` 和 `docker-compose.newapi-staging.yml` 中维护。生产密钥只能放在部署环境或 secret manager，不能提交到仓库。

## 5. 数据库迁移

NewAPI 的独立训练团队表由其 GORM migration 创建；TalkWise 的 Training Points 账本由 Alembic 管理。先备份两套数据库，再分别执行当前版本的标准迁移流程。TalkWise 示例：

```powershell
Push-Location backend
..\.venv-backend\Scripts\python.exe -m alembic upgrade head
Pop-Location
```

不要把 TalkWise 训练表迁入 NewAPI 数据库。NewAPI 新增的 `training_teams` 与 `training_team_memberships` 只保存平台侧训练团队成员关系，不保存训练业务数据，也不修改 `users.group`、额度或计费字段。

## 6. 上线与健康检查

发布后依次验证：

```text
GET  https://<host>/api/status
GET  https://<host>/training
GET  https://<host>/api/talkwise/training/growth/summary
GET  https://<host>/api/talkwise/admin/teams          （admin 身份）
GET  https://<talkwise-api>/health/live
```

预期：

- `/api/status` 返回成功；`/training` 由 NewAPI web 提供。
- 未登录访问受保护训练 API 返回认证失败，而不是代理未配置。
- 已登录用户只能读取 TalkWise 最终授权允许的训练资源。
- 管理员可以维护训练团队；普通用户不能访问 `/api/talkwise/admin/*`。
- 添加或移除训练团队成员后，NewAPI 用户的 gateway group、quota、used quota 和 request count 不变化。

## 7. 回滚

回滚单位是“NewAPI 镜像 + TalkWise FastAPI 镜像 + 对应数据库备份/向后兼容迁移”，不是切回旧 Vite 前端。

1. 保留上一个 NewAPI 与 TalkWise backend 镜像标签。
2. 数据迁移前备份 NewAPI 和 TalkWise 两套数据库。
3. 应用异常时先回滚镜像；只有迁移不向后兼容时才按 Alembic/GORM 兼容方案处理数据库。
4. 旧 `frontend/` 已退役，不是运行时回滚路径。

## 8. 常见故障

### `TalkWise training proxy is not configured`

检查 NewAPI 进程或容器的 `TALKWISE_TRAINING_UPSTREAM_URL`。它应指向 TalkWise FastAPI 根地址，不包含 `/api/v1/training-studio`，代理会自行拼接受限路径。

### 训练 API 返回 401/403

先确认浏览器使用 NewAPI 会话，再确认 FastAPI 收到由 NewAPI 验证的 Bearer 身份。不要通过 query/body 添加 user、team 或 role 绕过身份桥。

### 团队成员加入后模型访问变化

这是回归。训练团队只能写 `training_team_memberships`；任何修改 `users.group` 或计费字段的路径都必须停止发布并回滚。

### 前端仍显示旧页面

确认发布的是从当前 NewAPI 根 `Dockerfile` 构建的镜像，并检查 Go 内嵌的 `web/dist`。不要修复或重新部署旧 `frontend/dist`。
