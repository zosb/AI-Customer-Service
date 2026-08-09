# AI 智能客服系统

基于 **FastAPI + Vue 3 + MySQL + Chroma + Ollama** 的企业级本地 AI 客服项目，实现完整 RAG、SSE 流式回答、来源追踪、多轮会话、反馈闭环与知识库管理，并包含多知识库路由、大上下文防幻觉和 AI Agent 任务拆解等扩展能力。

## 核心能力

- 邮箱/手机号注册登录、JWT、管理员权限
- 独立 Session、历史会话与完整消息
- `.txt` / `.md` / `.pdf` 上传、解析、Chunk、Embedding、Chroma
- RAG：检索 → Prompt → Ollama → SSE
- 文档名称 + 片段摘要来源展示
- 500 字问题限制、每日 100 次可配置额度
- 空检索固定兜底，不让模型自由编造
- 最近 N 轮多轮上下文
- 点赞/点踩 + 文字反馈
- 意图识别、追问建议
- 管理后台：会话、反馈、问答趋势
- 多知识库自动路由
- 大上下文 A/B 层证据治理 + AnswerEvidenceGuard
- AI Agent：微服务识别、任务拆解、DAG、资源冲突、安全并行

## 技术栈

- Backend：Python 3.11 / FastAPI / SQLAlchemy 2 / Alembic / PyMySQL
- Frontend：Vue 3 / TypeScript / Pinia / Vue Router / Vite（Node `^22.22.2` / `^24.15.0` / `>=26.0.0`）
- Database：MySQL 8
- Vector DB：Chroma PersistentClient
- LLM：Ollama `qwen3.5:4b`
- Embedding：Ollama `qwen3-embedding:0.6b`（1024 维）
- Streaming：SSE

## 项目结构

```text
AI-Customer-Service/
├─ backend/
│  ├─ app/                  # FastAPI 业务代码
│  ├─ alembic/              # 数据库迁移
│  ├─ database/             # schema.sql + seed.sql + 初始化说明
│  ├─ scripts/              # 数据库/管理员运维脚本
│  ├─ tests/                # 单元与集成测试
│  ├─ storage/              # 运行时目录；实际数据 Git 忽略
│  ├─ requirements.txt
│  └─ README.md
├─ frontend/
│  ├─ src/
│  ├─ package.json
│  ├─ package-lock.json
│  └─ README.md
├─ docs/
│  ├─ API 文档.md
│  ├─ 数据库设计.md
│  ├─ AI 架构设计.md
│  ├─ 业务流程说明.md
│  └─ ...
├─ sample-data/             # RAG 演示知识数据
│  ├─ README.md
│  ├─ 公司产品介绍.txt
│  ├─ 常见问题FAQ.md
│  └─ 退换货政策.txt
├─ .env.example
├─ .gitattributes
├─ .gitignore
├─ 项目说明.md
├─ 运行指南.md
└─ README.md
```

## 快速启动

### 1. 环境变量

```cmd
copy .env.example .env
```

修改 `MYSQL_PASSWORD` 和 `JWT_SECRET_KEY`。

### 2. Ollama

```cmd
ollama pull qwen3.5:4b
ollama pull qwen3-embedding:0.6b
```

### 3. 后端

```cmd
cd backend
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python scripts\check_ollama.py
python scripts\bootstrap_mysql.py
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 4. 前端

```cmd
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

访问：

```text
http://127.0.0.1:5173
```

## 示例知识数据

仓库 `sample-data/` 提供 3 篇演示知识文档，用于快速验证知识库导入与完整 RAG 问答链路：

- `公司产品介绍.txt`
- `常见问题FAQ.md`
- `退换货政策.txt`

启动系统后，可进入 **知识库管理** 页面创建演示知识库并上传上述文档。

上传完成后，后端会自动执行：

```text
文件上传
    ↓
文档解析
    ↓
Chunk 切分
    ↓
qwen3-embedding:0.6b 向量化
    ↓
Chroma 持久化
    ↓
MySQL 元数据记录
    ↓
RAG 检索与问答
```

待文档状态变为“就绪”后，即可进行问答验证。

推荐测试问题：

```text
星河智能耳机 X1 的标准保修期是多久？
X1 曜石黑版本的内部产品代码是什么？
售后客服电话是多少？
购买后 30 天内出现非人为质量问题有什么政策？
退款审核通过后通常多久原路退回？
```

也可使用示例知识中不存在的问题验证空检索与防幻觉机制，例如：

```text
星河智能科技创始人毕业于哪所大学？
```

此类问题在没有可靠知识来源时，系统应返回标准兜底回答，而不是由模型自由编造。

> 示例数据仅用于本项目 RAG 功能演示，不代表真实企业、产品或售后政策。正式应用启动时不会自动写入演示知识数据，避免污染实际知识库。

## 质量检查

```cmd
cd backend
python -m pytest -q

cd ..\frontend
npm run type-check
npm run test:unit -- --run
npm run lint
npm run build
```

## 文档入口

- [项目说明](项目说明.md)
- [运行指南](运行指南.md)
- [API 文档](docs/API%20文档.md)
- [数据库设计](docs/数据库设计.md)
- [AI 架构设计](docs/AI%20架构设计.md)
- [业务流程说明](docs/业务流程说明.md)
- [需求验收矩阵](docs/01-需求验收矩阵.md)
- [大规模知识检索与 LLM 执行保障](docs/大规模知识检索与LLM执行保障.md)
- [AI Agent 任务拆解设计](docs/AI%20Agent任务拆解设计.md)
- [测试与验收](docs/测试与验收.md)
- [示例知识数据](sample-data/README.md)