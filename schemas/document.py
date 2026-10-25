import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

class DocumentChunkSchema(BaseModel):
    id: uuid.UUID
    chunk_index: int
    text_content: str
    metadata_json: Optional[str] = None

    class Config:
        from_attributes = True

class DocumentSummarySchema(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    checksum: str
    processing_status: str
    error_message: Optional[str] = None
    created_at: datetime
    chunk_count: Optional[int] = 0

    class Config:
        from_attributes = True

class DocumentDetailSchema(DocumentSummarySchema):
    chunks: List[DocumentChunkSchema] = []

class DocumentUploadResponse(BaseModel):
    success: bool
    document: DocumentSummarySchema
    message: str
