-- AI Customer Service schema snapshot
-- Generated from SQLAlchemy models. Alembic migrations remain the source of truth.
-- MySQL 8.x / utf8mb4

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS users (
	id BIGINT NOT NULL AUTO_INCREMENT,
	email VARCHAR(255),
	phone VARCHAR(32),
	password_hash VARCHAR(255) NOT NULL,
	display_name VARCHAR(64),
	`role` VARCHAR(20) NOT NULL DEFAULT 'user',
	status VARCHAR(20) NOT NULL DEFAULT 'active',
	last_login_at DATETIME,
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT ck_users_email_or_phone_required CHECK (email IS NOT NULL OR phone IS NOT NULL),
	CONSTRAINT ck_users_role CHECK (role IN ('user', 'admin')),
	CONSTRAINT ck_users_status CHECK (status IN ('active', 'disabled')),
	UNIQUE (email),
	UNIQUE (phone)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_users_role ON users (`role`);

CREATE INDEX ix_users_status ON users (status);

CREATE TABLE IF NOT EXISTS daily_question_usage (
	id BIGINT NOT NULL AUTO_INCREMENT,
	user_id BIGINT NOT NULL,
	usage_date DATE NOT NULL,
	question_count INTEGER NOT NULL DEFAULT 0,
	updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	CONSTRAINT ck_daily_question_usage_non_negative CHECK (question_count >= 0),
	CONSTRAINT uq_daily_question_usage_user_date UNIQUE (user_id, usage_date),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS knowledge_bases (
	id BIGINT NOT NULL AUTO_INCREMENT,
	name VARCHAR(128) NOT NULL,
	description TEXT,
	routing_description TEXT,
	is_active BOOL NOT NULL DEFAULT 1,
	created_by BIGINT,
	deleted_at DATETIME,
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	UNIQUE (name),
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_knowledge_bases_active_deleted ON knowledge_bases (is_active, deleted_at);

CREATE INDEX ix_knowledge_bases_created_by ON knowledge_bases (created_by);

CREATE INDEX ix_knowledge_bases_deleted_at ON knowledge_bases (deleted_at);

CREATE TABLE IF NOT EXISTS chat_sessions (
	id BIGINT NOT NULL AUTO_INCREMENT,
	user_id BIGINT NOT NULL,
	title VARCHAR(255) NOT NULL DEFAULT '新会话',
	status VARCHAR(20) NOT NULL DEFAULT 'active',
	selected_knowledge_base_id BIGINT,
	last_message_at DATETIME,
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT ck_chat_sessions_status CHECK (status IN ('active', 'archived')),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(selected_knowledge_base_id) REFERENCES knowledge_bases (id) ON DELETE SET NULL
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_chat_sessions_user_last_message ON chat_sessions (user_id, last_message_at);

CREATE TABLE IF NOT EXISTS knowledge_documents (
	id BIGINT NOT NULL AUTO_INCREMENT,
	knowledge_base_id BIGINT NOT NULL,
	original_name VARCHAR(255) NOT NULL,
	stored_name VARCHAR(255) NOT NULL,
	file_extension VARCHAR(10) NOT NULL,
	mime_type VARCHAR(100),
	file_size_bytes BIGINT NOT NULL,
	sha256 VARCHAR(64) NOT NULL,
	status VARCHAR(20) NOT NULL DEFAULT 'processing',
	error_message TEXT,
	chunk_count INTEGER NOT NULL DEFAULT 0,
	content_version INTEGER NOT NULL DEFAULT 1,
	uploaded_by BIGINT,
	processed_at DATETIME,
	deleted_at DATETIME,
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT ck_knowledge_documents_status CHECK (status IN ('processing', 'ready', 'failed')),
	CONSTRAINT ck_knowledge_documents_extension CHECK (file_extension IN ('.txt', '.md', '.pdf')),
	FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_bases (id) ON DELETE CASCADE,
	UNIQUE (stored_name),
	FOREIGN KEY(uploaded_by) REFERENCES users (id) ON DELETE SET NULL
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_knowledge_documents_deleted_at ON knowledge_documents (deleted_at);

CREATE INDEX ix_knowledge_documents_kb_status ON knowledge_documents (knowledge_base_id, status);

CREATE INDEX ix_knowledge_documents_sha256 ON knowledge_documents (sha256);

CREATE INDEX ix_knowledge_documents_uploaded_by ON knowledge_documents (uploaded_by);

CREATE TABLE IF NOT EXISTS chat_messages (
	id BIGINT NOT NULL AUTO_INCREMENT,
	session_id BIGINT NOT NULL,
	user_id BIGINT,
	reply_to_message_id BIGINT,
	`role` VARCHAR(16) NOT NULL,
	content LONGTEXT NOT NULL,
	intent VARCHAR(50),
	routed_knowledge_base_id BIGINT,
	retrieval_status VARCHAR(20),
	is_fallback BOOL NOT NULL DEFAULT 0,
	question_char_count INTEGER,
	prompt_token_estimate INTEGER,
	completion_token_count INTEGER,
	follow_up_suggestions JSON,
	stream_completed_at DATETIME,
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT ck_chat_messages_role CHECK (role IN ('user', 'assistant', 'system')),
	CONSTRAINT ck_chat_messages_retrieval_status CHECK (
            retrieval_status IS NULL OR
            retrieval_status IN ('matched', 'empty', 'skipped', 'failed')
            ),
	FOREIGN KEY(session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE,
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL,
	FOREIGN KEY(reply_to_message_id) REFERENCES chat_messages (id) ON DELETE SET NULL,
	FOREIGN KEY(routed_knowledge_base_id) REFERENCES knowledge_bases (id) ON DELETE SET NULL
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_chat_messages_intent ON chat_messages (intent);

CREATE INDEX ix_chat_messages_session_created ON chat_messages (session_id, created_at);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
	id BIGINT NOT NULL AUTO_INCREMENT,
	knowledge_base_id BIGINT NOT NULL,
	document_id BIGINT NOT NULL,
	chunk_index INTEGER NOT NULL,
	vector_id VARCHAR(128) NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	content_text LONGTEXT NOT NULL,
	char_count INTEGER NOT NULL,
	token_estimate INTEGER,
	priority INTEGER NOT NULL DEFAULT 0,
	metadata_json JSON,
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uq_knowledge_chunks_document_index UNIQUE (document_id, chunk_index),
	FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_bases (id) ON DELETE CASCADE,
	FOREIGN KEY(document_id) REFERENCES knowledge_documents (id) ON DELETE CASCADE,
	UNIQUE (vector_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_knowledge_chunks_kb_priority ON knowledge_chunks (knowledge_base_id, priority);

CREATE TABLE IF NOT EXISTS message_feedback (
	id BIGINT NOT NULL AUTO_INCREMENT,
	message_id BIGINT NOT NULL,
	user_id BIGINT NOT NULL,
	rating SMALLINT NOT NULL,
	comment VARCHAR(1000),
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT ck_message_feedback_rating CHECK (rating IN (-1, 1)),
	CONSTRAINT uq_message_feedback_message_user UNIQUE (message_id, user_id),
	FOREIGN KEY(message_id) REFERENCES chat_messages (id) ON DELETE CASCADE,
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_message_feedback_rating_created ON message_feedback (rating, created_at);

CREATE TABLE IF NOT EXISTS message_sources (
	id BIGINT NOT NULL AUTO_INCREMENT,
	message_id BIGINT NOT NULL,
	document_id BIGINT,
	chunk_id BIGINT,
	document_name VARCHAR(255) NOT NULL,
	chunk_summary TEXT NOT NULL,
	distance FLOAT,
	similarity_score FLOAT,
	`rank` INTEGER NOT NULL,
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	CONSTRAINT uq_message_sources_message_rank UNIQUE (message_id, `rank`),
	FOREIGN KEY(message_id) REFERENCES chat_messages (id) ON DELETE CASCADE,
	FOREIGN KEY(document_id) REFERENCES knowledge_documents (id) ON DELETE SET NULL,
	FOREIGN KEY(chunk_id) REFERENCES knowledge_chunks (id) ON DELETE SET NULL
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_message_sources_document ON message_sources (document_id);

SET FOREIGN_KEY_CHECKS = 1;
