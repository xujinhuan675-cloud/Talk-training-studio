# TalkWise 服务器部署操作手册

本文档用于把本地已经调试通过的 TalkWise 代码发布到服务器，并保留首次初始化、日常发布、验证、回滚和故障处理步骤。默认操作环境是 Windows PowerShell，本机通过 SSH 别名连接服务器。

## 当前生产拓扑

| 项目 | 当前值 |
|:---|:---|
| SSH 别名 | `lcayun-1panel` |
| TalkWise 访问地址 | `https://talkwise.flowguide.cc/` |
| TalkWise 直连地址 | `http://103.38.83.199:8081/` |
| TalkWise 前端容器 | `talkwise-frontend`，`0.0.0.0:8081 -> 80` |
| TalkWise 后端容器 | `talkwise-backend`，`127.0.0.1:8012 -> 8000` |
| TalkWise Cloudflare Tunnel | `talkwise-main-app`，ID `ac33cb04-ebc8-46a4-9344-2f5d7f05a988`，服务器服务 `cloudflared-talkwise.service` |
| 服务器部署目录 | `/opt/talkwise` |
| 当前版本链接 | `/opt/talkwise/current -> /opt/talkwise/releases/release-*` |
| TalkWise 数据库 | 1Panel PostgreSQL 容器 `1Panel-postgresql-LWUC` 中的 `talkwise` |
| NewAPI | 容器 `1Panel-new-api-4jUC`，公网 `http://103.38.83.199:3030`，内网 `http://1Panel-new-api-4jUC:3000` |
| NewAPI 域名 | `https://newapi.flowguide.cc`，服务器 Caddy 当前反代到 `127.0.0.1:3030` |
| Docker 网络 | TalkWise 自建 `talkwise_talkwise-network`，并接入外部 `1panel-network` |

不要把密钥写入本文档。服务器上的敏感配置只放在 `/opt/talkwise/backend.env`、`/opt/talkwise/.env` 和 1Panel 应用目录的 `.env` 中。

注意：`http://127.0.0.1:18080/` 如果在本机可访问，通常是本地调试进程，例如 `.codex-run\new-api-talkwise-e2e.exe`。它不是服务器上的生产端口，服务器 Caddy 也不能通过 `127.0.0.1:18080` 访问本机服务。要让 `newapi.flowguide.cc` 指向某个 NewAPI 实例，必须先把该实例部署到服务器上，并确认服务器本机可以访问目标端口。

## 日常发布流程

日常发布只需要执行本节。只有首次部署、换服务器、换域名/端口或 NewAPI 密钥时才看后面的初始化章节。

### 1. 本地确认工作区

```powershell
git status --short --branch
```

确认只包含本轮要发布的改动。不要把 `.env`、日志、缓存、虚拟环境、`node_modules`、临时包混入发布包。

### 2. 本地验证

后端：

```powershell
Push-Location backend
$env:NEWAPI_AUTH_ENABLED = "false"
$env:NEWAPI_AUTH_ALLOW_MOCK_FALLBACK = "true"
..\.venv-backend\Scripts\python.exe -m pytest tests
Pop-Location
```

前端：

```powershell
Push-Location frontend
node --test tests\*.mjs
Pop-Location
```

生产前端构建需要写入服务器侧 NewAPI 和 TalkWise 回调地址：

```powershell
Push-Location frontend
$env:VITE_NEWAPI_AUTH_ENABLED = "true"
$env:VITE_NEWAPI_BASE_URL = "http://103.38.83.199:3030"
$env:VITE_NEWAPI_LOGIN_URL = "http://103.38.83.199:3030/login"
$env:VITE_NEWAPI_LOGIN_MODE = "embedded"
$env:VITE_NEWAPI_CONSOLE_URL = "http://103.38.83.199:3030"
$env:VITE_NEWAPI_USAGE_URL = "http://103.38.83.199:3030/usage-logs/common"
$env:VITE_NEWAPI_API_KEYS_URL = "http://103.38.83.199:3030/keys"
$env:VITE_NEWAPI_TALKWISE_CLIENT_ID = "talkwise"
$env:VITE_NEWAPI_TALKWISE_REDIRECT_URI = "https://talkwise.flowguide.cc/login"
npm run build
Pop-Location
```

