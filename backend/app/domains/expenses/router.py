from datetime import date
from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.domains.auth.deps import AdminUser, CurrentUser, Db
from app.domains.expenses import service
from app.domains.expenses.models import Expense, ExpenseCategory, ExpenseOrigin, ExpenseStatus
from app.domains.expenses.schemas import (
    ExpenseCategoryOut,
    ExpenseCreate,
    ExpenseOut,
    ExpenseUpdate,
)

# Dois prefixos, um router só: `main.py` importa apenas `router` de cada domínio.
router = APIRouter(tags=["despesas"])
expenses_router = APIRouter(prefix="/expenses", tags=["despesas"])
categories_router = APIRouter(prefix="/expense-categories", tags=["despesas"])

_NAO_MANUAL = (
    "Esta despesa foi gerada por uma manutenção/multa. Edite o registro de origem."
)


def _get(db: Session, expense_id: UUID) -> Expense:
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise NotFound("Despesa não encontrada.")
    return expense


def _require_manual(expense: Expense) -> None:
    """Despesa gerada por manutenção/multa é reflexo, não fonte.

    Editá-la aqui deixaria o valor da despesa diferente do valor da manutenção que a criou —
    dois números para o mesmo fato, e nenhum deles confiável.
    """
    if expense.origin != ExpenseOrigin.manual:
        raise AppError(_NAO_MANUAL)


@categories_router.get("", response_model=list[ExpenseCategoryOut])
def list_categories(db: Db, _: CurrentUser):
    """Categorias são TABELA, não enum: o dono cria "pedágio" às 23h sem deploy."""
    stmt = (
        select(ExpenseCategory)
        .where(ExpenseCategory.is_active.is_(True))
        .order_by(ExpenseCategory.sort_order, ExpenseCategory.name)
    )
    return db.scalars(stmt).all()


@expenses_router.get("", response_model=list[ExpenseOut])
def list_expenses(
    db: Db,
    _: CurrentUser,
    vehicle_id: UUID | None = None,
    driver_id: UUID | None = None,
    category_id: int | None = None,
    status: ExpenseStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    """Despesas filtradas por COMPETÊNCIA (`competence_date`), não por pagamento.

    `paid_on` é nulo enquanto a despesa está pendente — filtrar por ele esconderia justamente
    as contas em aberto. (O regime de CAIXA vive no módulo de finanças, que usa `paid_on`.)
    """
    stmt = select(Expense)

    if vehicle_id:
        stmt = stmt.where(Expense.vehicle_id == vehicle_id)
    if driver_id:
        stmt = stmt.where(Expense.driver_id == driver_id)
    if category_id:
        stmt = stmt.where(Expense.category_id == category_id)
    if status:
        stmt = stmt.where(Expense.status == status)
    if date_from:
        stmt = stmt.where(Expense.competence_date >= date_from)
    if date_to:
        stmt = stmt.where(Expense.competence_date <= date_to)

    # `Expense.category` é lazy="joined": o nome da categoria vem junto, sem N+1.
    stmt = stmt.order_by(Expense.competence_date.desc(), Expense.created_at.desc())
    return db.scalars(stmt).all()


@expenses_router.post("", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense(data: ExpenseCreate, db: Db, _: CurrentUser):
    """Lançamento manual. `origin` é sempre `manual` aqui — as outras origens nascem no
    domínio delas (manutenção/multa), chamando `expenses.service.create_expense`."""
    category = service.require_category(db, data.category_id)

    expense = service.create_expense(
        db,
        vehicle_id=data.vehicle_id,
        category_code=category.code,
        amount=data.amount,
        competence_date=data.competence_date,
        driver_id=data.driver_id,
        supplier_name=data.supplier_name,
        description=data.description,
        paid_on=data.paid_on,
        status=data.status,
        origin=ExpenseOrigin.manual,
        odometer=data.odometer,
        document_number=data.document_number,
        notes=data.notes,
    )
    db.commit()
    return expense


@expenses_router.get("/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: UUID, db: Db, _: CurrentUser):
    return _get(db, expense_id)


@expenses_router.patch("/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: UUID, data: ExpenseUpdate, db: Db, _: CurrentUser):
    expense = _get(db, expense_id)
    _require_manual(expense)

    fields = data.model_dump(exclude_unset=True)

    if "vehicle_id" in fields:
        service.require_vehicle(db, fields["vehicle_id"])
    if "driver_id" in fields:
        service.require_driver(db, fields["driver_id"])
    if "category_id" in fields:
        service.require_category(db, fields["category_id"])

    for key, value in fields.items():
        setattr(expense, key, value)

    # Estado FINAL: o PATCH pode ter mexido só no status, só na data, ou em nenhum dos dois.
    service.validate_payment_state(expense.status, expense.paid_on)

    db.commit()
    return expense


@expenses_router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: UUID, db: Db, _: AdminUser):
    """Delete físico. Despesa não tem filhos e o log de auditoria guarda o que foi apagado."""
    expense = _get(db, expense_id)
    _require_manual(expense)

    db.delete(expense)
    db.commit()


router.include_router(expenses_router)
router.include_router(categories_router)
