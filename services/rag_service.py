import json
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from models import DocumentChunk, Document
from services.embedding_service import get_embedding, cosine_similarity

def retrieve_relevant_chunks(
    db: Session,
    user_id: uuid.UUID,
    query: str,
    top_k: int = 4,
    min_similarity: float = 0.40,
    filter_document_ids: Optional[List[uuid.UUID]] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves the most semantically relevant document chunks for a query.
    Restricted strictly to the authenticated user's indexed documents.
    """
    if not query.strip():
        return []

    # 1. Generate query embedding
    query_vector = get_embedding(query)

    # 2. Build query for user chunks from indexed documents
    stmt = (
        select(DocumentChunk, Document.filename)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.user_id == user_id,
            Document.processing_status == "indexed"
        )
    )

    if filter_document_ids:
        stmt = stmt.where(DocumentChunk.document_id.in_(filter_document_ids))

    results = db.execute(stmt).all()
    if not results:
        return []

    # 3. Calculate similarities and rank
    scored_chunks = []
    for chunk, filename in results:
        try:
            chunk_vec = json.loads(chunk.embedding_json)
            score = cosine_similarity(query_vector, chunk_vec)
            if score >= min_similarity:
                meta = json.loads(chunk.metadata_json) if chunk.metadata_json else {}
                scored_chunks.append({
                    "chunk_id": str(chunk.id),
                    "document_id": str(chunk.document_id),
                    "filename": filename,
                    "page": meta.get("page"),
                    "text": chunk.text_content,
                    "score": round(score, 3)
                })
        except Exception:
            continue

    # Sort descending by score
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    return scored_chunks[:top_k]

def build_rag_context_prompt(chunks: List[Dict[str, Any]]) -> str:
    """Formats retrieved chunks into a clean, grounded context block for the LLM."""
    if not chunks:
        return ""

    context_parts = []
    for idx, c in enumerate(chunks, start=1):
        source_label = c["filename"]
        if c.get("page"):
            source_label += f" (Page {c['page']})"
        context_parts.append(f"[Source {idx}: {source_label}]\n{c['text']}")

    return (
        "\n--- RELEVANT UPLOADED DOCUMENT EVIDENCE ---\n"
        + "\n\n".join(context_parts)
        + "\n---------------------------------------------\n"
    )
