# TalkWise 生产部署操作手册

本文档是 Talk Training Studio / TalkWise 的生产部署事实源，用于后续“本地服务更新后推到服务器”场景。旧独立 Vite/Nginx 前端流程已退役，不再作为发布或回滚路径。

不要在本文档、日志、最终报告或提交信息中输出数据库密码、Redis 密码、NewAPI token、渠道 key、`SESSION_SECRET`、`TALKWISE_CLIENT_SECRET` 或 backend `SECRET_KEY`。

## 1. 快速入口

本地仓库：

- 根仓库：`F:\AnchorOS\6-项目仓库\TalkWise`
- NewAPI：`outside-project/new-api-main`
- NewAPI web：`outside-project/new-api-main/web`
- TalkWise backend：`backend`
- 生产 compose 参考：`docker-compose.newapi-staging.yml`
- NewAPI 子仓库规则：`outside-project/new-api-main/AGENTS.md`

服务器入口：

- SSH：优先使用本机 SSH alias `lcayun-1panel`；如果 alias 不存在，先读取本机 SSH config，不要在文档里补写密钥。
- NewAPI 1Panel 应用目录：`/opt/1panel/apps/new-api/new-api`
- 官方通用 NewAPI 目录：`/opt/newapi-official`
- TalkWise 应用目录：`/opt/talkwise`
- 发布暂存目录：`/opt/talkwise-releases/<release-id>`
- 备份目录：`/opt/talkwise-backups/deploy-<timestamp>`
- Caddy 配置：`/etc/caddy/Caddyfile`
- TalkWise Cloudflare tunnel：`/etc/cloudflared/talkwise.yml`

当前公网入口：

- NewAPI 网关和控制面：`https://newapi.flowguide.cc`
- TalkWise 前台入口：`https://talkwise.flowguide.cc`
- 当前策略：两个域名进入不同容器；`talkwise.flowguide.cc` 进入 TalkWise 深改 NewAPI 宿主，`newapi.flowguide.cc` 进入官方原生 NewAPI 通用网关。

## 2. 当前生产拓扑

```text
Browser
  -> talkwise.flowguide.cc / Cloudflare tunnel
  -> TalkWise 深改 NewAPI Go + web/dist（TalkWise 唯一前端宿主，:3030 -> :3000）
  -> /api/talkwise/* 同源受认证代理
  -> TalkWise FastAPI（127.0.0.1:8012 -> :8000）
  -> TalkWise backend PostgreSQL 数据库

Service / Admin
  -> newapi.flowguide.cc / Caddy
  -> 官方原生 NewAPI v1.0.0-rc.25（:3031 -> :3000）
  -> PostgreSQL newapi_official
  -> Redis DB 2
  -> /v1/* OpenAI-compatible relay
```

生产容器：

- `1Panel-new-api-4jUC`：TalkWise 深改 NewAPI host，端口 `127.0.0.1:3030->3000`，数据库 `newapi`，Redis DB 0，网络 `1panel-network`
- `newapi-official-gateway`：官方原生 NewAPI 通用网关，端口 `127.0.0.1:3031->3000`，数据库 `newapi_official`，Redis DB 2，网络 `1panel-network`
- `talkwise-backend`：TalkWise FastAPI，端口 `127.0.0.1:8012->8000`，网络 `1panel-network` 和 `talkwise_talkwise-network`
- `1Panel-postgresql-LWUC`：现有 PostgreSQL，端口 `127.0.0.1:5432->5432`，网络 `1panel-network`
- `1Panel-redis-m6tI`：现有 Redis，网络 `1panel-network`
- `talkwise-frontend`：旧 nginx 前端容器，状态为 stopped、restart policy 为 `no`，Compose profile 为 `legacy-disabled`；仅保留历史证据，不参与正常流量或正式回滚

当前网络：

- `1panel-network`：TalkWise 深改 NewAPI、官方 NewAPI、PostgreSQL、Redis、TalkWise backend 共用容器网络，但应用数据库和 Redis DB 保持隔离
- `talkwise_talkwise-network`：TalkWise backend 与旧 frontend 保留网络

## 3. 生产部署基线

### 2026-08-20 当前基线

当前生产拆分：

