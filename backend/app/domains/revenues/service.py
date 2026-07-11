"""Regras da conta a receber — o coração financeiro do produto.

O contrato desta camada, em uma frase: **`paid_amount` e `status` são CONSEQUÊNCIA dos
pagamentos, nunca entrada do usuário.** Toda vez que um pagamento entra, os dois são
recalculados a partir da soma real de `revenue.payments`. Ninguém "marca como pago".

Nenhuma função aqui usa bulk DML (CLAUDE.md, regra 3): o listener de auditoria é cego a
`session.execute(update(...))` e o log ficaria com buraco justo onde o dinheiro se move.
Carrega-se o objeto e altera-se o atributo.

Nenhuma função aqui dá commit: quem chama é dono da transação.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.domains.drivers.models import Driver
from app.domains.revenues.models import (
    PaymentMethod,
    Revenue,
    RevenueCategory,
    RevenueOrigin,
    RevenuePayment,
    RevenueStatus,
)
from app.domains.vehicles.models import Vehicle

ZERO = Decimal("0.00")


def _brl(value: Decimal) -> str:
    """1234.5 → "1.234,50". Mensagem de erro sobre dinheiro tem que sair legível."""
    integer, _, cents = f"{value:.2f}".partition(".")
    return f"{f'{int(integer):,}'.replace(',', '.')},{cents}"


def require_vehicle(db: Session, vehicle_id: UUID) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.deleted_at is not None:
        raise NotFound("Veículo não encontrado.")
    return vehicle


def require_driver(db: Session, driver_id: UUID | None) -> Driver | None:
    if driver_id is None:
        return None
    driver = db.get(Driver, driver_id)
    if driver is None or driver.deleted_at is not None:
        raise NotFound("Motorista não encontrado.")
    return driver


def paid_total(revenue: Revenue) -> Decimal:
    """Soma dos pagamentos REAIS.

    Não usa `revenue.paid_amount`: aquele campo é uma denormalização mantida por este
    módulo (para a tela de inadimplência não precisar agregar `revenue_payments` a cada
    consulta). Se um dia os dois divergirem, o certo é o que está em `revenue_payments` —
    é lá que o dinheiro está registrado.
    """
    return sum((p.amount for p in revenue.payments), ZERO)


def outstanding(revenue: Revenue) -> Decimal:
    """Saldo devedor: o que falta receber."""
    return revenue.amount - paid_total(revenue)


def recalculate(revenue: Revenue) -> None:
    """Reescreve `paid_amount` e `status` a partir da soma dos pagamentos."""
    if revenue.status == RevenueStatus.canceled:
        # Cobrança cancelada não volta a ficar "em aberto" sozinha.
        return

    paid = paid_total(revenue)
    revenue.paid_amount = paid

    if paid >= revenue.amount:
        revenue.status = RevenueStatus.paid
    elif paid > ZERO:
        revenue.status = RevenueStatus.partial
    else:
        revenue.status = RevenueStatus.pending


def validate_new_amount(revenue: Revenue, amount: Decimal) -> None:
    """O valor da cobrança não pode cair abaixo do que já foi recebido.

    Além de não fazer sentido ("devia 800, recebi 500, agora devia 300"), o banco recusaria:
    CHECK `paid_amount <= amount`.
    """
    paid = paid_total(revenue)
    if amount < paid:
        raise AppError(f"O valor não pode ficar abaixo do total já recebido (R$ {_brl(paid)}).")


def create_revenue(
    db: Session,
    *,
    vehicle_id: UUID,
    amount: Decimal,
    competence_date: date,
    due_date: date,
    category: RevenueCategory = RevenueCategory.aluguel,
    driver_id: UUID | None = None,
    contract_id: UUID | None = None,
    fine_id: UUID | None = None,
    description: str | None = None,
    origin: RevenueOrigin = RevenueOrigin.manual,
    period_start: date | None = None,
    period_end: date | None = None,
    notes: str | None = None,
) -> Revenue:
    """Cria a cobrança em aberto (`pending`). NÃO faz commit.

    Usada pelo router (origin=manual) e pelo domínio de contratos, que passa
    `origin=contract` + `contract_id` + `period_start/end` — a UNIQUE(contract_id,
    period_start) torna a geração semanal idempotente.

    ATENÇÃO (CLAUDE.md, regra 4): não existe receita de "venda de veículo" nem de "caução".
    A venda mora em `vehicles.sale_price` e a caução em `contracts.deposit_amount`. Criar
    receita para elas contaria o lucro do carro em dobro.
    """
    require_vehicle(db, vehicle_id)
    require_driver(db, driver_id)

    revenue = Revenue(
        vehicle_id=vehicle_id,
        driver_id=driver_id,
        contract_id=contract_id,
        fine_id=fine_id,
        category=category,
        description=description,
        amount=amount,
        paid_amount=ZERO,
        competence_date=competence_date,
        due_date=due_date,
        status=RevenueStatus.pending,
        origin=origin,
        period_start=period_start,
        period_end=period_end,
        notes=notes,
    )
    db.add(revenue)
    # Flush (não commit): a receita já sai daqui com `id` e `code` do banco, para receber
    # um pagamento na mesma transação.
    db.flush()
    return revenue


def register_payment(
    db: Session,
    revenue: Revenue,
    *,
    amount: Decimal,
    paid_on: date,
    method: PaymentMethod = PaymentMethod.pix,
    user_id: UUID | None = None,
    receipt_ref: str | None = None,
) -> RevenuePayment:
    """Registra um recebimento e RECALCULA `paid_amount` e `status` da receita.

    O pagamento é anexado pela relação (`revenue.payments.append`), não por um INSERT solto:
    é assim que o ORM — e portanto o log de auditoria — enxerga o dinheiro entrando.
    """
    if revenue.status == RevenueStatus.canceled:
        raise AppError("Esta cobrança foi cancelada e não aceita pagamento.")

    saldo = outstanding(revenue)

    if saldo <= ZERO:
        raise AppError("Esta cobrança já está totalmente paga.")
    if amount > saldo:
        raise AppError(f"Pagamento maior que o valor em aberto (R$ {_brl(saldo)}).")

    payment = RevenuePayment(
        amount=amount,
        paid_on=paid_on,
        method=method,
        receipt_ref=receipt_ref,
        created_by_user_id=user_id,
    )
    revenue.payments.append(payment)

    recalculate(revenue)

    # Um único flush: o listener registra o pagamento criado E a receita atualizada.
    db.flush()
    return payment
