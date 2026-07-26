# TalkWise x NewAPI 控制面 Handoff

## 目标边界

TalkWise 保留训练产品核心：训练工作台、场景/persona/org 配置、对话、复盘、成长和训练数据访问控制。NewAPI 作为外部生产控制面提供账号、登录态、API Keys、余额/用量、订阅、模型/渠道和 OpenAI-compatible `/v1` gateway。

不要把 NewAPI 源码混入 TalkWise 前后端业务目录。托管 NewAPI 时只维护 env、反代和 adapter；自托管 NewAPI 时应作为独立服务、compose profile 或 submodule/fork 交付。

## 当前实现

TalkWise 已有两条 NewAPI 登录桥接路径：

- `POST /api/v1/auth/newapi/session`：兼容开发/诊断场景，用浏览器提交的 NewAPI dashboard Bearer token 调 `/api/user/self`，验证后写 TalkWise HttpOnly signed cookie。
- `POST /api/v1/auth/newapi/exchange`：生产 handoff 入口，接受 NewAPI 一次性 `code`，由 TalkWise 后端调用 `NEWAPI_TALKWISE_AUTH_EXCHANGE_PATH` 换用户声明，再写 TalkWise HttpOnly signed cookie。

前端登录页和 auth service 会优先消费 URL 中的 `talkwise_code` / `code`，并清理地址栏中的 code/token 参数；只有没有 code 时才回退到旧的 URL token 或同源 NewAPI localStorage token。NewAPI auth 开启时，用户菜单隐藏 mock 用户切换，并提供 NewAPI 控制台、API Keys、用量入口。

## NewAPI 侧建议扩展

NewAPI 已有 `model.AuthFlow`、`service/auth_session.go`、dashboard JWT/session、subscription、quota、token 和 relay 结算路径。TalkWise handoff 不应直接写 NewAPI 的 JWT、refresh cookie、`users.access_token`、quota 或 token 表。

推荐新增很薄的 NewAPI endpoint：

```text
POST /api/talkwise/auth/exchange
```

输入：

```json
{
  "client_id": "talkwise",
  "client_secret": "optional-server-secret",
  "code": "one-time-auth-flow-token",
  "redirect_uri": "https://app.example.com/login"
}
```

输出保持 NewAPI 现有 envelope 风格：

```json
{
  "success": true,
  "data": {
    "user": {
      "id": 42,
      "username": "alice",
      "display_name": "Alice",
      "role": 10,
      "status": 1,
      "group": "default"
    },
    "team": {
      "id": "team-acme",
      "name": "Acme Revenue"
    },
    "subscription": {
      "plan": "enterprise",
      "status": "active"
    },
    "gateway": {
      "base_url": "https://gateway.example.com/v1"
    },
    "quota": 900,
    "used_quota": 100,
    "request_count": 7
  }
}
```

内部应复用 AuthFlow 短 TTL、一次性消费、现有 session/user/subscription/quota 读取逻辑，并走 NewAPI 审计日志。TalkWise adapter 已兼容 `data.user`、`data.team`、`data.subscription`、`data.gateway` 以及旧 `/api/user/self` 平铺字段。

## 部署拓扑

反代子路径：

```text
/             -> TalkWise frontend
/api/*        -> TalkWise backend
/health/*     -> TalkWise backend
/console/*    -> NewAPI dashboard
/v1/*         -> NewAPI OpenAI-compatible gateway
```

如果 NewAPI 不适合挂子路径，用子域名：

```text
app.example.com          -> TalkWise
console.example.com      -> NewAPI dashboard
gateway.example.com/v1   -> NewAPI gateway
```

关键 env：

- Backend: `NEWAPI_BASE_URL`, `NEWAPI_GATEWAY_BASE_URL`, `NEWAPI_ACCESS_TOKEN`, `NEWAPI_AUTH_ENABLED`, `NEWAPI_TALKWISE_CLIENT_ID`, `NEWAPI_TALKWISE_CLIENT_SECRET`, `NEWAPI_TALKWISE_AUTH_EXCHANGE_PATH`, `NEWAPI_TALKWISE_REDIRECT_URI`
- Frontend: `VITE_NEWAPI_BASE_URL`, `VITE_NEWAPI_LOGIN_URL`, `VITE_NEWAPI_LOGIN_MODE`, `VITE_NEWAPI_CONSOLE_URL`, `VITE_NEWAPI_USAGE_URL`, `VITE_NEWAPI_API_KEYS_URL`, `VITE_NEWAPI_TALKWISE_CLIENT_ID`, `VITE_NEWAPI_TALKWISE_REDIRECT_URI`

## 剩余生产风险

- TalkWise session 仍是自包含 signed cookie，NewAPI 禁用/降权后会在 TTL 内继续有效。下一步应改 opaque session id + Redis/DB session store，并增加定期 claim refresh/revoke。
- LLM/voice/realtime 当前主要使用服务端静态 NewAPI gateway token，还没有逐 TalkWise 用户做模型权限、余额预检和用量提交。优先路线是训练模型调用走 NewAPI `/v1` relay，并在请求 metadata 中带 `source=talkwise`、`training_session_id`、`app_request_id`。
- `group -> team_id` 只保留为兜底。生产应由 NewAPI handoff 返回显式 `team.id/team.name`，不要把 NewAPI 模型组误当 TalkWise 租户。
- `NEWAPI_AUTH_ENABLED=false` 会保留本地 mock default admin；生产环境必须启用真实 NewAPI auth，并禁用 mock fallback。
- NewAPI callback URL 中的 code/token 已在 TalkWise 日志中脱敏，但反代、NewAPI 自身和浏览器 referer policy 仍需同步配置。
