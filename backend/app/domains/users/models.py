from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKey, code_column


class UserRole(str, Enum):
    admin = "admin"
    operador = "operador"
    # Login de vitrine, com credencial publicada. NÃO escreve nada: o bloqueio é no
    # `get_current_user`, que é por onde passa toda requisição autenticada — e a auditoria
    # deste projeto mostra que todo endpoint de escrita depende dele.
    demonstracao = "demonstracao"


class User(UUIDPrimaryKey, TimestampMixin, Base):
    """Funcionário da locadora. Só funcionários têm login."""

    __tablename__ = "users"

    code: Mapped[str] = code_column("USR", "user_code_seq")

    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, native_enum=False, length=20, name="user_role"),
        default=UserRole.operador,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
