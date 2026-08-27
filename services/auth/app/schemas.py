from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import Role


class UserCreate(BaseModel):
    email: EmailStr
    # bcrypt silently truncates/errors past 72 bytes; capping here means the
    # limit shows up as a clean 422 validation error instead of a confusing
    # failure inside the hashing call.
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str | None
    role: Role
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
