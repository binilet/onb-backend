from typing import List
from pydantic import BaseModel, Field, validator
from datetime import datetime


class PatternBase(BaseModel):
    name: str = Field(..., description="Unique pattern name")
    isActive: bool = Field(default=True, description="Whether the pattern is active")
    grid: List[List[bool]] = Field(..., description="5x5 boolean grid")


    @validator("grid")
    def validate_grid(cls, v):
        if len(v) != 5 or not all(len(row) == 5 for row in v):
            raise ValueError("Grid must be a valid 5x5 matrix of booleans")
        return v


class PatternCreate(PatternBase):
    """Schema for creating a jackpot pattern"""
    pass


class PatternUpdate(BaseModel):
    """Schema for updating a jackpot pattern"""
    name: str | None = None
    isActive: bool | None = None
    grid: List[List[bool]] | None = None

    @validator("grid")
    def validate_grid(cls, v):
        if v is not None:
            if len(v) != 5 or not all(len(row) == 5 for row in v):
                raise ValueError("Grid must be a valid 5x5 matrix of booleans")
        return v


class PatternInDB(PatternBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
