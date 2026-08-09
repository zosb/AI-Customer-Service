"""集中导入 ORM 模型，确保 Alembic 能发现全部数据表。"""

from app.models.chat import ChatMessage, ChatSession, MessageFeedback, MessageSource
from app.models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.models.usage import DailyQuestionUsage
from app.models.user import User

__all__ = [
    "User",
    "KnowledgeBase",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "ChatSession",
    "ChatMessage",
    "MessageSource",
    "MessageFeedback",
    "DailyQuestionUsage",
]
