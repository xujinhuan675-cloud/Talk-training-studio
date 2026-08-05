# TalkWise 生产部署操作手册

本文档是 Talk Training Studio / TalkWise 的生产部署事实源，用于后续“本地服务更新后推到服务器”场景。旧独立 Vite/Nginx 前端流程已退役，不再作为发布或回滚路径。

不要在本文档、日志、最终报告或提交信息中输出数据库密码、Redis 密码、NewAPI token、渠道 key、`SESSION_SECRET`、`TALKWISE_CLIENT_SECRET` 或 backend `SECRET_KEY`。

## 1. 快速入口

本地仓库：

- 根仓库：`F:\AnchorOS\6-项目仓库\Talk-training-studio`
- NewAPI：`outside-project/new-api-main`
- NewAPI web：`outside-project/new-api-main/web`
- TalkWise backend：`backend`
- 生产 compose 参考：`docker-compose.newapi-staging.yml`
- NewAPI 子仓库规则：`outside-project/new-api-main/AGENTS.md`

服务器入口：

- SSH：优先使用本机 SSH alias `lcayun-1panel`；如果 alias 不存在，先读取本机 SSH config，不要在文档里补写密钥。
- NewAPI 1Panel 应用目录：`/opt/1panel/apps/new-api/new-api`
- TalkWise 应用目录：`/opt/talkwise`
- 发布暂存目录：`/opt/talkwise-releases/<release-id>`
- 备份目录：`/opt/talkwise-backups/deploy-<timestamp>`
- Caddy 配置：`/etc/caddy/Caddyfile`
- TalkWise Cloudflare tunnel：`/etc/cloudflared/talkwise.yml`

当前公网入口：

- NewAPI 网关和控制面：`https://newapi.flowguide.cc`
- TalkWise 前台入口：`https://talkwise.flowguide.cc`
- 当前策略：两个域名都进入 NewAPI host；`newapi.flowguide.cc` 作为网关域名保持不动，`talkwise.flowguide.cc` 作为 TalkWise 前台域名。

## 2. 当前生产拓扑

```text
Browser
  -> HTTPS / Cloudflare / Caddy
  -> NewAPI Go + NewAPI web/dist（唯一前端宿主，:3030 -> :3000）
  -> /api/talkwise/* 同源受认证代理
  -> TalkWise FastAPI（127.0.0.1:8012 -> :8000）
  -> TalkWise backend PostgreSQL 数据库

NewAPI Go
  -> existing PostgreSQL container（NewAPI business data）
  -> existing Redis container（cache / limit / session / shared state）
  -> /v1/* OpenAI-compatible relay
  -> /pg/* user-billed relay
```

生产容器：

- `1Panel-new-api-4jUC`：NewAPI host，端口 `3030->3000`，网络 `1panel-network`
- `talkwise-backend`：TalkWise FastAPI，端口 `127.0.0.1:8012->8000`，网络 `1panel-network` 和 `talkwise_talkwise-network`
- `1Panel-postgresql-LWUC`：现有 PostgreSQL，端口 `127.0.0.1:5432->5432`，网络 `1panel-network`
- `1Panel-redis-m6tI`：现有 Redis，网络 `1panel-network`
- `talkwise-frontend`：旧 nginx 前端容器，当前只保留为回滚入口，不再作为正常入口

当前网络：

- `1panel-network`：NewAPI、PostgreSQL、Redis、TalkWise backend 共用
- `talkwise_talkwise-network`：TalkWise backend 与旧 frontend 保留网络

## 3. 2026-08-04 部署基线

当前已上线版本：

- 根仓库 commit：`d5690072963f6c034324dd3c138cebe135a75edb`
- NewAPI commit：`76d8def66c528a74cad1495ff1f78d3cff5e0f93`
- 构建版本：`talkwise-prod-20260804-d569007-76d8def`
- NewAPI 镜像：`talkwise-newapi:prod-20260804-d569007-76d8def`
- backend 镜像：`talkwise-backend:prod-20260804-d569007`

