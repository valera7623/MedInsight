"""Self-healing RAG: learn from agent errors and apply known fixes.

Adapted from ReportAgent. MedInsight keeps a durable SQL ``ErrorFix`` table and
uses ChromaDB as a similarity index when available, degrading gracefully to a
keyword-overlap search when ChromaDB / embeddings are not installed.
"""

from app.services.self_healing.healing_decorator import with_self_healing
from app.services.self_healing.vector_store import (
    ErrorKnowledgeBase,
    get_knowledge_base,
    is_self_healing_enabled,
)

__all__ = [
    "ErrorKnowledgeBase",
    "get_knowledge_base",
    "is_self_healing_enabled",
    "with_self_healing",
]
