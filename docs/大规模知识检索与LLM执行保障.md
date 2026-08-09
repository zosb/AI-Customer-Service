# 大规模知识检索与 LLM 执行保障

## 1. 问题

企业知识库变大后，单纯提高 Top-K 会带来：

1. **注意力稀释**：关键强制规则可能被大量普通高相似度内容挤出上下文。
2. **信息过载与幻觉**：重复或相近规则越多，模型越容易混淆、补全不存在的条件。

本项目通过“进入 LLM 前治理 + 生成后校验”处理，而不是只扩大上下文窗口。

## 2. 完整机制

```text
Chroma 候选
→ 近重复去重
→ 单文档 Chunk 限额
→ 关键规则识别
→ A 层规则 / B 层证据
→ 来源数 + 字符预算
→ RAG Prompt
→ Ollama Chat
→ AnswerEvidenceGuard
→ 通过 / 有限修复 / 安全兜底
```

## 3. A/B/C 分层

### A 层：关键规则

- Chunk `priority` 达到关键阈值；或
- 与问题相关并包含“必须、不得、禁止、只能、至少、最多、如果、若、例外”等约束语义。

A 层先于普通证据进入 Prompt，并产生必须覆盖的来源编号。

### B 层：直接回答证据

与问题相关但不属于强制规则的内容，用于解释与补充。

### C 层：本轮裁剪内容

重复、同文档过多、相关性较低或超出预算的材料不进入本轮 Prompt，但仍保留在知识库中。

## 4. 为什么第一层压缩不用 LLM 摘要

当前在线链路优先使用确定性规则句抽取：

- 避免摘要模型先把关键规则总结错；
- 减少额外模型调用延迟；
- 测试结果可重复；
- 关键规则筛选逻辑可精确单测。

未来可对低优先级 C 层做离线摘要，但 A 层规则不应经过有损压缩。

## 5. 预算配置

```env
RAG_MAX_CONTEXT_CHARS=12000
RAG_MAX_SOURCES=8
RAG_MAX_CHUNKS_PER_DOCUMENT=2
RAG_CRITICAL_PRIORITY=5
RAG_CRITICAL_SOURCE_LIMIT=4
RAG_RULE_SENTENCES_PER_SOURCE=3
RAG_SUPPORT_SENTENCES_PER_SOURCE=2
```

## 6. AnswerEvidenceGuard

1. A 层形成 `required_source_ranks`。
2. 第一次生成后检查关键来源是否被覆盖。
3. 遗漏时最多按配置执行受约束修复。
4. 仍遗漏、结果为空或模型失败时返回统一安全兜底。

SSE 已经输出部分草稿时，用 `replace` 事件覆盖，保证浏览器最终文本、MySQL 和来源一致。

## 7. Ollama 执行可靠性

```env
OLLAMA_RETRY_ATTEMPTS=3
OLLAMA_RETRY_BACKOFF_SECONDS=0.25
```

临时连接错误或 HTTP 502/503/504 可有限重试；流式生成只有在尚未向上游输出 token 时重试，避免文本重复。

## 8. 验证方式

自动化测试应覆盖：

- 重复 Chunk 去重；
- 单文档 Chunk 上限；
- 低相似度但高优先级规则不被挤掉；
- 问题相关规则进入 A 层；
- 来源数量和字符预算；
- 关键来源遗漏检测；
- 一次修复成功；
- 修复失败安全兜底；
- LLM/Embedding 临时故障重试；
- 非临时错误不盲目重试。

核心优先级：

```text
业务规则正确性
> 证据覆盖完整性
> 来源可追溯
> 上下文数量
> 单纯扩大 Top-K
```
