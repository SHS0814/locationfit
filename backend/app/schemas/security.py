from datetime import datetime

from pydantic import BaseModel, Field


class AIAccessRequest(BaseModel):
    access_code: str = Field(min_length=1, max_length=256)


class AISessionStatus(BaseModel):
    required: bool
    authenticated: bool
    expires_at: datetime | None