如果以后更换域名，把上面的 `talkwise.flowguide.cc` 替换为新正式域名，并同步更新 NewAPI 的 `TALKWISE_REDIRECT_URIS`。

### 3. 本地打包

发布包只包含后端运行所需文件和前端 `dist`，不包含测试、虚拟环境、缓存和本地密钥。

```powershell
$Stage = ".codex-run\talkwise-release"
$Archive = ".codex-run\talkwise-deploy-current.tgz"
New-Item -ItemType Directory -Force .codex-run | Out-Null
Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$Stage\backend", "$Stage\frontend" | Out-Null

$backendDirs = @(
  "alembic",
  "api",
  "application",
  "core",
  "domain",
  "grpc_app",
  "infrastructure",
  "locales",
  "scripts",
  "shared",
  "data"
)

foreach ($dir in $backendDirs) {
  robocopy "backend\$dir" "$Stage\backend\$dir" /E /XD __pycache__ .pytest_cache | Out-Null
  if ($LASTEXITCODE -gt 7) { throw "robocopy failed for backend\$dir" }
}

$backendFiles = @(
  "alembic.ini",
  "babel.cfg",
  "grpc_main.py",
  "main.py",
  "pyproject.toml",
  "requirements.txt",
  "uv.lock"
)

foreach ($file in $backendFiles) {
  Copy-Item "backend\$file" "$Stage\backend\$file" -Force
}

Copy-Item README.md "$Stage\backend\README.md" -Force

@'
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gcc g++ libpq-dev git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY . .
RUN uv sync --frozen --no-dev --extra voice

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
'@ | Set-Content -Encoding ascii "$Stage\backend\Dockerfile.deploy"

Copy-Item frontend\dist "$Stage\frontend\dist" -Recurse -Force

Remove-Item $Archive -Force -ErrorAction SilentlyContinue
tar -czf $Archive -C $Stage .
Get-Item $Archive
```

### 4. 上传并切换版本

```powershell
$Server = "lcayun-1panel"
$Archive = ".codex-run\talkwise-deploy-current.tgz"
scp $Archive "${Server}:/opt/talkwise/releases/talkwise-deploy-current.tgz"

$remote = @'
set -euo pipefail
BASE=/opt/talkwise
STAMP=$(date +%Y%m%d-%H%M%S)
RELEASE="$BASE/releases/release-$STAMP"

mkdir -p "$RELEASE"
tar -xzf "$BASE/releases/talkwise-deploy-current.tgz" -C "$RELEASE"
[ -d "$RELEASE/backend" ]
[ -d "$RELEASE/frontend/dist" ]

if [ -d "$BASE/current" ] && [ ! -L "$BASE/current" ]; then
  entries=$(find "$BASE/current" -mindepth 1 -maxdepth 1 | wc -l)
  if [ "$entries" -eq 0 ]; then
    rmdir "$BASE/current"
  else
    mv "$BASE/current" "$BASE/releases/current-dir-backup-$STAMP"
  fi
fi

ln -sfn "$RELEASE" "$BASE/current"
readlink -f "$BASE/current"
'@

$remote | ssh $Server "tr -d '\r' | bash"
```

注意：`/opt/talkwise/current` 必须是符号链接。如果它变成普通目录，`ln -sfn` 可能会把新链接创建到目录里面，导致后续找不到 `current/backend`。

### 5. 构建并启动服务

```powershell
$Server = "lcayun-1panel"

$remote = @'
set -euo pipefail
cd /opt/talkwise

docker compose config --quiet
docker compose build backend
docker compose up -d --force-recreate --no-build backend

for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8012/health; then
    echo
    echo "backend healthy"
    break
  fi
  sleep 5
done

curl -fsS http://127.0.0.1:8012/health >/dev/null
docker compose up -d --force-recreate --no-build frontend
docker compose ps --all
'@

$remote | ssh $Server "tr -d '\r' | bash"
```

只改前端静态资源时，可以跳过 `docker compose build backend` 和后端重建，只切换 `current` 后重建前端容器：

```powershell
ssh lcayun-1panel "cd /opt/talkwise && docker compose up -d --force-recreate --no-build frontend"
```

### 6. 发布验证

从本地访问公网：

```powershell
curl.exe -sS -L -o NUL -w "root=%{http_code} bytes=%{size_download}`n" http://103.38.83.199:8081/
curl.exe -sS -L -o - -w "`nhealth=%{http_code}`n" http://103.38.83.199:8081/health
curl.exe -sS -L -o NUL -w "auth_me=%{http_code}`n" http://103.38.83.199:8081/api/v1/auth/me
curl.exe -sS -L -o NUL -w "domain_root=%{http_code} bytes=%{size_download}`n" https://talkwise.flowguide.cc/
curl.exe -sS -L -o - -w "`ndomain_health=%{http_code}`n" https://talkwise.flowguide.cc/health
curl.exe -sS -L -o NUL -w "domain_auth_me=%{http_code}`n" https://talkwise.flowguide.cc/api/v1/auth/me
curl.exe -sS -L -o NUL -w "newapi_status=%{http_code}`n" http://103.38.83.199:3030/api/status
curl.exe -sS -L -o NUL -w "newapi_domain_status=%{http_code}`n" https://newapi.flowguide.cc/api/status
```

预期结果：

- 首页和域名首页返回 `200`。
- `/health` 和域名 `/health` 返回 `{"status":"alive"}` 和 `200`。
- `/api/v1/auth/me` 和域名 `/api/v1/auth/me` 未登录时返回 `401`，这是正常的鉴权结果。
- NewAPI IP 端口和域名 `/api/status` 都返回 `200`。

从服务器检查容器、端口和迁移版本：

```powershell
$remote = @'
set -euo pipefail
cd /opt/talkwise

echo "containers"
docker compose ps --all

echo "ports"
ss -ltnp | grep -E ':(8081|8012|3030)\b' || true

echo "talkwise tunnel"
systemctl is-active cloudflared-talkwise.service || true
journalctl -u cloudflared-talkwise.service -n 40 --no-pager

echo "backend logs"
docker logs --tail 120 talkwise-backend 2>&1

echo "frontend logs"
docker logs --tail 80 talkwise-frontend 2>&1

echo "db version"
set -a
. /opt/1panel/apps/postgresql/postgresql/.env
set +a
docker exec -e PGPASSWORD="$PANEL_DB_ROOT_PASSWORD" 1Panel-postgresql-LWUC \
  psql -U "$PANEL_DB_ROOT_USER" -d talkwise -tAc 'SELECT version_num FROM alembic_version;'
'@

$remote | ssh lcayun-1panel "tr -d '\r' | bash"
```

当前已验证的 Alembic head 是 `b7f6a3d2c9e1`。

如果怀疑 NewAPI 存在重复实例，优先用下面命令确认运行态。备份目录和旧 Compose 不代表正在运行：

```powershell
ssh lcayun-1panel "docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}' | grep -Ei 'new-api|newapi|oneapi|3030|18080' || true"
ssh lcayun-1panel "ss -ltnp | grep -E ':(3030|18080)\b' || true"
ssh lcayun-1panel "grep -RInE 'newapi\.flowguide\.cc|3030|18080' /etc/caddy /opt/1panel/apps/openresty/openresty/conf 2>/dev/null || true"
```

当前生产判断口径：

- 服务器正在运行的 NewAPI 是 `1Panel-new-api-4jUC`。
- `newapi.flowguide.cc` 和 `http://103.38.83.199:3030` 指向同一个服务器实例。
- 服务器主机当前没有监听 `18080`。
- 本机 `127.0.0.1:18080` 若存在，是本地调试服务，不应作为生产域名的反代目标。