- TalkWise 深改镜像：`talkwise-newapi:prod-20260811-8ff03af-575c15a`
- 官方通用网关镜像：`calciumion/new-api:v1.0.0-rc.25`
- 官方镜像 ID：`sha256:54a0b10924aa75fa5b5947208b820ced66b6ef4b445b35f122b31d80676aba2b`
- TalkWise backend 镜像：`talkwise-backend:prod-20260811-8ff03af`
- 备份目录：`/opt/talkwise-backups/deploy-20260820-044503`

该次拆分结果：

- `talkwise.flowguide.cc` 继续指向 `127.0.0.1:3030` 的 TalkWise 深改宿主。
- `newapi.flowguide.cc` 已切到 `127.0.0.1:3031` 的官方原生 NewAPI。
- 原 `newapi` 数据库继续供 TalkWise 深改宿主使用；一致性快照恢复到独立 `newapi_official` 数据库，迁移了 7 个用户、4 个渠道、4 个 token 和 111 条日志。
- 官方实例保留账号、渠道、token、额度、价格和日志数据，但移除了复制库中的 TalkWise 品牌、首页和训练导航配置。
- 现有 API token 通过官方实例的公网 `/v1/models` 返回 `200`，可见 34 个模型。
- TalkWise backend 的标准 `NEWAPI_GATEWAY_BASE_URL` 已改为 `http://newapi-official-gateway:3000/v1`；auth bridge 和 TalkWise 专属 `/pg` relay 仍由深改宿主承载。
- 旧 `talkwise-frontend` 已停止并禁用默认 Compose 启动，`8081` 无监听。

### 2026-08-11 历史基线

当前已上线版本：

- 根仓库 commit：`8ff03afb5aac1285e4d3c0c67706930aafdcd9d5`
- NewAPI commit：`575c15af9e301719590af706358caf433ce5433f`
- release id：`talkwise-prod-20260811-8ff03af-575c15a`
- NewAPI 镜像：`talkwise-newapi:prod-20260811-8ff03af-575c15a`
- NewAPI OCI digest：`sha256:390559c0ac2b989a85e5fd448cf50e8b7b898d14db6a2b6201d249017d279a2f`
- backend 镜像：`talkwise-backend:prod-20260811-8ff03af`
- backend image id：`sha256:787f6e19863e510d1e32189dd178f5a27e4dd3374ef36bc9d9ad643071812915`

当前生产状态：

- `talkwise.flowguide.cc` 和 `newapi.flowguide.cc` 均由 NewAPI host 提供，训练后端继续独立承载 TalkWise 业务语义。
- NewAPI、backend、PostgreSQL、Redis 均通过健康检查；NewAPI/backend 容器未发生 restart 或 OOM。
- PostgreSQL `5432`、Redis `6379`、NewAPI `3030`、backend `8012` 和历史 frontend `8081` 均只绑定 `127.0.0.1`，不直接暴露公网。
- `/health/voice/ready` 已配置独立监控 token；有权限的探测返回 `200`，无 token 返回 `403`，响应不回显 token。
- Caddy 配置已格式化、校验并 reload；Cloudflare tunnel 继续指向 `127.0.0.1:3030`。
- 历史 frontend 容器只作取证保留，不承接流量，也不是正式回滚入口。

本次备份和发布目录：

- `/opt/talkwise-backups/deploy-20260811-135513`
- `/opt/talkwise-releases/talkwise-prod-20260811-8ff03af-575c15a`

备份包含 PostgreSQL 全量及业务库 dump、TalkWise/NewAPI/Redis 应用目录、compose/env、Caddy、cloudflared、openresty 配置和 SHA256 校验文件。发布目录包含 backend 源码包、部署结果和校验文件。

### 2026-08-04 历史基线

当时上线版本：

- 根仓库 commit：`d5690072963f6c034324dd3c138cebe135a75edb`
- NewAPI commit：`76d8def66c528a74cad1495ff1f78d3cff5e0f93`
- 构建版本：`talkwise-prod-20260804-d569007-76d8def`
- NewAPI 镜像：`talkwise-newapi:prod-20260804-d569007-76d8def`
- backend 镜像：`talkwise-backend:prod-20260804-d569007`

该次生产切换结果：

