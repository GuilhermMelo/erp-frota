from datetime import date
from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import Session, noload

from app.core.errors import AppError, NotFound
from app.domains.auth.deps import AdminUser, CurrentUser, Db
from app.domains.drivers.models import Driver
from app.domains.revenues import service
from app.domains.revenues.models import Revenue, RevenueOrigin, RevenueStatus
from app.domains.revenues.schemas import (
    ReceivableOut,
    RevenueCreate,
    RevenueDetailOut,
    RevenueOut,
    RevenuePaymentIn,
    RevenueUpdate,
)
from app.domains.vehicles.models import Vehicle

router = APIRouter(prefix="/revenues", tags=["receitas"])

_DE_CONTRATO = "Esta cobrança foi gerada por um contrato."

# Cobranças em aberto: é sobre elas que a inadimplência é calculada.
_OPEN = (RevenueStatus.pending, RevenueStatus.partial)


def _get(db: Session, revenue_id: UUID) -> Revenue:
    revenue = db.get(Revenue, revenue_id)
    if revenue is None:
        raise NotFound("Receita não encontrada.")
    return revenue


def _require_manual(revenue: Revenue) -> None:
    """Cobrança de contrato é reflexo do contrato, não um lançamento avulso."""
    if revenue.origin == RevenueOrigin.contract:
        raise AppError(_DE_CONTRATO)


def _detail(revenue: Revenue) -> RevenueDetailOut:
    out = RevenueDetailOut.model_validate(revenue)
    out.payments.sort(key=lambda p: p.paid_on)
    return out