## 回滚

回滚只切换 `/opt/talkwise/current` 到旧 release 并重建容器。注意：如果新版本已经执行了不可逆数据库迁移，代码回滚不等于数据结构回滚；涉及破坏性迁移前必须先单独备份数据库。

```powershell
$Server = "lcayun-1panel"

$remote = @'
set -euo pipefail
BASE=/opt/talkwise
cd "$BASE"

echo "available releases"
ls -1dt "$BASE"/releases/release-* | sed -n '1,10p'

# 手动把这里替换为要回滚到的版本目录。
TARGET=/opt/talkwise/releases/release-YYYYMMDD-HHMMSS
[ -d "$TARGET/backend" ]
[ -d "$TARGET/frontend/dist" ]

ln -sfn "$TARGET" "$BASE/current"
docker compose build backend
docker compose up -d --force-recreate --no-build backend
curl -fsS http://127.0.0.1:8012/health
docker compose up -d --force-recreate --no-build frontend
docker compose ps --all
'@

$remote | ssh $Server "tr -d '\r' | bash"
```

## 首次服务器初始化

当前服务器已经完成本节初始化。换服务器或从零恢复时再执行。

### 1. 服务器基础检查

```bash
docker --version
docker compose version
docker network ls
docker ps --format '{{.Names}}'
systemctl status 1panel-core --no-pager
systemctl status 1panel-agent --no-pager
```

必须存在：

- `1panel-network`
- `1Panel-postgresql-LWUC`
- `1Panel-new-api-4jUC`

### 2. 创建目录

```bash
mkdir -p /opt/talkwise/releases /opt/talkwise/storage /opt/talkwise/logs
chmod 700 /opt/talkwise
```

### 3. 创建 TalkWise 数据库

```bash
set -euo pipefail
set -a
. /opt/1panel/apps/postgresql/postgresql/.env
set +a

TW_DB_USER=talkwise
TW_DB_NAME=talkwise
TW_DB_PASSWORD='<generate-a-strong-password>'

export PGPASSWORD="$PANEL_DB_ROOT_PASSWORD"
docker exec -e PGPASSWORD="$PANEL_DB_ROOT_PASSWORD" 1Panel-postgresql-LWUC \
  psql -U "$PANEL_DB_ROOT_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "CREATE ROLE $TW_DB_USER LOGIN PASSWORD '$TW_DB_PASSWORD';"

docker exec -e PGPASSWORD="$PANEL_DB_ROOT_PASSWORD" 1Panel-postgresql-LWUC \
  createdb -U "$PANEL_DB_ROOT_USER" -O "$TW_DB_USER" "$TW_DB_NAME"

docker exec -e PGPASSWORD="$PANEL_DB_ROOT_PASSWORD" 1Panel-postgresql-LWUC \
  psql -U "$PANEL_DB_ROOT_USER" -d "$TW_DB_NAME" -v ON_ERROR_STOP=1 \
  -c "GRANT ALL PRIVILEGES ON DATABASE $TW_DB_NAME TO $TW_DB_USER;"
```

如果数据库或角色已经存在，改用 `ALTER ROLE talkwise WITH PASSWORD '<password>';`，不要删除现有数据库。

### 4. 准备环境文件

`/opt/talkwise/.env` 只放 Compose 变量：

```bash
cat > /opt/talkwise/.env <<'EOF'
TALKWISE_BACKEND_PORT=8012
TALKWISE_FRONTEND_PORT=8081
TALKWISE_PUBLIC_BASE_URL=https://talkwise.flowguide.cc
EOF
chmod 600 /opt/talkwise/.env
```

`/opt/talkwise/backend.env` 只放后端运行时真正会读取的配置。不要把 `TW_DB_PASSWORD`、`TALKWISE_FRONTEND_PORT` 这类辅助变量放进 `backend.env`。

