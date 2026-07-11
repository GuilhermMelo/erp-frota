"""Consulta do log de auditoria.

Só leitura, e só ADMIN. O log é append-only: não existe endpoint que atualize ou apague
uma linha daqui — se existisse, o log deixaria de ser prova.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.domains.audit.models import AuditAction, AuditLog
from app.domains.auth.deps import AdminUser, Db

router = APIRouter(prefix="/audit", tags=["auditoria"])


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    actor_user_id: UUID | None
    actor_email: str
    action: AuditAction
    entity_type: str  # o nome da TABELA: vehicles, contracts, inspections...
    entity_id: UUID | None
    entity_code: str | None
    changes: dict | None  # {"campo": {"de": ..., "para": ...}}
    ip_address: str | None


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    db: Db,
    _: AdminUser,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    stmt = (
        select(AuditLog)
        # `occurred_at` é o now() da TRANSAÇÃO: várias linhas do mesmo commit têm o mesmo
        # instante. O id desempata e garante ordem estável.
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    return db.scalars(stmt).all()