- NewAPI 已从 SQLite 切换到现有 PostgreSQL。
- NewAPI SQLite 数据已迁移到 PostgreSQL `newapi` 数据库。
- NewAPI 已接入现有 Redis。
- backend 已接入现有 Redis，并继续使用 TalkWise 自己的 PostgreSQL 业务库。
- `talkwise.flowguide.cc` 的 Cloudflare tunnel upstream 已从 `127.0.0.1:8081` 切到 `127.0.0.1:3030`。
- 旧 frontend 容器和旧配置均保留，不删除。

该次备份目录：

- `/opt/talkwise-backups/deploy-20260804-123208`

该备份包含 PostgreSQL dump、`/opt/talkwise`、NewAPI 1Panel 应用目录、Redis 应用目录、Caddy、cloudflared、openresty 配置和校验文件。

## 4. 发布前必须读取

每次生产发布前先读取：

- 根目录 `AGENTS.md`
- `outside-project/new-api-main/AGENTS.md`
- 本文档
- `docker-compose.newapi-staging.yml`
- 当前服务器上的 `/opt/1panel/apps/new-api/new-api/docker-compose.yml`
- 当前服务器上的 `/opt/talkwise/docker-compose.yml`
- 当前服务器上的 `/opt/talkwise/backend.env`
- 当前反向代理配置：`/etc/caddy/Caddyfile`、`/etc/cloudflared/talkwise.yml`

同时先查看：

```powershell
git status --short
git -C outside-project\new-api-main status --short
```

不要回滚或覆盖用户、其他 agent 或线上已有的无关改动。

## 5. 服务器检查

部署前先做只读检查，不要立即覆盖生产文件：

```powershell
ssh lcayun-1panel "docker version"
ssh lcayun-1panel "docker compose version"
ssh lcayun-1panel "docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'"
ssh lcayun-1panel "docker network ls"
ssh lcayun-1panel "ss -lntp"
ssh lcayun-1panel "df -h && free -h && nproc"
ssh lcayun-1panel "systemctl status caddy --no-pager"
ssh lcayun-1panel "systemctl status cloudflared-talkwise --no-pager"
```

检查 PostgreSQL 和 Redis 时只输出连通性、库名、用户存在性、行数或状态，不输出密码：

```powershell
ssh lcayun-1panel "docker exec 1Panel-postgresql-LWUC psql --version"
ssh lcayun-1panel "docker exec 1Panel-redis-m6tI redis-cli --version"
```

## 6. 发布前备份

生产发布前必须创建新的时间戳备份，不删除旧备份。至少备份：

- PostgreSQL：全量 dump 和相关数据库单独 dump
- `/opt/talkwise`
- `/opt/1panel/apps/new-api/new-api`
- 当前 Docker Compose 和 env 文件
- Caddy / Cloudflared / OpenResty 配置

备份目录命名：

```text
/opt/talkwise-backups/deploy-YYYYMMDD-HHMMSS
```

备份完成后记录 manifest 和 sha256。最终报告只写备份路径和文件类型，不输出 dump 内容。

## 7. 本地验证与 GitHub Actions 构建

生产发布的正式构建入口是 `.github/workflows/deploy.yml`：GitHub 托管 runner
构建并推送 TalkWise backend 与 TalkWise 深改 NewAPI 前端宿主镜像，服务器只执行
`docker pull`、Compose 切换和健康检查。生产发布不在本地或服务器执行 `docker build`。
官方网关实例不属于此工作流，不会被构建、拉取或重启。

下面的本地命令用于开发验证或排查，不是生产发布的构建步骤。

NewAPI web：

```powershell
cd outside-project\new-api-main\web
bun test src\features\training
bun run typecheck
bun run build
```

backend：

```powershell
cd backend
..\.venv-backend\Scripts\python.exe -m pytest tests
docker build -f Dockerfile.deploy -t <backend-image> .
docker run --rm --entrypoint sh <backend-image> -lc "test -f /app/alembic.ini && test -f /app/alembic/env.py && python -m alembic -c /app/alembic.ini heads"
```

生产 backend 使用版本化的 `backend/Dockerfile.deploy`，通过 `uv.lock` 和 `uv sync --frozen` 固定 Python 依赖。生产开启 `AUTO_RUN_MIGRATIONS=true`，镜像内必须包含 `/app/alembic.ini`、`/app/alembic/env.py` 和迁移版本；内容检查或 Alembic head 检查失败时禁止继续发布。