```bash
cat > /opt/talkwise/backend.env <<'EOF'
PROJECT_NAME=TalkWise
VERSION=1.0.0
DEBUG=false
ENVIRONMENT=staging
AUTO_RUN_MIGRATIONS=true
HOST=0.0.0.0
PORT=8000
RELOAD=false
WORKERS=1
SECRET_KEY=<generate-a-strong-secret>
DATABASE__URL=postgresql+asyncpg://talkwise:<db-password>@1Panel-postgresql-LWUC:5432/talkwise
CORS_ORIGINS=["https://talkwise.flowguide.cc","http://103.38.83.199:8081","http://127.0.0.1:8081","http://localhost:8081"]
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=["*"]
CORS_ALLOW_HEADERS=["*"]
NEWAPI_BASE_URL=http://1Panel-new-api-4jUC:3000
NEWAPI_GATEWAY_BASE_URL=http://1Panel-new-api-4jUC:3000/v1
NEWAPI_ACCESS_TOKEN=<newapi-service-token>
NEWAPI_AUTH_ENABLED=true
NEWAPI_AUTH_ALLOW_MOCK_FALLBACK=false
NEWAPI_AUTH_TIMEOUT_SECONDS=5
NEWAPI_TALKWISE_CLIENT_ID=talkwise
NEWAPI_TALKWISE_CLIENT_SECRET=<newapi-talkwise-client-secret>
NEWAPI_TALKWISE_AUTH_EXCHANGE_PATH=/api/talkwise/auth/exchange
NEWAPI_TALKWISE_REDIRECT_URI=https://talkwise.flowguide.cc/login
TALKWISE_SESSION_COOKIE_NAME=talkwise_session
TALKWISE_SESSION_TTL_SECONDS=28800
OPENAI_COMPATIBLE_API_KEY=<newapi-service-token>
OPENAI_COMPATIBLE_BASE_URL=http://1Panel-new-api-4jUC:3000/v1
OPENAI_COMPATIBLE_MODEL=gpt-4o-mini
OPENAI_COMPATIBLE_WIRE_API=chat_completions
LLM__PROVIDER=openai
LLM__API_KEY=<newapi-service-token>
LLM__BASE_URL=http://1Panel-new-api-4jUC:3000/v1
LLM__WIRE_API=chat_completions
LLM__DEFAULT_MODEL=gpt-4o-mini
LLM__USER_AGENT=TalkTrainingStudio/1.0
REALTIME_PROVIDER=openai
REALTIME_API_KEY=<newapi-service-token>
REALTIME_BASE_URL=http://1Panel-new-api-4jUC:3000/v1/realtime/calls
REALTIME_OPENAI_API_KEY=<newapi-service-token>
REALTIME_OPENAI_MODEL=gpt-realtime-2.1
REALTIME_OPENAI_VOICE=marin
REALTIME_OPENAI_TRANSCRIPTION_MODEL=gpt-realtime-whisper
STORAGE__TYPE=local
STORAGE__LOCAL_BASE_PATH=/app/storage
UPLOAD_DIR=/app/storage/uploads
LOG_LEVEL=INFO
LOG_REQUEST_BODY_ENABLE_BY_DEFAULT=false
CLIENT_EVENT_LOGGING_ENABLED=true
CLIENT_EVENT_LOGGING_MAX_PAYLOAD_BYTES=4096
METRICS__ENABLED=false
TRACING__ENABLED=false
HEALTH__INCLUDE_DETAILS=false
EOF
chmod 600 /opt/talkwise/backend.env
```

推荐在 NewAPI 控制台创建 TalkWise 专用 token。若临时需要从 NewAPI SQLite 查询现有 token，只列出候选，不要把结果写进文档或终端共享记录：

```bash
NEWAPI_DB=/opt/1panel/apps/new-api/new-api/data/one-api.db
docker run --rm -v "$NEWAPI_DB:/data/one-api.db:ro" nouchka/sqlite3 /data/one-api.db \
  "SELECT id,name,status FROM tokens WHERE deleted_at IS NULL ORDER BY id;"
```

