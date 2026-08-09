-- Minimal production-safe initial data.
-- No test user, password, API key or demo conversation is inserted.

INSERT INTO knowledge_bases
    (name, description, routing_description, is_active, created_by, created_at, updated_at)
VALUES
    ('默认知识库', '系统初始化的默认知识库，可在管理界面重命名或删除。', NULL, 1, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON DUPLICATE KEY UPDATE
    description = VALUES(description),
    updated_at = CURRENT_TIMESTAMP;