NewAPI Go 必须使用 WSL Go：

```powershell
wsl -d Ubuntu-22.04 -- bash -lc "cd /mnt/f/AnchorOS/6-项目仓库/TalkWise/outside-project/new-api-main && go build -o /mnt/f/AnchorOS/6-项目仓库/TalkWise/.artifacts/new-api-linux-amd64"
```

完成后记录：

- 根仓库 commit
- NewAPI commit
- build time UTC
- release id
- 构建产物路径

如果本地 Docker 无法拉取基础镜像，不要降低生产要求。依赖未变化时可在服务器复用已验证的 backend 依赖层进行 rebase，但必须使用本次版本化 `Dockerfile.deploy` 或等价的可审计构建上下文，并通过镜像内容、导入和健康检查；如果 `backend/pyproject.toml` 或 `backend/uv.lock` 变化，必须重新构建依赖层或明确阻塞。

## 8. NewAPI 生产 env 要求

NewAPI 生产必须使用 PostgreSQL + Redis，不得使用 SQLite。

TalkWise 深改宿主的 `/opt/1panel/apps/new-api/new-api/.env` 必须包含以下类型配置：

```dotenv
SQL_DSN=postgresql://<newapi-user>:<password>@1Panel-postgresql-LWUC:5432/newapi
REDIS_CONN_STRING=redis://:<password>@1Panel-redis-m6tI:6379/0
BATCH_UPDATE_ENABLED=true

SQL_MAX_OPEN_CONNS=<env-tunable>
SQL_MAX_IDLE_CONNS=<env-tunable>
SQL_MAX_LIFETIME=<env-tunable>
REDIS_POOL_SIZE=<env-tunable>

RELAY_MAX_IDLE_CONNS=2048
RELAY_MAX_IDLE_CONNS_PER_HOST=512
RELAY_MAX_CONNS_PER_HOST=0

SESSION_SECRET=<stable-random-secret>
CRYPTO_SECRET=<stable-random-secret-or-session-secret>
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_TRUSTED_URL=https://newapi.flowguide.cc,https://talkwise.flowguide.cc
TRUSTED_PROXIES=127.0.0.1/32,172.19.0.0/16,172.21.0.0/16

TALKWISE_CLIENT_ID=talkwise
TALKWISE_CLIENT_SECRET=<shared-secret>
TALKWISE_REDIRECT_URIS=https://talkwise.flowguide.cc/login,https://newapi.flowguide.cc/login,https://talkwise.flowguide.cc/training,https://newapi.flowguide.cc/training
TALKWISE_GATEWAY_BASE_URL=https://newapi.flowguide.cc/v1
TALKWISE_TRAINING_UPSTREAM_URL=http://talkwise-backend:8000
```

并发参数必须作为 env 可调值维护。不要因为 `RELAY_MAX_CONNS_PER_HOST=0` 就声称系统支持无限并发；必须以压测结果为准。

官方通用网关由 `/opt/newapi-official/docker-compose.yml` 管理，只使用固定官方镜像，不从 TalkWise fork 构建。其 `.env` 复用迁移数据所需的稳定 `SESSION_SECRET`、`CRYPTO_SECRET` 和数据库用户，但必须使用独立资源：

```dotenv
SQL_DSN=postgresql://<newapi-user>:<password>@1Panel-postgresql-LWUC:5432/newapi_official
REDIS_CONN_STRING=redis://:<password>@1Panel-redis-m6tI:6379/2
SESSION_COOKIE_TRUSTED_URL=https://newapi.flowguide.cc
```

官方实例不得配置 `TALKWISE_*` 环境变量，也不得加入 TalkWise 训练路由、品牌配置或前端源码。

## 9. backend 生产 env 要求

`/opt/talkwise/backend.env` 至少应保证：

