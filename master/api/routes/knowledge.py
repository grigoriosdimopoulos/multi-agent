"""Knowledge-base routes — upload files, query, manage collections."""
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from ..models import KnowledgeCollectionInfo, KnowledgeQueryRequest

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

CHROMA_DIR = os.getenv("CHROMA_DIR", "./data/chroma")


@router.get("/collections", response_model=list[KnowledgeCollectionInfo])
async def list_collections():
    from core.knowledge.retrieval import list_collections, get_collection_stats
    names = await list_collections(CHROMA_DIR)
    return [
        KnowledgeCollectionInfo(**(await get_collection_stats(n, CHROMA_DIR)))
        for n in names
    ]


@router.delete("/collections/{name}", status_code=204)
async def delete_collection(name: str):
    from core.knowledge.retrieval import delete_collection
    ok = await delete_collection(name, CHROMA_DIR)
    if not ok:
        raise HTTPException(404, f"Collection '{name}' not found")


@router.post("/ingest/file")
async def ingest_file(
    file: UploadFile = File(...),
    collection: str = Form("default"),
):
    """Upload and ingest a single file into a knowledge collection."""
    from core.knowledge.ingestion import ingest_file as _ingest

    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await _ingest(tmp_path, collection, CHROMA_DIR)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not result.get("success"):
        raise HTTPException(422, result.get("error", "Ingestion failed"))
    return result


@router.post("/ingest/directory")
async def ingest_directory(
    directory: str = Form(...),
    collection: str = Form("default"),
    recursive: bool = Form(True),
):
    """Ingest all supported files in a server-side directory."""
    from core.knowledge.ingestion import ingest_directory as _ingest_dir
    result = await _ingest_dir(directory, collection, CHROMA_DIR, recursive)
    return result


@router.post("/query")
async def query_knowledge(body: KnowledgeQueryRequest):
    from core.knowledge.retrieval import retrieve
    results = await retrieve(
        query=body.query,
        collection_name=body.collection,
        n_results=body.n_results,
        persist_directory=CHROMA_DIR,
    )
    return {"results": results}
