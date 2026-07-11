from datetime import date, datetime
from enum import Enum

from sqlalchemy import Date, DateTime, Enum as SAEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKey, code_column


class DriverStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    blocked = "blocked"


class Driver(UUIDPrimaryKey, TimestampMixin, Base):
    """Motorista é DADO, não usuário. Motorista não tem login (ver MANIFESTO.md)."""

    __tablename__ = "drivers"

    code: Mapped[str] = code_column("DRV", "driver_code_seq")

    full_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    cpf: Mapped[str] = mapped_column(String(11), unique=True, nullable=False, index=True)
    rg: Mapped[str | None] = mapped_column(String(20))
    birth_date: Mapped[date | None] = mapped_column(Date)

    cnh_number: Mapped[str | None] = mapped_column(String(20))
    cnh_category: Mapped[str | None] = mapped_column(String(5))
    cnh_expiry: Mapped[date | None] = mapped_column(Date)

    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(120))
    emergency_contact: Mapped[str | None] = mapped_column(String(120))

    address_street: Mapped[str | None] = mapped_column(String(160))
    address_number: Mapped[str | None] = mapped_column(String(20))
    address_city: Mapped[str | None] = mapped_column(String(80))
    address_state: Mapped[str | None] = mapped_column(String(2))
    address_zip: Mapped[str | None] = mapped_column(String(9))

    status: Mapped[DriverStatus] = mapped_column(
        SAEnum(DriverStatus, native_enum=False, length=20, name="driver_status"),
        default=DriverStatus.active,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
