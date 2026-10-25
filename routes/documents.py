import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from core.database import get_db
from models import User, Document, DocumentChunk
from routes.conversations import resolve_active_user
from schemas.document import DocumentSummarySchema, DocumentUploadResponse
from services import document_service

router = APIRouter(prefix="/api/documents", tags=["Documents & RAG"])

@router.get("", response_model=List[DocumentSummarySchema])
def list_user_documents(
    current_user: User = Depends(resolve_active_user),
    db: Session = Depends(get_db)
):
    """Lists all uploaded documents for the authenticated user."""
    docs = db.scalars(
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(desc(Document.created_at))
    ).all()

    items = []
    for d in docs:
        chunk_count = db.scalar(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == d.id)
        ) or 0
        items.append({
            "id": d.id,
            "filename": d.filename,
            "content_type": d.content_type,
            "file_size": d.file_size,
            "checksum": d.checksum,
            "processing_status": d.processing_status,
            "error_message": d.error_message,
            "created_at": d.created_at,
            "chunk_count": chunk_count
        })
    return items

@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(resolve_active_user),
    db: Session = Depends(get_db)
):
    """Uploads, validates, extracts text, embeds, and indexes a document for local RAG."""
    content_bytes = await file.read()
    if not content_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        doc = document_service.ingest_document(
            db=db,
            user_id=current_user.id,
            filename=file.filename or "uploaded_file.txt",
            content_type=file.content_type or "application/octet-stream",
            file_bytes=content_bytes
        )

        chunk_count = db.scalar(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == doc.id)
        ) or 0

        summary = {
            "id": doc.id,
            "filename": doc.filename,
            "content_type": doc.content_type,
            "file_size": doc.file_size,
            "checksum": doc.checksum,
            "processing_status": doc.processing_status,
            "error_message": doc.error_message,
            "created_at": doc.created_at,
            "chunk_count": chunk_count
        }

        return DocumentUploadResponse(
            success=True,
            document=summary,
            message="Document successfully uploaded and indexed for RAG."
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document processing failed: {e}")

@router.delete("/{document_id}")
def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(resolve_active_user),
    db: Session = Depends(get_db)
):
    """Deletes a document and all associated chunks from RAG index."""
    success = document_service.delete_document(
        db=db,
        user_id=current_user.id,
        document_id=document_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or access denied.")
    return {"message": "Document and all vector embeddings deleted successfully."}