本次生产切换结果：

- NewAPI 已从 SQLite 切换到现有 PostgreSQL。
- NewAPI SQLite 数据已迁移到 PostgreSQL `newapi` 数据库。
- NewAPI 已接入现有 Redis。
- backend 已接入现有 Redis，并继续使用 TalkWise 自己的 PostgreSQL 业务库。
- `talkwise.flowguide.cc` 的 Cloudflare tunnel upstream 已从 `127.0.0.1:8081` 切到 `127.0.0.1:3030`。
- 旧 frontend 容器和旧配置均保留，不删除。

本次备份目录：

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

## 7. 本地验证与构建

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
```

NewAPI Go 必须使用 WSL Go：

```powershell
wsl -d Ubuntu-22.04 -- bash -lc "cd /mnt/f/AnchorOS/6-项目仓库/Talk-training-studio/outside-project/new-api-main && go build -o /mnt/f/AnchorOS/6-项目仓库/Talk-training-studio/.artifacts/new-api-linux-amd64"
```

完成后记录：

- 根仓库 commit
- NewAPI commit
- build time UTC
- release id
- 构建产物路径

如果本地 Docker 无法拉取基础镜像，不要降低生产要求。可在服务器复用已有基础镜像构建 rebase 镜像，但必须确认依赖未变化；如果 `backend/requirements.txt` 变化，必须重新构建依赖层或明确阻塞。

## 8. NewAPI 生产 env 要求

NewAPI 生产必须使用 PostgreSQL + Redis，不得使用 SQLite。

`/opt/1panel/apps/new-api/new-api/.env` 必须包含以下类型配置：

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

NEWAPI_BASE_URL=http://1Panel-new-api-4jUC:3000
NEWAPI_GATEWAY_BASE_URL=http://1Panel-new-api-4jUC:3000/v1
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
REALTIME_BASE_URL=ws://1Panel-new-api-4jUC:3000/pg/realtime
```

当前文本默认模型基线：

```dotenv
OPENAI_COMPATIBLE_MODEL=deepseek/deepseek-v4-flash
LLM__DEFAULT_MODEL=deepseek/deepseek-v4-flash
```

当前生产渠道尚未提供 `tts-1` 和 `gpt-4o-mini-transcribe` 对应可用模型；TTS/STT 验证会返回 NewAPI `model_not_found`。不要把这个结果误判为 PostgreSQL、Redis、反向代理或 backend 部署失败。

## 10. 数据迁移规则

NewAPI 已在 2026-08-04 从 SQLite 迁移到 PostgreSQL。后续普通发布不要重复执行 SQLite -> PostgreSQL 初始迁移。

只有在明确执行数据库迁移或灾备恢复时，才处理：

- `/opt/1panel/apps/new-api/new-api/data/one-api.db`
- PostgreSQL `newapi` 数据库

迁移原则：

- 先备份 PostgreSQL 和 SQLite 数据文件。
- 先让 NewAPI 在 PostgreSQL 上完成 schema migration。
- 再按表迁移数据，只输出表名和行数，不输出行内容。
- 迁移后检查用户、渠道、token、options 等关键表行数。

TalkWise 训练业务数据继续由 backend 自己的 Alembic 管理；不要把训练 session、scenario、persona、evaluation、growth 等业务数据迁入 NewAPI 数据库。

## 11. 部署顺序

标准顺序：

1. 读取规则和本文档。
2. 执行服务器只读检查。
3. 创建时间戳备份。
4. 本地运行 NewAPI web tests/typecheck/build。
5. 本地运行 backend tests。
6. 使用 WSL Go 构建 NewAPI Go。
7. 上传构建产物或镜像到 `/opt/talkwise-releases/<release-id>`。
8. 生成或加载 NewAPI 镜像。
9. 生成或加载 backend 镜像。
10. 写入生产 env，保持密钥稳定。
11. 先启动或更新 `talkwise-backend`。
12. 再启动或更新 `1Panel-new-api-4jUC`。
13. 确认 backend、NewAPI、PostgreSQL、Redis 健康。
14. 确认 `talkwise.flowguide.cc` 仍指向 NewAPI host。
15. 执行验证和压测。

