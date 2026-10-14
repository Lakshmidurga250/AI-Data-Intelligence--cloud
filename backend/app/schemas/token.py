"""Authentication token schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class Token(BaseModel):
    """Access token payload returned upon authentication."""

    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


class TokenPayload(BaseModel):
    """Decoded JWT payload."""

    sub: Optional[str] = Field(default=None, description="Subject (User ID)")
    exp: Optional[int] = Field(default=None, description="Expiration timestamp")
