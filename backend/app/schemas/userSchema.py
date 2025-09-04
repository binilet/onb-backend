from datetime import datetime,timezone
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class UserSchema(BaseModel):
    phone: str
    username: str
    role: str = "user"
    agentId: Optional[str] = None
    agentPercent: float = 0.0
    adminId: Optional[str] = None
    adminPercent: float = 0.0
    isActive: bool = True
    verified: bool = False
    verification_txt_count: int = 0
    banUntil: Optional[datetime] = None
    pwd_change_count: int = 0
    pwd_change_date: Optional[datetime] = None
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    password: str
    invitedBy:Optional[str] = None

    @field_validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v
    
class UserUpdate(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    agentId: Optional[str] = None
    agentPercent: Optional[float] = None
    adminId: Optional[str] = None
    adminPercent: Optional[float] = None
    isActive: Optional[bool] = None
    banUntil: Optional[datetime] = None
    verified: Optional[bool] = None
    


class UserLogin(BaseModel):
    phone: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    phone: Optional[str] = None