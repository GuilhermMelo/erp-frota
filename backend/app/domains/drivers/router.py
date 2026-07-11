import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.domains.auth.deps import AdminUser, CurrentUser, Db
from app.domains.drivers.models import Driver, DriverStatus
from app.domains.drivers.schemas import DriverCreate, DriverOut, DriverUpdate

router = APIRouter(prefix="/drivers", tags=["motoristas"])

_NOT_DIGIT = re.compile(r"\D")


def _get(db: Session, driver_id: UUID) -> Driver:
    """Motorista soft-deletado é, para todos os efeitos, inexistente."""
    driver = db.get(Driver, driver_id)
    if driver is None or driver.deleted_at is not None:
        raise NotFound("Motorista não encontrado.")
    return driver


def _check_unique_cpf(db: Session, cpf: str | None, *, exclude_id: UUID | None = None) -> None:
    """CPF é UNIQUE: sem esta checagem o duplicado vira IntegrityError → HTTP 500."""
    if not cpf:
        return
    stmt = select(Driver).where(Driver.cpf == cpf)
    if exclude_id:
        stmt = stmt.where(Driver.id != exclude_id)
    found = db.scalar(stmt)
    if found:
        suffix = " (registro excluído)." if found.deleted_at else f" ({found.code})."
        raise Conflict("Já existe um motorista com esse CPF" + suffix)


@router.get("", response_model=list[DriverOut])
def list_drivers(
    db: Db,
    _: CurrentUser,
    status: DriverStatus | None = None,
    q: str | None = None,
):
    stmt = select(Driver).where(Driver.deleted_at.is_(None))

    if status:
        stmt = stmt.where(Driver.status == status)

    if q and q.strip():
        term = f"%{q.strip()}%"
        # O CPF é gravado só com dígitos; quem busca "123.456" tem que achar mesmo assim.
        digits = _NOT_DIGIT.sub("", q)
        conditions = [
            Driver.full_name.ilike(term),
            Driver.code.ilike(term),
            Driver.phone.ilike(term),
        ]
        if digits:
            conditions.append(Driver.cpf.ilike(f"%{digits}%"))
        stmt = stmt.where(or_(*conditions))

    return db.scalars(stmt.order_by(Driver.full_name)).all()


@router.post("", response_model=DriverOut, status_code=status.HTTP_201_CREATED)
def create_driver(data: DriverCreate, db: Db, _: CurrentUser):
    _check_unique_cpf(db, data.cpf)

    driver = Driver(**data.model_dump())
    db.add(driver)
    db.commit()
    return driver


@router.get("/{driver_id}", response_model=DriverOut)
def get_driver(driver_id: UUID, db: Db, _: CurrentUser):
    return _get(db, driver_id)


@router.patch("/{driver_id}", response_model=DriverOut)
def update_driver(driver_id: UUID, data: DriverUpdate, db: Db, _: CurrentUser):
    driver = _get(db, driver_id)
    fields = data.model_dump(exclude_unset=True)

    _check_unique_cpf(db, fields.get("cpf"), exclude_id=driver.id)

    for key, value in fields.items():
        setattr(driver, key, value)

    db.commit()
    return driver


@router.delete("/{driver_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_driver(driver_id: UUID, db: Db, _: AdminUser):
    """Soft delete — SEMPRE.

    O motorista está amarrado a contratos, receitas e multas. DELETE físico barraria no FK
    (ondelete=RESTRICT) ou apagaria histórico financeiro. Some da lista, continua nos registros.
    """
    driver = _get(db, driver_id)
    driver.deleted_at = datetime.now(UTC)
    db.commit()
