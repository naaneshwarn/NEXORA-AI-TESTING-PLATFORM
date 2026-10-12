from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CRMLeadCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str
    company: Optional[str] = None
    status: Literal["new", "contacted", "qualified", "closed"] = "new"


class CRMLeadResponse(CRMLeadCreate):
    id: str
    created_at: str
    updated_at: Optional[str] = None
