# AI 销冠陪练中心

面向门店销售团队的 AI 实战训练平台。管理员配置销售场景和评分维度，销售人员与 AI 客户进行多轮对话，系统自动生成多维评分、复盘建议和团队排行榜。

## 在线体验

**Demo 地址**：[https://ai-sales-coach-demo.onrender.com](https://ai-sales-coach-demo.onrender.com)

> Render 免费版首次访问需等待约 30 秒冷启动。数据库为 SQLite，每次重新部署会重置为演示数据。

### 演示账号

| 角色 | 账号 | 密码 | 可体验功能 |
|---|---|---|---|
| 管理员 | `admin` | `admin123` | 配置销售场景、评分维度、查看全量训练记录 |
| 组长 | `leader1` | `leader123` | 查看团队练习记录、排行榜、薄弱维度分析 |
| 员工 | `user1` | `user123` | 选择场景、完成 AI 陪练对话、查看评分报告 |

移动端地址：[https://ai-sales-coach-demo.onrender.com/#/m](https://ai-sales-coach-demo.onrender.com/#/m)

## 产品背景

传统销售培训存在三个常见问题：

- **练习成本高**：需要占用老员工或主管的时间陪练
- **反馈不及时**：培训结束后才能汇总，难以针对个人薄弱点
- **团队差距难量化**：凭感觉判断谁需要重点培训

本项目将"场景配置 → AI 角色扮演 → 结构化评分 → 团队复盘"串成一个闭环：

1. 管理员沉淀真实业务场景，例如新客推介、续卡挽留、价格异议处理
2. 员工与 AI 扮演的客户进行多轮对话练习
3. AI 按专业度、亲和力、应变力、成交力等维度评分，并引用对话原文给出证据化反馈
4. 组长通过排行榜、未完成名单、团队薄弱维度，用数据安排后续训练重点

## 功能模块

### 员工端
- 场景列表：查看所有训练场景，区分必练/选练
- AI 陪练：与 AI 客户进行多轮对话，支持文字和语音输入
- 评分报告：对话结束后查看维度评分、证据引用和改进建议
- 历史记录：回顾历次训练的评分变化

### 组长端
- 团队排行榜：按综合得分排序，要求完成必练场景后才入榜
- 薄弱维度分析：统计团队在各评分维度的平均分
- 未完成名单：查看哪些员工未完成必练场景

### 管理员端
- 场景管理：配置场景名称、客户画像、难度、开场白、是否必练
- 维度管理：自定义评分维度及各维度权重
- 全量记录：查看所有员工的训练记录和评分详情

## AI 设计说明

**Prompt 分层设计**

客户扮演和评分使用两套独立 Prompt：
- 客户扮演 Prompt 根据难度（1-4 级）控制客户的防御程度，难度越高客户越难缠，用来模拟真实销售场景的挑战梯度
- 评分 Prompt 强制模型输出结构化 JSON，每个维度分数必须附带从对话中引用的原话作为证据，避免只输出抽象评语

**容错设计**

AI 评分失败时有三级降级：
1. 优先修复 JSON 格式错误并重试（最多 3 次）
2. 重试失败则返回占位评分并标记状态，不阻断用户流程
3. 前端轮询评分结果，超时后提示用户手动刷新

**公开 Demo 限流**

为控制 API 调用成本，增加了每用户每日 30 次、每 IP 每日 80 次的限流，支持通过环境变量调整。

## 本地运行

### 环境要求

- Python 3.10+
- Node.js 18+
- 通义千问 DashScope API Key（或使用 mock 模式）

### 后端

```bash
cd backend
pip install -r requirements.txt

# 使用真实 AI
export QWEN_API_KEY=your-api-key
export AI_MODE=real

# 或使用 mock 模式（无需 API Key）
export AI_MODE=mock

python seed_data.py
uvicorn main:app --port 8001 --reload
```

Windows PowerShell：

```powershell
cd backend
python -m pip install -r requirements.txt
$env:QWEN_API_KEY = "your-api-key"
$env:AI_MODE = "real"
python seed_data.py
python -m uvicorn main:app --port 8001 --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:9528`，移动端为 `http://localhost:9528/#/m`。

> 本地开发需同时启动前后端两个服务：后端运行在 8001，前端 dev server 运行在 9528 并自动将 `/api` 请求代理到 8001。访问入口始终是 9528。

## 部署到 Render

项目已包含 `render.yaml`，支持一键部署到 Render 的 Docker Web Service。

详细步骤见 [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md)。

核心环境变量：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `QWEN_API_KEY` | 通义千问 DashScope API Key | 必填 |
| `AI_MODE` | `real` 使用真实 AI，`mock` 使用固定回复 | `real` |
| `AI_DAILY_LIMIT_PER_USER` | 每账号每日 AI 调用上限 | `30` |
| `AI_DAILY_LIMIT_PER_IP` | 每 IP 每日 AI 调用上限 | `80` |
| `AUTO_SEED_DEMO` | 首次启动时自动写入演示数据 | `1` |

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 2, Vue Router, Vuex, Element UI, Vant, ECharts |
| 后端 | FastAPI, aiosqlite, SQLite |
| AI | 通义千问（DashScope OpenAI 兼容接口） |
| 部署 | Docker + Render |

## 文档

- [产品需求文档](docs/PRD.md)
- [演示脚本](docs/DEMO.md)
- [Render 部署说明](docs/DEPLOY_RENDER.md)
