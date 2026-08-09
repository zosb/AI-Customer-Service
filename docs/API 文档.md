# API 文档

统一前缀：`/api/v1`。除注册、登录和健康检查外，业务接口使用：

```http
Authorization: Bearer <access_token>
```

Swagger：`http://127.0.0.1:8000/docs`。

## 1. 完整接口列表

### 健康与认证

| Method | Path | 说明 |
|---|---|---|
| GET | `/health` | 后端健康检查 |
| POST | `/auth/register` | 邮箱或手机号注册 |
| POST | `/auth/login` | 登录并获取 JWT |
| GET | `/auth/me` | 当前用户 |

### 知识库

| Method | Path | 说明 |
|---|---|---|
| GET | `/knowledge/bases` | 知识库列表 |
| POST | `/knowledge/bases` | 创建知识库 |
| PATCH | `/knowledge/bases/{knowledge_base_id}` | 编辑/启停知识库 |
| DELETE | `/knowledge/bases/{knowledge_base_id}` | 删除知识库并级联清理文档、向量、上传文件 |
| POST | `/knowledge/documents` | 上传并向量化文档（multipart） |
| GET | `/knowledge/documents` | 文档列表 |
| DELETE | `/knowledge/documents/{document_id}` | 删除文档并清除向量 |

### 会话、问答与反馈

| Method | Path | 说明 |
|---|---|---|
| POST | `/chat/sessions` | 创建独立会话 |
| GET | `/chat/sessions` | 当前用户会话列表 |
| GET | `/chat/sessions/{session_id}` | 会话详情 |
| PATCH | `/chat/sessions/{session_id}` | 修改标题/绑定知识库 |
| DELETE | `/chat/sessions/{session_id}` | 归档会话 |
| POST | `/chat/sessions/{session_id}/restore` | 恢复会话 |
| GET | `/chat/sessions/{session_id}/messages` | 完整消息历史 |
| POST | `/chat/sessions/{session_id}/messages` | **SSE 流式问答** |
| GET | `/chat/messages/{message_id}/sources` | AI 消息来源 |
| GET | `/chat/sessions/{session_id}/feedback` | 会话反馈 |
| PUT | `/chat/messages/{message_id}/feedback` | 提交/更新点赞踩及文字反馈 |
| DELETE | `/chat/messages/{message_id}/feedback` | 撤销反馈 |

### 管理后台（管理员）

| Method | Path | 说明 |
|---|---|---|
| GET | `/admin/overview` | 总览指标 |
| GET | `/admin/sessions` | 全量会话 |
| GET | `/admin/sessions/{session_id}` | 任意会话完整记录 |
| GET | `/admin/feedback/summary` | 反馈统计 |
| GET | `/admin/feedback` | 反馈明细 |
| GET | `/admin/analytics/daily-questions` | 日均问答趋势 |

### Agent（管理员）

| Method | Path | 说明 |
|---|---|---|
| POST | `/agent/plans` | 需求拆解、DAG 与安全并行计划 |

## 2. 注册示例

请求：

```http
POST /api/v1/auth/register
Content-Type: application/json
```

```json
{
  "account": "user@example.com",
  "password": "StrongPass1!",
  "display_name": "Demo User"
}
```

响应 `201`：

```json
{
  "id": 1,
  "email": "user@example.com",
  "phone": null,
  "display_name": "Demo User",
  "role": "user",
  "status": "active",
  "created_at": "2026-08-09T03:00:00"
}
```

## 3. 登录示例

```json
{
  "account": "user@example.com",
  "password": "StrongPass1!"
}
```

响应：

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 7200,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "phone": null,
    "display_name": "Demo User",
    "role": "user",
    "status": "active",
    "created_at": "2026-08-09T03:00:00"
  }
}
```

## 4. 上传文档示例

```http
POST /api/v1/knowledge/documents
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

Form 字段：

```text
knowledge_base_id=1
priority=5
file=@退款政策.md
```

支持：`.txt`、`.md`、`.pdf`。成功响应包含文档元数据、Embedding 维度和 SHA-256。

## 5. 会话历史示例

```http
GET /api/v1/chat/sessions/12/messages
Authorization: Bearer <token>
```

响应：

```json
{
  "session": {
    "id": 12,
    "user_id": 1,
    "title": "退款咨询",
    "status": "active",
    "selected_knowledge_base_id": null,
    "last_message_at": "2026-08-09T03:10:00",
    "created_at": "2026-08-09T03:09:00",
    "updated_at": "2026-08-09T03:10:00"
  },
  "messages": []
}
```

## 6. SSE 流式问答

请求：

```http
POST /api/v1/chat/sessions/12/messages
Authorization: Bearer <token>
Content-Type: application/json
Accept: text/event-stream
```

```json
{
  "question": "退款一般多久到账？"
}
```

服务端响应类型：

```text
text/event-stream
```

### 6.1 event 格式

每个事件：

```text
event: <event-name>
data: <json>

```

实际事件包括：

#### `meta`

```text
event: meta
data: {"session_id":12,"user_message_id":33,"intent":"refund","daily_question_count":4,"retrieval_status":"matched","routed_knowledge_base_id":2,"route_mode":"auto","route_score":0.81}
```

#### `delta`

逐步返回模型文本，不等待完整回答：

```text
event: delta
data: {"content":"退款"}

event: delta
data: {"content":"通常"}
```

#### `replace`

当流中断需要安全兜底，或最终来源编号清洗/证据修复改变了草稿时，前端用该内容**整体替换**当前草稿：

```text
event: replace
data: {"content":"抱歉，当前知识库中没有找到能够可靠回答该问题的相关信息。"}
```

#### `error`

```text
event: error
data: {"code":"llm_stream_failed","message":"模型流式生成失败"}
```

错误事件后仍会尽量发送安全 fallback 和 `done`，前端不应只依赖 HTTP 状态判断模型阶段异常。

#### `sources`

```text
event: sources
data: {"items":[{"document_name":"退款政策.md","chunk_summary":"...","rank":1,"similarity_score":0.84}]}
```

#### `done`

```text
event: done
data: {"assistant_message_id":34,"content":"... [来源1]","is_fallback":false,"retrieval_status":"matched","follow_up_suggestions":["退款失败怎么办？","如何查询退款状态？"],"source_count":1,"routed_knowledge_base_id":2,"route_mode":"auto","route_score":0.81}
```

## 7. 反馈提交示例

```http
PUT /api/v1/chat/messages/34/feedback
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "rating": 1,
  "comment": "回答准确，来源清晰。"
}
```

`rating=1` 表示点赞，`rating=-1` 表示点踩，`comment` 可为空，最大 1000 字。

## 8. 常见错误

- `401`：Token 缺失、过期或无效。
- `403`：普通用户访问管理员接口或账号被禁用。
- `404`：会话、消息、知识库或文档不存在/不属于当前用户。
- `409`：重复账号、重复知识库等冲突。
- `422`：参数不合法、问题超过 500 字等。
- `429`：达到每日提问上限。
- `500/502`：数据库、Ollama 或其他服务异常。
