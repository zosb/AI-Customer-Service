# Backend

FastAPI 后端负责认证、MySQL 业务数据、知识库上传与解析、Embedding、Chroma 检索、RAG Prompt、Ollama Chat、SSE、来源追踪、反馈、管理后台与 Agent Planner。

## 环境

- Python 3.11
- MySQL 8
- Ollama

## 安装

```cmd
cd backend
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

## 配置

后端读取**项目根目录** `.env`：

```cmd
copy ..\.env.example ..\.env
```

至少配置 `MYSQL_PASSWORD` 与 `JWT_SECRET_KEY`。`MYSQL_PASSWORD` 请使用至少 12 位 ASCII 强密码，并同时包含大写字母、小写字母、数字和英文特殊符号。

本项目运行时使用本地 Ollama，因此**不需要第三方 LLM API Key**。如未来替换为云端模型，应通过环境变量注入 API Key，禁止硬编码或提交真实 Key。

## Ollama 运行预检

下载模型后执行：

```cmd
python scripts\check_ollama.py
```

该脚本会检查 Ollama 服务、两个必需模型，并实际调用一次 1024 维 Embedding 和一次 Chat 生成。

## 数据库

```cmd
python scripts\bootstrap_mysql.py
python -m alembic upgrade head
```

审阅用 SQL 快照位于 `database/schema.sql`，初始数据位于 `database/seed.sql`；迁移维护以 `alembic/versions/` 为准。

## 启动

```cmd
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- Swagger：`http://127.0.0.1:8000/docs`
- Health：`http://127.0.0.1:8000/api/v1/health`

## 测试

```cmd
python -m pytest -q
```

`tests/unit/` 覆盖核心业务逻辑，`tests/integration/` 覆盖 FastAPI/API 组合行为。

## 目录职责

- `app/api/`：REST/SSE 路由与依赖注入
- `app/core/`：配置、安全
- `app/db/`：SQLAlchemy 会话与 URL
- `app/models/`：ORM 模型
- `app/repositories/`：MySQL 数据访问
- `app/services/knowledge/`：解析、切块、Embedding、检索、知识库生命周期
- `app/services/chat/`：会话、RAG 与 SSE 编排
- `app/services/rag/`：上下文治理与回答证据校验
- `app/services/llm/`：Ollama Chat/Embedding 与重试
- `app/services/agent/`：任务拆解、DAG 与资源安全
- `database/`：审阅用建表/初始化 SQL
- `storage/`：运行时数据目录，实际内容被 Git 忽略
