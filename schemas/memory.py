import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class MemorySchema(BaseModel):
    id: uuid.UUID
    memory_text: str
    category: str
    is_active: bool
    source_conversation_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CreateMemoryRequest(BaseModel):
    memory_text: str
    category: Optional[str] = "project_context"
    source_conversation_id: Optional[uuid.UUID] = None

class UpdateMemoryRequest(BaseModel):
    memory_text: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None
