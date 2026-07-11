from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domains.users.models import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    role: UserRole = UserRole.operador

    @field_validator("email")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return v.strip().lower()


class UserCreate(UserBase):
    # 8 caracteres no mínimo; bcrypt trunca acima de 72 bytes, então barramos antes.
    password: str = Field(min_length=8, max_length=72)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)


class UserOut(BaseModel):
    """Nunca expõe hashed_password."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
