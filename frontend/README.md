# Frontend

Vue 3 + TypeScript 前端，提供登录注册、AI 客服会话、SSE 流式回答、知识来源、反馈、知识库管理、运营后台和 Agent Planner 页面。

运行时要求 Node.js `^22.22.2`、`^24.15.0` 或 `>=26.0.0`；推荐使用 Node 24.15+。

## 安装

```cmd
cd frontend
npm ci
```

## 配置

复制可选的前端环境配置：

```cmd
copy .env.example .env.local
```

默认：

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 开发启动

```cmd
npm run dev -- --host 127.0.0.1
```

访问 `http://127.0.0.1:5173`。

## 质量检查

```cmd
npm run type-check
npm run test:unit -- --run
npm run lint
npm run build
```

## 页面

- `/`：智能客服工作台
- `/login`：登录
- `/register`：注册
- `/knowledge`：知识库管理
- `/admin`：运营管理后台
- `/admin/agent`：AI Agent Planner

LLM、Embedding 和向量检索均由后端完成；前端只调用 FastAPI。