```dotenv
ENVIRONMENT=production
DEBUG=false
AUTO_RUN_MIGRATIONS=true

DATABASE__URL=<talkwise-postgres-dsn>
SECRET_KEY=<stable-random-secret>
REDIS__URL=redis://:<password>@1Panel-redis-m6tI:6379/1
REDIS__MAX_CONNECTIONS=<env-tunable>
REDIS__NAMESPACE=talkwise
HEALTH__ACCESS_TOKEN=<stable-random-monitoring-secret>

NEWAPI_BASE_URL=http://1Panel-new-api-4jUC:3000
NEWAPI_GATEWAY_BASE_URL=http://newapi-official-gateway:3000/v1
NEWAPI_USER_BILLING_ENABLED=true
NEWAPI_USER_RELAY_BASE_URL=http://1Panel-new-api-4jUC:3000/pg
NEWAPI_USER_RELAY_REALTIME_URL=ws://1Panel-new-api-4jUC:3000/pg/realtime

NEWAPI_AUTH_ENABLED=true
NEWAPI_AUTH_ALLOW_MOCK_FALLBACK=false
NEWAPI_TALKWISE_CLIENT_ID=talkwise
NEWAPI_TALKWISE_CLIENT_SECRET=<same-shared-secret>
NEWAPI_TALKWISE_REDIRECT_URI=https://talkwise.flowguide.cc/login

OPENAI_COMPATIBLE_BASE_URL=http://1Panel-new-api-4jUC:3000/pg
LLM__BASE_URL=http://1Panel-new-api-4jUC:3000/pg
```

实时用户计费链路只使用上面的 `NEWAPI_USER_RELAY_REALTIME_URL`；不要再写入已废弃且代码不读取的 `REALTIME_BASE_URL`。

这里的地址分工不能合并：`NEWAPI_BASE_URL` 用于 TalkWise auth bridge 和控制面，必须指向深改宿主；标准 `NEWAPI_GATEWAY_BASE_URL` 用于通用 `/v1` 模型调用，必须指向官方原生实例；`/pg` 是 TalkWise 专属扩展，在官方实例没有等价契约前仍指向深改宿主。

`/health/voice/ready` 必须配置 `HEALTH__ACCESS_TOKEN` 才会执行非计费语音就绪检查。监控请求通过 `Authorization: Bearer <token>` 或 `X-Access-Token` 传入；报告和日志不得输出 token。

当前文本默认模型基线：

```dotenv
OPENAI_COMPATIBLE_MODEL=deepseek/deepseek-v4-flash
LLM__DEFAULT_MODEL=deepseek/deepseek-v4-flash
```

当前生产渠道尚未提供 `tts-1` 和 `gpt-4o-mini-transcribe` 对应可用模型；TTS/STT 验证会返回 NewAPI `model_not_found`。不要把这个结果误判为 PostgreSQL、Redis、反向代理或 backend 部署失败。

## 10. 数据迁移规则

NewAPI 已在 2026-08-04 从 SQLite 迁移到 PostgreSQL。2026-08-20 又从 `newapi` 创建一致性快照并恢复为 `newapi_official`，此后两个数据库独立演进；后续普通发布不要重复执行初始迁移或自动双向同步。

只有在明确执行数据库迁移或灾备恢复时，才处理：

- `/opt/1panel/apps/new-api/new-api/data/one-api.db`
- PostgreSQL `newapi` 数据库
- PostgreSQL `newapi_official` 数据库

迁移原则：

- 先备份 PostgreSQL 和 SQLite 数据文件。
- 先让 NewAPI 在 PostgreSQL 上完成 schema migration。
- 再按表迁移数据，只输出表名和行数，不输出行内容。
- 迁移后检查用户、渠道、token、options 等关键表行数。

TalkWise 训练业务数据继续由 backend 自己的 Alembic 管理；不要把训练 session、scenario、persona、evaluation、growth 等业务数据迁入 NewAPI 数据库。

## 11. 部署顺序

标准顺序：

1. 读取规则和本文档，确认工作区和子模块状态。
2. 对本次代码运行本地 focused tests；不要在本地执行生产镜像构建。
3. 确认 GitHub Actions secrets `DEPLOY_SSH_HOST`、`DEPLOY_SSH_PORT`、`DEPLOY_SSH_USER`、`DEPLOY_SSH_KEY` 已配置。
4. 使用 `scripts/deploy-server.ps1 -Push` 推送干净的提交，或在 GitHub Actions 手动 dispatch。
5. GitHub runner checkout 根仓库和 `outside-project/new-api-main` 子模块，构建两个 `linux/amd64` 镜像并推送 GHCR。
6. Actions 通过 SSH 传输 `scripts/remote-deploy.sh`；服务器创建 Compose/env 备份，拉取两个镜像并更新 TalkWise backend 与深改 NewAPI 服务。
7. 远端脚本对两个服务执行健康检查；任一失败都会恢复上一版镜像。
8. 确认 `talkwise.flowguide.cc -> 3030`、TalkWise backend `127.0.0.1:8012` 以及 PostgreSQL/Redis 健康。
9.官方网关 `newapi.flowguide.cc` 不在本流程内，除非单独进行官方网关维护。