### 5. NewAPI 回调地址

NewAPI 的 `TALKWISE_REDIRECT_URIS` 至少包含：

```text
https://talkwise.flowguide.cc/login
http://103.38.83.199:8081/login
http://localhost:5177/login
http://127.0.0.1:5177/login
```

如果正式更换域名，同时更新：

- NewAPI `TALKWISE_REDIRECT_URIS`
- TalkWise `NEWAPI_TALKWISE_REDIRECT_URI`
- 前端构建变量 `VITE_NEWAPI_TALKWISE_REDIRECT_URI`
- CORS `CORS_ORIGINS`

### 6. Dockerfile

日常打包步骤会把 `Dockerfile.deploy` 写入每个 release。首次手工恢复时，也可以在 `/opt/talkwise/current/backend/Dockerfile.deploy` 写入同样内容：

```dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gcc g++ libpq-dev git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY . .
RUN uv sync --frozen --no-dev --extra voice

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

这里使用 `uv sync --frozen`，避免 `--locked` 在构建时因为 lockfile 新鲜度检查要求重写 `uv.lock`。

### 7. Nginx 配置

在 `/opt/talkwise/nginx.conf` 写入：

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;
    client_max_body_size 100m;

    location /api/ {
        proxy_pass http://talkwise-backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location /health {
        proxy_pass http://talkwise-backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 8. Docker Compose

在 `/opt/talkwise/docker-compose.yml` 写入：

```yaml
services:
  backend:
    container_name: talkwise-backend
    build:
      context: ./current/backend
      dockerfile: Dockerfile.deploy
    env_file:
      - ./backend.env
    restart: unless-stopped
    ports:
      - "127.0.0.1:${TALKWISE_BACKEND_PORT:-8012}:8000"
    volumes:
      - ./storage:/app/storage
      - ./logs:/app/logs
    networks:
      - talkwise-network
      - 1panel-network
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 90s

  frontend:
    container_name: talkwise-frontend
    image: nginx:1.27-alpine
    restart: unless-stopped
    depends_on:
      backend:
        condition: service_healthy
    ports:
      - "0.0.0.0:${TALKWISE_FRONTEND_PORT:-8081}:80"
    volumes:
      - ./current/frontend/dist:/usr/share/nginx/html:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    networks:
      - talkwise-network

networks:
  talkwise-network:
    driver: bridge
  1panel-network:
    external: true
```

### 9. 当前：用 Cloudflare Tunnel 暴露 TalkWise 域名

当前 `talkwise.flowguide.cc` 使用 Cloudflare Tunnel，而不是服务器 Caddy 站点：

```text
talkwise.flowguide.cc
  -> Cloudflare Tunnel talkwise-main-app
  -> 服务器 cloudflared-talkwise.service
  -> http://127.0.0.1:8081
  -> talkwise-frontend
```

本机已有 Cloudflare origin cert 时，可用官方 CLI 检查：

```powershell
cloudflared tunnel info ac33cb04-ebc8-46a4-9344-2f5d7f05a988
Resolve-DnsName talkwise.flowguide.cc -Server 1.1.1.1
curl.exe -sS -L -o NUL -w "domain_root=%{http_code}`n" https://talkwise.flowguide.cc/
```

服务器检查：

```bash
systemctl status cloudflared-talkwise.service --no-pager
journalctl -u cloudflared-talkwise.service -n 80 --no-pager
curl -fsS http://127.0.0.1:8081/ >/dev/null
```

如需重建该 tunnel，先用 `cloudflared tunnel route dns --overwrite-dns <new-tunnel-id> talkwise.flowguide.cc` 覆盖 DNS，再把新 tunnel 凭据、`/etc/cloudflared/talkwise.yml` 和 `cloudflared-talkwise.service` 安装到服务器。

### 10. 可选：用 Caddy 暴露 80/443

当前生产使用 Cloudflare Tunnel。若以后改回普通 DNS A 记录和 Caddy，则在 Cloudflare 把域名 A 记录指向 `103.38.83.199`，并把 Caddy 反代到 `127.0.0.1:8081`：

```caddyfile
talkwise.flowguide.cc {
    reverse_proxy 127.0.0.1:8081
}
```

然后把所有 `talkwise.flowguide.cc` 配置替换为新的正式域名或保留原域名。

## 常见故障

### `current/backend/Dockerfile.deploy: No such file or directory`

检查 `/opt/talkwise/current` 是否是普通目录而不是符号链接：

```bash
ls -la /opt/talkwise /opt/talkwise/current
readlink -f /opt/talkwise/current
```

修复：

```bash
BASE=/opt/talkwise
TARGET=/opt/talkwise/releases/release-YYYYMMDD-HHMMSS

