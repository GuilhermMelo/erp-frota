"""Auditoria automática via event listeners do SQLAlchemy.

Por que listener e não chamada no service: chamada no service é coisa que humano cansado
esquece, e um log de auditoria com buraco é pior do que nenhum. Aqui, tudo que passar pela
sessão é registrado, sem ninguém precisar lembrar.

Por que DOIS eventos:
  - `before_flush` é o único momento em que o HISTÓRICO do atributo existe (o "de → para").
    Depois do flush, o SQLAlchemy já limpou essa informação.
  - `after_flush` é o único momento em que o `id` (gen_random_uuid) e o `code` (nextval)
    JÁ FORAM gerados pelo banco. Registrar a criação em before_flush gravaria entity_id
    NULL — e o log de criação de um veículo nunca apareceria na busca por aquele veículo.

Então: coleta-se o diff em before_flush, e grava-se em after_flush.

ARMADILHA CONHECIDA: o listener é CEGO a DML em massa
(`session.execute(update(...))`, `query.delete()`), porque isso não passa pelo ORM.
Regra do projeto (CLAUDE.md, nº 3): services nunca usam bulk DML em tabela auditada.
Carregue o objeto e altere o atributo.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import event, insert, inspect
from sqlalchemy.orm import Session

from app.core.context import get_actor
from app.domains.audit.models import AuditAction, AuditLog

# Não geram log: o próprio log (recursão) e as tabelas de catálogo (seed, não operação).
_IGNORED = {"audit_logs", "expense_categories", "checklist_items"}
_MASKED_FIELDS = {"hashed_password"}
_PENDING = "_audit_pending"


def _serialize(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _diff(obj, *, only_changed: bool) -> dict:
    state = inspect(obj)
    changes: dict[str, dict] = {}
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in {"created_at", "updated_at"}:
            continue
        history = state.attrs[key].history
        if only_changed and not history.has_changes():
            continue
        before = history.deleted[0] if history.deleted else None
        after = history.added[0] if history.added else getattr(obj, key, None)
        if only_changed and before == after:
            continue
        if key in _MASKED_FIELDS:
            changes[key] = {"de": "***", "para": "***"}
            continue
        entry = {"para": _serialize(after)}
        if only_changed:
            entry["de"] = _serialize(before)
        changes[key] = entry
    return changes


@event.listens_for(Session, "before_flush")
def _collect_changes(session: Session, _flush_context, _instances) -> None:
    """Coleta o 'de → para'. É o único momento em que essa informação existe."""
    pending: list[tuple] = session.info.setdefault(_PENDING, [])

    for obj in session.new:
        if obj.__tablename__ not in _IGNORED:
            pending.append((obj, AuditAction.create, _diff(obj, only_changed=False)))

    for obj in session.dirty:
        if obj.__tablename__ in _IGNORED or not session.is_modified(obj):
            continue
        changes = _diff(obj, only_changed=True)
        if changes:
            pending.append((obj, AuditAction.update, changes))

    for obj in session.deleted:
        if obj.__tablename__ not in _IGNORED:
            pending.append((obj, AuditAction.delete, {}))


@event.listens_for(Session, "after_flush")
def _write_audit_rows(session: Session, _flush_context) -> None:
    """Grava. Aqui o id (UUID) e o code (CAR000001) já vieram do banco."""
    pending = session.info.pop(_PENDING, None)
    if not pending:
        return

    actor = get_actor()
    rows = []
    for obj, action, changes in pending:
        entity_id = getattr(obj, "id", None)
        rows.append(
            {
                "actor_user_id": actor.user_id if actor else None,
                "actor_email": actor.email if actor else "sistema",
                "ip_address": actor.ip if actor else None,
                "action": action.value,
                "entity_type": obj.__tablename__,
                "entity_id": entity_id if isinstance(entity_id, UUID) else None,
                "entity_code": getattr(obj, "code", None),
                "changes": changes or None,
            }
        )

    # INSERT direto em vez de session.add(): objetos adicionados dentro de after_flush não
    # entram neste flush. O execute grava agora, na mesma transação. (audit_logs está em
    # _IGNORED, então isto não realimenta o listener.)
    session.execute(insert(AuditLog), rows)


def log_auth_event(session: Session, action: AuditAction, email: str, user_id: UUID | None) -> None:
    """Login e falha de login não alteram entidade nenhuma — registra na mão."""
    session.execute(
        insert(AuditLog),
        [
            {
                "actor_user_id": user_id,
                "actor_email": email,
                "action": action.value,
                "entity_type": "users",
                "entity_id": user_id,
            }
        ],
    )