紧急情况下的服务重启只允许使用已经写入服务器 Compose 的当前镜像：

```powershell
ssh lcayun-1panel "cd /opt/talkwise && docker compose up -d backend"
ssh lcayun-1panel "cd /opt/1panel/apps/new-api/new-api && docker compose up -d new-api"
```

`talkwise.flowguide.cc` 当前由 Cloudflare tunnel 管理：

```yaml
hostname: talkwise.flowguide.cc
service: http://127.0.0.1:3030
```

不要把它切回 `8081`。旧 frontend 不是正式回滚路径；正式回滚继续让 TalkWise 域名指向深改宿主，只恢复上一版 TalkWise NewAPI/backend 镜像与配置。

## 12. 反向代理要求

生产入口必须支持：

- HTTPS
- `/api/*`
- `/v1/*`
- `/pg/*`
- `/v1/realtime` WebSocket
- `/pg/realtime` WebSocket
- 长请求和流式响应
- WebSocket upgrade，不得按普通 HTTP 请求代理

`newapi.flowguide.cc` 当前由 Caddy 反代到 `127.0.0.1:3031` 的官方原生 NewAPI。

`talkwise.flowguide.cc` 当前由 `cloudflared-talkwise.service` 反代到 `127.0.0.1:3030`。

如果改反向代理，先备份配置，并用 WebSocket 握手探测确认不是 404 或普通 HTTP fallback。

## 13. 发布后验证

基础健康检查：

```powershell
ssh lcayun-1panel "curl -k -s -o /tmp/status.out -w '%{http_code} %{time_total}' https://newapi.flowguide.cc/api/status"
ssh lcayun-1panel "curl -k -s -o /tmp/status.out -w '%{http_code} %{time_total}' https://talkwise.flowguide.cc/api/status"
ssh lcayun-1panel "curl -k -s -o /tmp/training.out -w '%{http_code} %{time_total}' https://talkwise.flowguide.cc/training"
ssh lcayun-1panel "curl -s -o /tmp/backend.out -w '%{http_code} %{time_total}' http://127.0.0.1:8012/health"
```

基础设施验证：

- PostgreSQL `newapi` 和 `newapi_official` 数据库均可连接，关键表有行数且拆分时迁移计数一致。
- Redis `PING` 返回 `PONG`。
- TalkWise 深改 NewAPI 使用 Redis DB 0，TalkWise backend 使用 DB 1，官方 NewAPI 使用 DB 2。
- 两个 NewAPI 容器 env 均存在 `SQL_DSN`、`REDIS_CONN_STRING`、`BATCH_UPDATE_ENABLED` 和 relay 连接池配置，且数据库/Redis 目标不同。
- backend 容器 env 存在 `NEWAPI_USER_RELAY_BASE_URL`、`NEWAPI_USER_RELAY_REALTIME_URL`、`REDIS__URL`。

业务探测：

- 未登录访问受保护训练 API 应返回 `401`，不是代理未配置。
- `/v1/models` 带有效 token 应返回 `200`。
- 文本模型请求只做一次短请求，避免重复计费。
- TTS/STT 只有在 NewAPI 渠道已配置对应模型时才验证成功；否则记录 `model_not_found`，不要重复请求。
- `/v1/realtime` 和 `/pg/realtime` WebSocket 无 token 探测返回 `401` 说明已到鉴权层；如果返回 `404` 或 HTML，说明路由/代理错误。

## 14. 并发压测

压测不要用模型接口刷并发，除非用户明确要求并接受可能计费。默认用 `/api/status` 验证网关、代理、PostgreSQL、Redis 和容器状态。

2026-08-11 当前基线：

