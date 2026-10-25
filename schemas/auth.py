import uuid
from typing import Optional
from pydantic import BaseModel

class UserPreferenceSchema(BaseModel):
    theme: str
    selected_model: str
    voice_model_size: str
    language: str
    memory_enabled: bool

    class Config:
        from_attributes = True

class UserProfileSchema(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    avatar_url: Optional[str] = None
    preferences: Optional[UserPreferenceSchema] = None

    class Config:
        from_attributes = True

class GoogleAuthRequest(BaseModel):
    credential: Optional[str] = None
    code: Optional[str] = None
    redirect_uri: Optional[str] = None

class SessionResponse(BaseModel):
    authenticated: bool
    user: Optional[UserProfileSchema] = None
    message: Optional[str] = None
