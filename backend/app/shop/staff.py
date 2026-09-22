from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from schemas.userSchema import UserSchema


class StaffUserCreate(BaseModel):
    phone: str
    username: str
    password: str
    role: Literal["agent", "subagent", "admin", "cashier"]
    shopId: Optional[str] = None
    branchId: Optional[str] = None
    parentCutPercent: Optional[float] = Field(default=None, gt=0)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 6:
            raise ValueError("Password must be at least 6 characters")
        return value

    def to_user_schema(self) -> UserSchema:
        return UserSchema(**self.model_dump(), mustChangePassword=True)


class StaffUserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    isActive: Optional[bool] = None
    banUntil: Optional[datetime] = None
    branchId: Optional[str] = None
    shopId: Optional[str] = None
    role: Optional[Literal["agent", "subagent", "admin", "cashier"]] = None
    parentCutPercent: Optional[float] = Field(default=None, gt=0)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and len(value) < 6:
            raise ValueError("Password must be at least 6 characters")
        return value
