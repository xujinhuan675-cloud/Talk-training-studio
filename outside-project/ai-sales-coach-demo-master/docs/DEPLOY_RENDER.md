# Render Deployment

## 准备

1. 将项目推到 GitHub。
2. 准备 DashScope Qwen API Key。
3. 在 Render 创建新的 Web Service，连接该 GitHub 仓库。
4. 选择 Docker 部署，Render 会使用仓库根目录的 `Dockerfile`。

## Environment Variables

| Key | Value |
|---|---|
| `QWEN_API_KEY` | 你的 DashScope API Key |
| `AI_MODE` | `real` |
| `AI_DAILY_LIMIT_PER_USER` | `30` |
| `AI_DAILY_LIMIT_PER_IP` | `80` |
| `AUTO_SEED_DEMO` | `1` |

Render 会自动提供 `PORT`，不需要手动设置。

## Verify

部署成功后检查：

1. `https://your-service.onrender.com/health` 返回 `{"status":"ok"}`。
2. 打开首页，使用 `admin / admin123` 登录。
3. 使用 `user1 / user123` 完成一次 AI 对话。
4. 打开 `/m` 验证移动端登录和训练入口。

## Notes

- 免费服务可能冷启动，首次访问会慢一些。
- SQLite 数据用于 demo。免费环境重启后可能重新初始化演示数据，这是可接受的作品集行为。
- 公开 demo 使用真实 AI，务必配置限流环境变量，避免 API Key 被刷。