- 20 路 `/api/status`：`20/20` 成功，p50 `198.3ms`，p95 `268.1ms`，最大 `284.7ms`
- 100 路 `/api/status`：`100/100` 成功，p50 `301.5ms`，p95 `440.8ms`，最大 `488.2ms`
- 没有观察到 429/502/504
- PostgreSQL 未观察到错误或死锁
- Redis `blocked_clients=0`、`rejected_connections=0`

2026-08-04 历史基线：

- 20 路 `/api/status`：`20/20` 成功，p50 约 `908ms`，p95 约 `950ms`
- 100 路 `/api/status`：`100/100` 成功，p50 约 `1267ms`，p95 约 `1893ms`
- 300 路 `/api/status`：出现 NewAPI `429` 限流；细分复测为 `300/300` 返回 `429`
- 没有观察到 502/504
- PostgreSQL 未观察到锁错误
- Redis `blocked_clients=0`、`rejected_connections=0`

结论：2026-08-11 当前版本的 100 路健康探测稳定；本次未重复执行 300 路探测。2026-08-04 的 300 路历史结果会触发 NewAPI 限流，后续不得通过关闭限流来掩盖问题。服务器升级后可提高 env 连接池并重新压测，但仍以实际结果为准。

## 15. 回滚方法

回滚单位：

- TalkWise 深改 NewAPI 镜像与 `/opt/1panel/apps/new-api/new-api` env/compose
- 官方 NewAPI 镜像与 `/opt/newapi-official` env/compose
- TalkWise backend 镜像与 `/opt/talkwise` env/compose
- 反向代理配置
- 必要时数据库备份

优先回滚镜像和配置：

```powershell
ssh lcayun-1panel "cd /opt/1panel/apps/new-api/new-api && cp docker-compose.yml.bak-deploy-<release-id> docker-compose.yml && cp .env.bak-deploy-<release-id> .env && docker compose up -d"
ssh lcayun-1panel "cd /opt/talkwise && cp docker-compose.yml.bak-deploy-<release-id> docker-compose.yml && cp backend.env.bak-deploy-<release-id> backend.env && docker compose up -d backend"
```

旧 `talkwise-frontend` 容器可以暂存用于取证，但不应重新接入域名或作为正式回滚入口。

网关拆分回滚优先把 Caddy 的 `newapi.flowguide.cc` upstream 从 `127.0.0.1:3031` 恢复为备份中的 `127.0.0.1:3030`，再 reload Caddy。只有确认官方副本发生不可兼容迁移或数据损坏时才恢复 `newapi_official`；不得覆盖仍供 TalkWise 使用的原 `newapi` 数据库。

数据库回滚只在迁移不兼容或数据损坏时执行。执行前必须再次备份当前状态，且不得删除旧备份。

## 16. 常见故障分类

`TalkWise training proxy is not configured`：

- NewAPI 未配置 `TALKWISE_TRAINING_UPSTREAM_URL`，或 env 未进入容器。
- 不是前端数据问题。

训练 API 返回 `401/403`：

- 先确认 NewAPI 登录态和 Bearer 身份桥。
- 不要通过 query/body 添加 user、team 或 role 绕过身份。

`/training` 返回旧页面：

- `talkwise.flowguide.cc` 仍指向 `127.0.0.1:8081`。
- 应检查 `/etc/cloudflared/talkwise.yml`，正常应为 `127.0.0.1:3030`。

模型请求 `503 model_not_found`：

- NewAPI 渠道没有该模型或用户分组不可用。
- 先查 `/v1/models` 和渠道 `models` 字段，不要改代码绕过。

WebSocket 返回 HTML 或 `404`：

- 反向代理未按 WebSocket upgrade 转发，或路径没有进入 NewAPI relay。
- `/v1/realtime`、`/pg/realtime` 无 token 返回 `401` 才是路由到鉴权层的合理探测结果。

Redis 启动日志泄露 URL：

- backend 代码已对 Redis URL 成功日志做脱敏。后续新增 Redis 日志时也必须脱敏。

## 17. 最终报告清单

每次生产发布最终报告必须包含：

- 实际部署架构
- 使用的 Docker 容器和网络
- PostgreSQL/Redis 是否复用成功
- 实际域名和访问入口
- NewAPI 和 TalkWise backend 状态
- 验证命令和结果
- 并发测试结果
- 回滚方法
- 未解决风险
- 确认没有输出任何密钥
- Git 修改、暂存和提交状态
