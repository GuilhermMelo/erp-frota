from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class AuditAction(str, Enum):
    create = "create"
    update = "update"
    delete = "delete"
    login = "login"
    login_failed = "login_failed"


class AuditLog(Base):
    """Log de auditoria — append-only.

    Não tem UPDATE nem DELETE, nem endpoint que os faça. É populado por um event listener
    do SQLAlchemy (ver listeners.py), não por chamadas espalhadas pelos services: chamada
    no service é coisa que humano cansado esquece, e log com buraco é pior que log nenhum.

    Guarda `actor_email` desnormalizado de propósito — o log sobrevive à exclusão do usuário.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    actor_user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    actor_email: Mapped[str] = mapped_column(String(120), default="sistema", nullable=False)

    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction, native_enum=False, length=20, name="audit_action"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    entity_code: Mapped[str | None] = mapped_column(String(12))

    # {"campo": {"de": ..., "para": ...}}
    changes: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))

    __table_args__ = (
        Index("ix_audit_logs_entidade", "entity_type", "entity_id"),
        Index("ix_audit_logs_quando", "occurred_at"),
    )
