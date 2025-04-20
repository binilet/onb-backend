from datetime import datetime,timezone
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class UserSchema(BaseModel):
    phone: str
    username: str
    role: str = "user"
    agent_id: str = "system"
    agent_percent: float = 0.0
    is_active: bool = True
    verified: bool = False
    verification_txt_count: int = 0
    ban_until: Optional[datetime] = None
    pwd_change_count: int = 0
    pwd_change_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    password: str

    @field_validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v
    
class UserUpdate(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    agent_id: Optional[str] = None
    agent_percent: Optional[float] = None
    is_active: Optional[bool] = None
    ban_until: Optional[datetime] = None
    verified: Optional[bool] = None


class UserLogin(BaseModel):
    phone: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    phone: Optional[str] = None