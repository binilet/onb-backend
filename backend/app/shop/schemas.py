from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ShopCreate(BaseModel):
    representativePhone: str
    shopName: str
    address: str
    isActive: bool = True
    banUntil: Optional[datetime] = None


class ShopUpdate(BaseModel):
    representativePhone: Optional[str] = None
    shopName: Optional[str] = None
    address: Optional[str] = None
    isActive: Optional[bool] = None
    banUntil: Optional[datetime] = None


class Shop(BaseModel):
    shop_id: str = Field(default_factory=lambda: str(uuid4()))
    representativePhone: str
    representativeRole: str
    agentId: Optional[str] = None
    shopName: str
    address: str
    isActive: bool = True
    banUntil: Optional[datetime] = None
    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: datetime = Field(default_factory=utc_now)


class ShopBranchCreate(BaseModel):
    branchName: str
    address: str
    depositPhone: str = Field(min_length=3, max_length=32)
    telebirrAccountName: str = Field(min_length=2, max_length=120)
    isActive: bool = True
    banUntil: Optional[datetime] = None


class ShopBranchUpdate(BaseModel):
    branchName: Optional[str] = None
    address: Optional[str] = None
    depositPhone: Optional[str] = Field(default=None, min_length=3, max_length=32)
    telebirrAccountName: Optional[str] = Field(default=None, min_length=2, max_length=120)
    isActive: Optional[bool] = None
    banUntil: Optional[datetime] = None


class ShopBranch(BaseModel):
    branch_id: str = Field(default_factory=lambda: str(uuid4()))
    shopId: str
    branchName: str
    address: str
    depositPhone: Optional[str] = None
    telebirrAccountName: Optional[str] = None
    isActive: bool = True
    banUntil: Optional[datetime] = None
    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: datetime = Field(default_factory=utc_now)