if [ -d "$BASE/current" ] && [ ! -L "$BASE/current" ]; then
  entries=$(find "$BASE/current" -mindepth 1 -maxdepth 1 | wc -l)
  if [ "$entries" -eq 0 ]; then
    rmdir "$BASE/current"
  else
    mv "$BASE/current" "$BASE/releases/current-dir-backup-$(date +%Y%m%d-%H%M%S)"
  fi
fi

ln -sfn "$TARGET" "$BASE/current"
```

### `uv.lock needs to be updated, but --locked was provided`

Dockerfile 中使用：

```dockerfile
RUN uv sync --frozen --no-dev --extra voice
```

不要在服务器部署时临时运行 `uv lock` 改写锁文件。

### Alembic PostgreSQL 标识符超过 63 字符

如果日志出现：

```text
Identifier 'fk_stakeholder_competency_evaluations_room_id_stakeholder_chat_rooms' exceeds maximum length of 63 characters
```

确认本地和发布包中包含 `backend/alembic/versions/20260414_1649-c81263f68d3d_competency_eval_room_id_set_null.py` 的 PostgreSQL 分支修复。不要用 `alembic stamp head` 跳过迁移。

### 后端启动后只有 401

`/api/v1/auth/me` 未登录返回 `401` 是正常的。判断服务是否正常看：

```bash
curl -fsS http://127.0.0.1:8012/health
curl -i http://127.0.0.1:8012/api/v1/auth/me
```

### `127.0.0.1:18080` 和 NewAPI 域名内容不一致

先判断 `18080` 是在哪台机器上监听。

服务器上检查：

```bash
ss -ltnp | grep -E ':18080\b' || true
curl -I --max-time 5 http://127.0.0.1:18080/
```

Windows 本机检查：

```powershell
Get-NetTCPConnection -LocalPort 18080 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,State,OwningProcess
Get-CimInstance Win32_Process -Filter "ProcessId=<OwningProcess>" |
  Select-Object ProcessId,Name,ExecutablePath,CommandLine
```

如果进程来自 `.codex-run\new-api-talkwise-e2e.exe`，这是本地 E2E 调试实例。不要把服务器 Caddy 改成 `reverse_proxy 127.0.0.1:18080`，因为服务器上的 `127.0.0.1` 指服务器自己，不是开发机。正确做法是把要上线的 NewAPI 构建部署到服务器的 1Panel NewAPI 容器，再让 Caddy 继续指向服务器上的 `127.0.0.1:3030`，或改到另一个服务器可访问的端口。

### Nginx 日志提示 read-only config

如果看到：

```text
10-listen-on-ipv6-by-default.sh: info: can not modify /etc/nginx/conf.d/default.conf (read-only file system?)
```

这是官方 Nginx 镜像启动脚本尝试修改只读挂载配置导致的信息，不影响服务。

## 发布完成记录模板

每次发布结束，把结果记录在 PR、提交说明或运维记录中：

```text
Release:
- local git ref:
- release dir:
- frontend build env:
- backend image:
- Alembic version:
- public checks:
  - /:
  - /health:
  - /api/v1/auth/me:
- rollback target:
- known warnings:
```
