# Legacy Stakeholder Chat Frontend (Migration Reference)

React + TypeScript + Vite frontend retained only as a migration reference and rollback source.
The default local host is `outside-project/new-api-main/web` (Rsbuild); run
`start-dev.cmd -LegacyViteFrontend` only when validating the legacy fallback.

## 开发

```powershell
..\start-dev.cmd  # 推荐：从仓库根目录同步前后端 env 并启动完整开发环境
npm run build   # 生产构建
```

直接调试前端时可以运行 `npm run dev`，但要确保 `.env` 中的 `VITE_API_URL` 指向正在运行的后端。仓库默认本地后端为 `http://127.0.0.1:8012`。

## 配置

- `.env` 中 `VITE_API_URL` 设置后端地址；`start-dev.cmd` 会自动写入
- `vite.config.ts` 将 `/api` 和 `/health` 请求代理到后端，便于本地健康检查
