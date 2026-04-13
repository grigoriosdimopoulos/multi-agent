"""
Knowledge-base tool — query ingested documents via ChromaDB.
"""
from typing import Callable, Optional

from .base import BaseTool, ToolResult


class QueryKnowledgeBaseTool(BaseTool):
    name = "query_knowledge_base"
    description = (
        "Search the ingested document knowledge base and return the most relevant "
        "text chunks. Use this to answer questions grounded in uploaded files."
    )

    def __init__(self, retrieval_fn: Optional[Callable] = None):
        """
        Args:
            retrieval_fn: async callable(query, collection, n_results) -> list[dict]
                          Injected at runtime so the tool stays decoupled from ChromaDB.
        """
        self._retrieval_fn = retrieval_fn

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query"},
                "collection": {
                    "type": "string",
                    "description": "Knowledge collection name",
                    "default": "default",
                },
                "n_results": {
                    "type": "integer",
                    "description": "Number of document chunks to return",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self, query: str, collection: str = "default", n_results: int = 5
    ) -> ToolResult:
        if not self._retrieval_fn:
            return ToolResult(
                success=False,
                output=None,
                error="Knowledge base retrieval function not configured.",
            )
        try:
            results = await self._retrieval_fn(
                query=query, collection_name=collection, n_results=n_results
            )
            return ToolResult(success=True, output=results)
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))