@router.get("", response_model=list[RevenueOut])
def list_revenues(
    db: Db,
    _: CurrentUser,
    vehicle_id: UUID | None = None,
    driver_id: UUID | None = None,
    contract_id: UUID | None = None,
    status: RevenueStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    """Receitas por COMPETÊNCIA (`competence_date`) — a data do fato.

    (Vencimento e atraso são o assunto de `/revenues/receivables`; caixa recebido é o
    assunto do módulo de finanças, que soma `revenue_payments.paid_on`.)
    """
    stmt = select(Revenue).options(noload(Revenue.payments))

    if vehicle_id:
        stmt = stmt.where(Revenue.vehicle_id == vehicle_id)
    if driver_id:
        stmt = stmt.where(Revenue.driver_id == driver_id)
    if contract_id:
        stmt = stmt.where(Revenue.contract_id == contract_id)
    if status:
        stmt = stmt.where(Revenue.status == status)
    if date_from:
        stmt = stmt.where(Revenue.competence_date >= date_from)
    if date_to:
        stmt = stmt.where(Revenue.competence_date <= date_to)

    stmt = stmt.order_by(Revenue.competence_date.desc(), Revenue.due_date.desc())
    return db.scalars(stmt).all()


# ATENÇÃO: esta rota precisa vir ANTES de /{revenue_id}, senão "receivables" é lido como um
# UUID de receita e o endpoint responde 422 para sempre.
@router.get("/receivables", response_model=list[ReceivableOut])
def list_receivables(db: Db, _: CurrentUser, only_overdue: bool = False):
    """INADIMPLÊNCIA — quem te deve, quanto, e há quantos dias.

    O atraso é DERIVADO aqui, na consulta: `status IN (pending, partial) AND due_date < hoje`.
    Não existe status 'overdue' no banco de propósito — estado armazenado precisaria de um job
    noturno e estaria errado toda manhã antes de ele rodar.
    """
    today = date.today()

    stmt = (
        select(Revenue, Vehicle.plate, Driver.full_name)
        .join(Vehicle, Vehicle.id == Revenue.vehicle_id)
        .outerjoin(Driver, Driver.id == Revenue.driver_id)
        .options(noload(Revenue.payments))
        .where(Revenue.status.in_(_OPEN))
        .order_by(Revenue.due_date)
    )
    if only_overdue:
        stmt = stmt.where(Revenue.due_date < today)

    return [
        ReceivableOut(
            id=revenue.id,
            code=revenue.code,
            vehicle_id=revenue.vehicle_id,
            vehicle_plate=plate,
            driver_id=revenue.driver_id,
            driver_name=driver_name,
            contract_id=revenue.contract_id,
            category=revenue.category,
            description=revenue.description,
            amount=revenue.amount,
            paid_amount=revenue.paid_amount,
            saldo=revenue.amount - revenue.paid_amount,
            # Só conta atraso; adiantado não é "-3 dias de atraso", é zero.
            dias_em_atraso=max((today - revenue.due_date).days, 0),
            competence_date=revenue.competence_date,
            due_date=revenue.due_date,
            status=revenue.status,
        )
        for revenue, plate, driver_name in db.execute(stmt).all()
    ]


@router.post("", response_model=RevenueDetailOut, status_code=status.HTTP_201_CREATED)
def create_revenue(data: RevenueCreate, db: Db, user: CurrentUser):
    """Cria a receita. Com `pay_now` (default), já registra o recebimento integral.

    É o caminho comum — "recebi R$ 800 hoje". Por baixo continua sendo uma conta a receber
    que nasceu e foi quitada no mesmo instante; o operador não vê a maquinaria.
    """
    revenue = service.create_revenue(
        db,
        vehicle_id=data.vehicle_id,
        driver_id=data.driver_id,
        category=data.category,
        description=data.description,
        amount=data.amount,
        competence_date=data.competence_date,
        due_date=data.due_date,
        notes=data.notes,
    )

    if data.pay_now:
        service.register_payment(
            db,
            revenue,
            amount=revenue.amount,
            paid_on=data.paid_on,
            method=data.method,
            user_id=user.id,
        )

    db.commit()
    return _detail(revenue)


@router.post(
    "/{revenue_id}/payments",
    response_model=RevenueDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def add_payment(revenue_id: UUID, data: RevenuePaymentIn, db: Db, user: CurrentUser):
    """Recebimento parcial ou total. `paid_amount` e `status` da receita saem recalculados.

    Funciona para cobrança de contrato também: receber não é editar.
    """
    revenue = _get(db, revenue_id)

    service.register_payment(
        db,
        revenue,
        amount=data.amount,
        paid_on=data.paid_on,
        method=data.method,
        user_id=user.id,
        receipt_ref=data.receipt_ref,
    )

    db.commit()
    return _detail(revenue)


@router.get("/{revenue_id}", response_model=RevenueDetailOut)
def get_revenue(revenue_id: UUID, db: Db, _: CurrentUser):
    return _detail(_get(db, revenue_id))


@router.patch("/{revenue_id}", response_model=RevenueDetailOut)
def update_revenue(revenue_id: UUID, data: RevenueUpdate, db: Db, _: CurrentUser):
    revenue = _get(db, revenue_id)
    _require_manual(revenue)

    fields = data.model_dump(exclude_unset=True)

    if "driver_id" in fields:
        service.require_driver(db, fields["driver_id"])

    if "amount" in fields:
        service.validate_new_amount(revenue, fields["amount"])

    for key, value in fields.items():
        setattr(revenue, key, value)

    if "amount" in fields:
        # Mudou o valor devido: quem estava `partial` pode ter virado `paid`.
        service.recalculate(revenue)

    db.commit()
    return _detail(revenue)


@router.delete("/{revenue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_revenue(revenue_id: UUID, db: Db, _: AdminUser):
    """Apaga a cobrança e, em cascata, os pagamentos dela.

    Isso mexe no lucro do veículo — por isso é ação de administrador. Os pagamentos são
    carregados e removidos pelo ORM (delete-orphan), não por um DELETE em massa: assim a
    auditoria registra cada linha que sumiu.
    """
    revenue = _get(db, revenue_id)
    _require_manual(revenue)

    db.delete(revenue)
    db.commit()
