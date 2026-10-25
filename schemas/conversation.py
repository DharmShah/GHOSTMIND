import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

class MessageSchema(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    metadata_json: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ConversationSummarySchema(BaseModel):
    id: uuid.UUID
    title: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    message_count: Optional[int] = 0
    last_message_preview: Optional[str] = None

    class Config:
        from_attributes = True

class ConversationDetailSchema(BaseModel):
    id: uuid.UUID
    title: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    messages: List[MessageSchema] = []

    class Config:
        from_attributes = True

class CreateConversationRequest(BaseModel):
    title: Optional[str] = None

class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    is_archived: Optional[bool] = None
