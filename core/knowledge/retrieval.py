"""
Knowledge retrieval — cosine-similarity search over ChromaDB collections.
"""
from typing import Optional

from .ingestion import get_chroma_client


async def retrieve(
    query: str,
    collection_name: str = "default",
    n_results: int = 5,
    persist_directory: str = "./data/chroma",
    where: Optional[dict] = None,
) -> list[dict]:
    """Return the top-n most relevant document chunks for *query*."""
    client = get_chroma_client(persist_directory)
    try:
        collection = client.get_collection(collection_name)
    except Exception:
        return []

    count = collection.count()
    if count == 0:
        return []

    n = min(n_results, count)
    query_params: dict = {"query_texts": [query], "n_results": n}
    if where:
        query_params["where"] = where

    results = collection.query(**query_params)

    docs: list[dict] = []
    for content, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        docs.append(
            {
                "content": content,
                "metadata": meta,
                "score": round(1.0 - dist, 4),  # distance → similarity
            }
        )
    return docs


async def list_collections(persist_directory: str = "./data/chroma") -> list[str]:
    client = get_chroma_client(persist_directory)
    return [c.name for c in client.list_collections()]


async def delete_collection(
    collection_name: str, persist_directory: str = "./data/chroma"
) -> bool:
    client = get_chroma_client(persist_directory)
    try:
        client.delete_collection(collection_name)
        return True
    except Exception:
        return False


async def get_collection_stats(
    collection_name: str, persist_directory: str = "./data/chroma"
) -> dict:
    client = get_chroma_client(persist_directory)
    try:
        col = client.get_collection(collection_name)
        return {"name": collection_name, "count": col.count()}
    except Exception:
        return {"name": collection_name, "count": 0, "error": "Collection not found"}