切换服务：

```powershell
ssh lcayun-1panel "cd /opt/talkwise && docker compose up -d backend"
ssh lcayun-1panel "cd /opt/1panel/apps/new-api/new-api && docker compose up -d"
```

`talkwise.flowguide.cc` 当前由 Cloudflare tunnel 管理：

```yaml
hostname: talkwise.flowguide.cc
service: http://127.0.0.1:3030
```

不要把它切回 `8081`，除非执行回滚。

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

`newapi.flowguide.cc` 当前由 Caddy 反代到 `127.0.0.1:3030`。

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

- PostgreSQL `newapi` 数据库可连接，关键表有行数。
- Redis `PING` 返回 `PONG`。
- NewAPI 容器 env 存在 `SQL_DSN`、`REDIS_CONN_STRING`、`BATCH_UPDATE_ENABLED`、relay 连接池配置。
- backend 容器 env 存在 `NEWAPI_USER_RELAY_BASE_URL`、`NEWAPI_USER_RELAY_REALTIME_URL`、`REDIS__URL`。

业务探测：

- 未登录访问受保护训练 API 应返回 `401`，不是代理未配置。
- `/v1/models` 带有效 token 应返回 `200`。
- 文本模型请求只做一次短请求，避免重复计费。
- TTS/STT 只有在 NewAPI 渠道已配置对应模型时才验证成功；否则记录 `model_not_found`，不要重复请求。
- `/v1/realtime` 和 `/pg/realtime` WebSocket 无 token 探测返回 `401` 说明已到鉴权层；如果返回 `404` 或 HTML，说明路由/代理错误。

## 14. 并发压测

压测不要用模型接口刷并发，除非用户明确要求并接受可能计费。默认用 `/api/status` 验证网关、代理、PostgreSQL、Redis 和容器状态。

2026-08-04 基线：

- 20 路 `/api/status`：`20/20` 成功，p50 约 `908ms`，p95 约 `950ms`
- 100 路 `/api/status`：`100/100` 成功，p50 约 `1267ms`，p95 约 `1893ms`
- 300 路 `/api/status`：出现 NewAPI `429` 限流；细分复测为 `300/300` 返回 `429`
- 没有观察到 502/504
- PostgreSQL 未观察到锁错误
- Redis `blocked_clients=0`、`rejected_connections=0`

结论：当前机器和默认限流下，100 路健康探测稳定；300 路会触发 NewAPI 限流。不要通过关闭限流来掩盖问题。服务器升级后可提高 env 连接池并重新压测，但仍以实际结果为准。

## 15. 回滚方法

回滚单位：

- NewAPI 镜像与 `/opt/1panel/apps/new-api/new-api` env/compose
- TalkWise backend 镜像与 `/opt/talkwise` env/compose
- 反向代理配置
- 必要时数据库备份

优先回滚镜像和配置：

```powershell
ssh lcayun-1panel "cd /opt/1panel/apps/new-api/new-api && cp docker-compose.yml.bak-deploy-<release-id> docker-compose.yml && cp .env.bak-deploy-<release-id> .env && docker compose up -d"
ssh lcayun-1panel "cd /opt/talkwise && cp docker-compose.yml.bak-deploy-<release-id> docker-compose.yml && cp backend.env.bak-deploy-<release-id> backend.env && docker compose up -d backend"
```

如果要把 TalkWise 域名回滚到旧前端：

```powershell
ssh lcayun-1panel "cp /etc/cloudflared/talkwise.yml.bak-deploy-<release-id> /etc/cloudflared/talkwise.yml && systemctl restart cloudflared-talkwise"
```

旧 `talkwise-frontend` 容器保留在 `8081`，但它只是临时回滚入口，不是长期架构。

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
