from datetime import date, timedelta

from app.core.tempo import hoje
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.domains.auth.deps import CurrentUser, Db
from app.domains.expenses.models import Expense, ExpenseStatus
from app.domains.finance import queries
from app.domains.finance.schemas import DashboardOut, MonthlyPointOut, VehicleResultOut
from app.domains.revenues.models import Revenue, RevenuePayment, RevenueStatus
from app.domains.vehicles.models import Vehicle, VehicleStatus

router = APIRouter(prefix="/finance", tags=["financeiro"])

ZERO = Decimal("0.00")
EM_ABERTO = [RevenueStatus.pending, RevenueStatus.partial]

# COBRANÇA EM ABERTO DE CARRO EXCLUÍDO NÃO É "A RECEBER".
#
# `/finance/fleet` e `/finance/vehicles/{id}` já ignoram o veículo soft-deletado (o segundo
# responde 404). Sem o mesmo filtro aqui, a tela inicial anunciava "a receber" e
# "inadimplência" de carros que sumiram da frota: o dono clicava no número, chegava na lista
# de cobranças e não conseguia abrir o veículo. Dois números sobre o mesmo dinheiro, um deles
# impossível de auditar.
#
# O caixa do mês (recebido/pago) NÃO leva este filtro de propósito: aquele dinheiro entrou e
# saiu de verdade, e apagar o carro não desfaz o extrato.
VEICULO_NA_FROTA = select(Vehicle.id).where(
    Vehicle.id == Revenue.vehicle_id, Vehicle.deleted_at.is_(None)
).exists()


def _money(value) -> Decimal:
    """Dinheiro é Decimal, ponto. `coalesce(sum(...), 0)` pode voltar int quando não há linhas."""
    return Decimal(value) if value is not None else ZERO


def _current_month(today: date) -> tuple[date, date]:
    """[primeiro dia do mês, primeiro dia do mês que vem) — meia-aberto, sem perder o dia 31."""
    start = today.replace(day=1)
    return start, (start + timedelta(days=32)).replace(day=1)


@router.get("/vehicles/{vehicle_id}", response_model=VehicleResultOut)
def vehicle_result(db: Db, _: CurrentUser, vehicle_id: UUID):
    """A CONTA DO VEÍCULO — a tela mais importante do produto.

        Lucro = receitas − despesas − valor_compra + valor_venda
    """
    row = queries.vehicle_result(db, vehicle_id)
    if row is None:
        raise NotFound("Veículo não encontrado.")

    out = dict(row)
    pb = queries.payback(
        db, vehicle_id, out["investment"], is_sold=out["sale_date"] is not None
    )
    out["payback_month"] = pb["month"]
    out["payback_months_elapsed"] = pb["months_elapsed"]
    out["payback_months_remaining"] = pb["months_remaining"]
    return out


@router.get("/fleet", response_model=list[VehicleResultOut])
def fleet_results(db: Db, _: CurrentUser):
    """Ranking da frota por lucro: qual carro vender e qual comprar de novo."""
    return [dict(row) for row in queries.fleet_results(db)]


@router.get("/monthly", response_model=list[MonthlyPointOut])
def monthly_series(db: Db, _: CurrentUser, vehicle_id: UUID | None = None):
    """Receita e despesa por mês (regime de caixa). Sem `vehicle_id`, a frota inteira."""
    return queries.monthly_series(db, vehicle_id)


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Db, _: CurrentUser):
    """Resumo da tela inicial: como está a frota e como está o mês."""
    today = hoje()
    month_start, next_month = _current_month(today)

    by_status = _vehicles_by_status(db)
    received = _money(
        db.scalar(
            select(func.coalesce(func.sum(RevenuePayment.amount), 0)).where(
                RevenuePayment.paid_on >= month_start, RevenuePayment.paid_on < next_month
            )
        )
    )
    paid = _money(
        db.scalar(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(
                Expense.status == ExpenseStatus.paid,
                Expense.paid_on >= month_start,
                Expense.paid_on < next_month,
            )
        )
    )
    receivable = _money(
        db.scalar(
            select(func.coalesce(func.sum(Revenue.amount - Revenue.paid_amount), 0)).where(
                Revenue.status.in_(EM_ABERTO), VEICULO_NA_FROTA
            )
        )
    )
    # Inadimplência derivada na hora da pergunta — sem estado armazenado, sem job noturno.
    overdue_total, overdue_count = db.execute(
        select(
            func.coalesce(func.sum(Revenue.amount - Revenue.paid_amount), 0),
            func.count(Revenue.id),
        ).where(Revenue.status.in_(EM_ABERTO), Revenue.due_date < today, VEICULO_NA_FROTA)
    ).one()

    return DashboardOut(
        month=month_start.strftime("%Y-%m"),
        vehicles_total=sum(by_status.values()),
        vehicles_by_status=by_status,
        revenue_received_month=received,
        expense_paid_month=paid,
        profit_month=received - paid,
        total_receivable=receivable,
        total_overdue=_money(overdue_total),
        overdue_count=overdue_count,
    )


def _vehicles_by_status(db: Session) -> dict[str, int]:
    # Todos os status sempre presentes (zerados): a tela não pode piscar por falta de chave.
    counts = {status.value: 0 for status in VehicleStatus}
    rows = db.execute(
        select(Vehicle.status, func.count(Vehicle.id))
        .where(Vehicle.deleted_at.is_(None))
        .group_by(Vehicle.status)
    ).all()
    for status, total in rows:
        counts[getattr(status, "value", status)] = total
    return counts
