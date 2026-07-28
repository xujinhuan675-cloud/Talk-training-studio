# TalkWise NewAPI 项目界面操作手册

本文档记录 TalkWise 生产环境中 NewAPI 控制台和项目界面配置的可复用操作方式。适用于后续通过 NewAPI 后台接口、当前浏览器登录态、或服务器内网接口完成用户、模型、渠道、回调和界面配置。

## 当前入口

| 项目 | 地址或标识 |
|:---|:---|
| TalkWise 主应用 | `https://talkwise.flowguide.cc/` |
| TalkWise 直连地址 | `http://103.38.83.199:8081/` |
| NewAPI 控制台 | `https://newapi.flowguide.cc/` |
| NewAPI 用户管理页 | `https://newapi.flowguide.cc/users` |
| NewAPI 容器 | `1Panel-new-api-4jUC` |
| NewAPI 容器内地址 | `http://1Panel-new-api-4jUC:3000` |
| NewAPI 服务器内网地址 | `http://127.0.0.1:3030` |
| NewAPI 数据库 | `/opt/1panel/apps/new-api/new-api/data/one-api.db` |
| Feishu Base 入口 | `https://ccnainrpixz2.feishu.cn/base/Lqw4bc6LbamtSzsrU15czIAHnPh?table=tblppC1VHMGCjgzL&view=vewoTegjwx` |

敏感信息只留在服务器环境文件、NewAPI 数据库或浏览器登录态中，不写入本文档、飞书文档、终端共享记录或提交说明。

## 操作原则

1. 优先调用 NewAPI 自身后台接口，不直接改数据库。
2. 如果接口因历史脏数据无法处理单条异常记录，再做最小数据库修正，并记录原因。
3. 批量操作前先冻结目标集合，避免分页移动导致误操作。
4. 保留 `flowguide` root 用户，判断口径为 `username=flowguide`、`role=100`。
5. API 路径以后以当前前端静态资源为准；先查资源或网络请求，再调用接口。
6. 不打印 `access_token`、NewAPI service token、client secret、数据库密码。

## 已验证的用户管理接口

前端资源：

```text
https://newapi.flowguide.cc/static/js/index.40cfea2544.js
```

已验证 API：

```http
GET    /api/user/?p=1&page_size=500
GET    /api/user/search?keyword=&group=&p=1&page_size=30
DELETE /api/user/{id}
```

注意：

- 删除接口使用无尾斜杠：`DELETE /api/user/{id}`。
- `DELETE /api/user/{id}/` 会返回 `307`，Python `urllib` 默认不会用 `DELETE` 继续跟随。
- root 用户 token 用于服务器内网管理调用时，使用 `Authorization: Bearer <root-access-token>`；实际 token 不得输出。

## 服务器侧接口调用模板

下面模板从 NewAPI SQLite 中读取 root 用户 access token，然后调用服务器内网 NewAPI API。脚本不打印 token。

```bash
python3 - <<'PY'
import json
import sqlite3
import urllib.request
import urllib.error

DB = "/opt/1panel/apps/new-api/new-api/data/one-api.db"
BASE = "http://127.0.0.1:3030"

con = sqlite3.connect(DB)
row = con.execute(
    "SELECT id, access_token FROM users WHERE username='flowguide' AND role=100 AND deleted_at IS NULL"
).fetchone()
if not row:
    raise SystemExit("flowguide root user not found")

root_id, token = row

def request_json(method, path):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = {"raw": body[:500]}
        return exc.code, parsed

status, payload = request_json("GET", "/api/user/?p=1&page_size=500")
print(status, payload.get("success") if isinstance(payload, dict) else None)
PY
```

## 批量删除非 root 用户流程

适用场景：清理 NewAPI 用户表，只保留 `flowguide` root 用户。

1. 通过接口列出用户：

```http
GET /api/user/?p=1&page_size=500
```

2. 冻结目标集合：

```text
targets = users where username != "flowguide"
```

3. 对每个目标调用：

```http
DELETE /api/user/{id}
```

4. 再次验证：

```http
GET /api/user/?p=1&page_size=500
```

预期只返回：

```json
[
  {"id": 1, "username": "flowguide", "role": 100, "status": 1}
]
```

## 本轮执行记录：2026-07-28

用户目标：删除 `https://newapi.flowguide.cc/users` 中除 `flowguide` root 用户外的所有用户。

执行结果：

- 通过前端静态资源确认用户删除接口为 `DELETE /api/user/{id}`。
- 使用服务器内网地址 `http://127.0.0.1:3030` 调用 NewAPI 后台 API。
- 保留 root 用户：`id=1`、`username=flowguide`、`role=100`。
- 通过接口删除 19 个普通用户。
- `id=23`、`username=sunny3724` 是历史异常残留：数据库已有 `deleted_at`，删除接口返回 `record not found`，但用户列表仍返回该记录。
- 对 `sunny3724` 执行最小硬删除。
- 最终 API 和数据库均只剩 `flowguide` root 用户。

验证输出摘要：

```text
API_REMAINING_COUNT 1
API_REMAINING [{"id": 1, "username": "flowguide", "role": 100, "status": 1}]
DB_REMAINING [{"id": 1, "username": "flowguide", "role": 100, "status": 1, "deleted_at": null}]
```

## 后续项目界面配置流程

后续如果需要通过接口配置 NewAPI 项目界面，例如模型、渠道、导航、订阅、用户权限或 TalkWise handoff：

1. 在浏览器打开对应后台页面，确认当前 UI 操作入口。
2. 从当前前端资源或浏览器网络请求中定位 API：

```powershell
$html = curl.exe -sS -L https://newapi.flowguide.cc/<page>
$html | Select-String -Pattern 'src="[^"]+\.js' -AllMatches
curl.exe -sS -L https://newapi.flowguide.cc/static/js/<asset>.js |
  Select-String -Pattern '/api/[^"` ]+' -AllMatches
```

3. 确认接口方法、路径、参数和返回 envelope。
4. 优先用当前浏览器登录态或服务器 root 管理 token 调接口。
5. 批量修改前冻结目标集合。
6. 修改后用后台页面和 API 双重验证。
7. 把稳定接口补充到本文档。

## 相关文档

- [服务器部署操作手册](server-deployment-runbook.md)
- [TalkWise x NewAPI 控制面 Handoff](../plans/2026-07-25-newapi-control-plane-handoff.md)
