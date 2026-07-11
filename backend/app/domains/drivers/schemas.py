import re
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.domains.drivers.models import DriverStatus

_NOT_DIGIT = re.compile(r"\D")


class _DriverFields(BaseModel):
    """Normalização compartilhada entre criação e edição."""

    @field_validator("cpf", mode="before", check_fields=False)
    @classmethod
    def _normalize_cpf(cls, v):
        """`123.456.789-09` → `12345678909`.

        O CPF é UNIQUE: gravar ora com pontuação, ora sem, deixaria o mesmo motorista
        entrar duas vezes.
        """
        if not isinstance(v, str):
            return v
        cpf = _NOT_DIGIT.sub("", v)
        if len(cpf) != 11:
            raise ValueError("O CPF deve ter 11 dígitos.")
        return cpf


class DriverCreate(_DriverFields):
    # `code` (DRV000001) é gerado por SEQUENCE no banco — não é aceito no input.
    full_name: str = Field(min_length=2, max_length=120)
    cpf: str
    rg: str | None = Field(default=None, max_length=20)
    birth_date: date | None = None

    cnh_number: str | None = Field(default=None, max_length=20)
    cnh_category: str | None = Field(default=None, max_length=5)
    cnh_expiry: date | None = None

    phone: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    emergency_contact: str | None = Field(default=None, max_length=120)

    address_street: str | None = Field(default=None, max_length=160)
    address_number: str | None = Field(default=None, max_length=20)
    address_city: str | None = Field(default=None, max_length=80)
    address_state: str | None = Field(default=None, max_length=2)
    address_zip: str | None = Field(default=None, max_length=9)

    status: DriverStatus = DriverStatus.active
    notes: str | None = None


# Colunas NOT NULL: aceitar `null` nelas no PATCH viraria IntegrityError (HTTP 500).
_REQUIRED = {"full_name", "cpf", "status"}


class DriverUpdate(_DriverFields):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    cpf: str | None = None
    rg: str | None = Field(default=None, max_length=20)
    birth_date: date | None = None

    cnh_number: str | None = Field(default=None, max_length=20)
    cnh_category: str | None = Field(default=None, max_length=5)
    cnh_expiry: date | None = None

    phone: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    emergency_contact: str | None = Field(default=None, max_length=120)

    address_street: str | None = Field(default=None, max_length=160)
    address_number: str | None = Field(default=None, max_length=20)
    address_city: str | None = Field(default=None, max_length=80)
    address_state: str | None = Field(default=None, max_length=2)
    address_zip: str | None = Field(default=None, max_length=9)

    status: DriverStatus | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _no_null_on_required(self):
        empty = sorted(f for f in self.model_fields_set & _REQUIRED if getattr(self, f) is None)
        if empty:
            raise ValueError(f"Estes campos não podem ficar vazios: {', '.join(empty)}.")
        return self


class DriverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    full_name: str
    cpf: str
    rg: str | None
    birth_date: date | None

    cnh_number: str | None
    cnh_category: str | None
    cnh_expiry: date | None

    phone: str | None
    email: str | None
    emergency_contact: str | None

    address_street: str | None
    address_number: str | None
    address_city: str | None
    address_state: str | None
    address_zip: str | None

    status: DriverStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime
