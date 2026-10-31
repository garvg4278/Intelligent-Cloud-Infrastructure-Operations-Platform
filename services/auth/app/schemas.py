from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import Role


class UserCreate(BaseModel):
    email: EmailStr
    # bcrypt silently truncates/errors past 72 bytes; capping here means the
    # limit shows up as a clean 422 validation error instead of a confusing
    # failure inside the hashing call.
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def _password_fits_bcrypt(cls, value: str) -> str:
        # max_length counts characters; bcrypt's limit is 72 BYTES. 40
        # two-byte characters passed the length check and then crashed the
        # hashing call with a 500.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes when UTF-8 encoded")
        return value


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


class RoleUpdate(BaseModel):
    role: Role
