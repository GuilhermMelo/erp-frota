"""Contrato de locação: cobrança semanal e encerramento da caução.

Duas coisas aqui não são óbvias e as duas vêm do MANIFESTO.md:

1. **A CAUÇÃO NÃO É RECEITA.** Ela mora em `contracts.deposit_amount` e é dinheiro que
   o dono segura e devolve. Só a parte efetivamente RETIDA no encerramento vira receita
   (categoria `caucao_retida`). Lançar a caução como receita infla o lucro do carro até
   o dia da devolução.

2. **A geração de cobrança é idempotente**, garantida por `UNIQUE(contract_id, period_start)`.
   Por isso ela pode rodar toda vez que o app abre — sem cron, sem job noturno e sem
   duplicar. A checagem prévia dos períodos já existentes é o mecanismo de verdade; a
   constraint é a rede de proteção (no Postgres um IntegrityError aborta a transação
   inteira, então não dá para usar try/except como estratégia).
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.domains.contracts.models import Contract, ContractStatus, DepositStatus
from app.domains.contracts.schemas import ContractCreate, ContractFinish, ContractUpdate
from app.domains.drivers.models import Driver
from app.domains.revenues import service as revenues_service
from app.domains.revenues.models import (
    PaymentMethod,
    Revenue,
    RevenueCategory,
    RevenueOrigin,
    RevenueStatus,
)
from app.domains.vehicles.models import Vehicle, VehicleStatus

ZERO = Decimal("0.00")

# Rede de proteção contra data de início digitada errada (1999 em vez de 2019): sem isso,
# um erro de digitação geraria milhares de cobranças que alguém teria de apagar na mão.
MAX_WEEKS = 520  # 10 anos


# ---------------------------------------------------------------- leitura


def get_contract(db: Session, contract_id: UUID) -> Contract:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise NotFound("Contrato não encontrado.")
    return contract


def list_contracts(
    db: Session,
    *,
    vehicle_id: UUID | None = None,
    driver_id: UUID | None = None,
    status: ContractStatus | None = None,
) -> list[Contract]:
    stmt = select(Contract)
    if vehicle_id:
        stmt = stmt.where(Contract.vehicle_id == vehicle_id)
    if driver_id:
        stmt = stmt.where(Contract.driver_id == driver_id)
    if status:
        stmt = stmt.where(Contract.status == status)
    stmt = stmt.order_by(Contract.start_date.desc(), Contract.code.desc())
    return list(db.scalars(stmt).unique().all())


def active_contract_for_vehicle(db: Session, vehicle_id: UUID) -> Contract | None:
    return db.scalar(
        select(Contract).where(
            Contract.vehicle_id == vehicle_id,
            Contract.status == ContractStatus.active,
        )
    )


# ---------------------------------------------------------------- escrita


def create_contract(db: Session, data: ContractCreate) -> Contract:
    vehicle = db.get(Vehicle, data.vehicle_id)
    if vehicle is None or vehicle.deleted_at is not None:
        raise NotFound("Veículo não encontrado.")

    driver = db.get(Driver, data.driver_id)
    if driver is None or driver.deleted_at is not None:
        raise NotFound("Motorista não encontrado.")

    if vehicle.status == VehicleStatus.sold:
        raise Conflict("Este veículo já foi vendido — não pode ser alugado.")

    # O índice parcial `uq_contracts_veiculo_ativo` também barra isso no banco. A checagem
    # aqui existe para o dono ler uma frase em português em vez de tomar um erro 500.
    em_uso = active_contract_for_vehicle(db, data.vehicle_id)
    if em_uso:
        raise Conflict(
            f"O veículo já tem um contrato ativo ({em_uso.code}). Encerre-o antes de criar outro."
        )

    contract = Contract(
        vehicle_id=data.vehicle_id,
        driver_id=data.driver_id,
        start_date=data.start_date,
        weekly_amount=data.weekly_amount,
        billing_weekday=data.billing_weekday,
        deposit_amount=data.deposit_amount,
        notes=data.notes,
        status=ContractStatus.active,
        deposit_status=DepositStatus.held,
    )
    db.add(contract)

    # Objeto carregado, atributo alterado — nunca bulk DML (CLAUDE.md, regra 3):
    # o listener de auditoria é cego a UPDATE em massa.
    vehicle.status = VehicleStatus.rented

    db.flush()  # precisa do id do contrato para gerar as cobranças
    generate_charges(db, contract)

    try:
        db.commit()
    except IntegrityError:
        # Corrida com outro cadastro do mesmo veículo: quem chegou primeiro ganhou o índice
        # parcial `uq_contracts_veiculo_ativo`. Melhor uma frase em português que um 500.
        db.rollback()
        raise Conflict("O veículo já tem um contrato ativo. Recarregue a tela.") from None

    return contract


def update_contract(db: Session, contract: Contract, data: ContractUpdate) -> Contract:
    fields = data.model_dump(exclude_unset=True)

    if contract.status != ContractStatus.active:
        raise Conflict("Contrato encerrado não pode ser alterado.")

    nova_data = fields.get("start_date")
    if nova_data is not None and nova_data != contract.start_date and _has_charges(db, contract.id):
        # Mudar o início mudaria a semana de cada cobrança — e as já geradas ficariam
        # órfãs, porque a idempotência é ancorada em period_start.
        raise Conflict(
            "Não é possível mudar a data de início: já existem cobranças geradas para este contrato."
        )

    for key, value in fields.items():
        setattr(contract, key, value)

    db.commit()
    return contract


def finish_contract(
    db: Session, contract: Contract, data: ContractFinish, *, user_id: UUID | None = None
) -> Contract:
    """Encerra o contrato e acerta a caução.

    A caução volta para o motorista; o que for RETIDO (avaria, semana em aberto, dívida)
    é a única parte que vira receita — categoria `caucao_retida`, já paga, porque o
    dinheiro já está com o dono desde o começo do contrato.
    """
    if contract.status != ContractStatus.active:
        raise Conflict("Este contrato já foi encerrado.")

    if data.end_date < contract.start_date:
        raise AppError("A data de encerramento não pode ser anterior ao início do contrato.")

    devolvido = Decimal(data.deposit_returned_amount)
    if devolvido > contract.deposit_amount:
        raise AppError(
            f"O valor devolvido da caução não pode passar de R$ {contract.deposit_amount} "
            "(o valor recebido como caução)."
        )

    # Gera o que faltar ANTES de encerrar: depois de `finished` o contrato sai da geração,
    # e a última semana que o motorista rodou nunca mais seria cobrada.
    generate_charges(db, contract, until=data.end_date)
    _cancel_charges_after(db, contract, data.end_date)

    contract.end_date = data.end_date
    contract.status = ContractStatus.finished
    contract.deposit_returned_amount = devolvido
    contract.deposit_status = DepositStatus.settled
    contract.deposit_settled_at = datetime.now(UTC)
    if data.notes is not None:
        contract.notes = data.notes

    retido = contract.deposit_amount - devolvido
    if retido > ZERO:
        # Só agora a caução (a parte retida) vira dinheiro do dono. Já entra PAGA: o valor
        # está com ele desde a assinatura, não há nada a receber.
        # origin=manual de propósito — `contract` é reservado à cobrança semanal.
        revenue = revenues_service.create_revenue(
            db,
            vehicle_id=contract.vehicle_id,
            driver_id=contract.driver_id,
            contract_id=contract.id,
            category=RevenueCategory.caucao_retida,
            amount=retido,
            description=f"Caução retida — contrato {contract.code}",
            competence_date=data.end_date,
            due_date=data.end_date,
            origin=RevenueOrigin.manual,
        )
        revenues_service.register_payment(
            db,
            revenue,
            amount=retido,
            paid_on=data.end_date,
            # `outro`: não houve transferência nova — o dinheiro já estava com o dono.
            method=PaymentMethod.outro,
            user_id=user_id,
        )

    vehicle = contract.vehicle or db.get(Vehicle, contract.vehicle_id)
    if vehicle is not None and vehicle.status != VehicleStatus.sold:
        vehicle.status = VehicleStatus.available

    db.commit()
    return contract


# ---------------------------------------------------------------- cobrança semanal


def week_due_date(period_start: date, billing_weekday: int) -> date:
    """O dia de cobrança dentro da semana que começa em `period_start`.

    A semana tem 7 dias, então o `billing_weekday` (0=segunda ... 6=domingo, igual ao
    `date.weekday()` do Python) cai exatamente uma vez dentro dela.
    """
    return period_start + timedelta(days=(billing_weekday - period_start.weekday()) % 7)


def generate_charges(
    db: Session, contract: Contract, *, until: date | None = None
) -> list[Revenue]:
    """Gera as cobranças semanais do contrato até HOJE. Idempotente.

    Não faz commit — quem chama decide o momento (assim a geração da frota inteira é
    uma transação só).
    """
    if contract.status != ContractStatus.active:
        return []

    # Nunca cobrar semana futura: uma semana só é cobrável depois de começar.
    limite = date.today()
    if until is not None:
        limite = min(limite, until)
    if contract.end_date is not None:
        limite = min(limite, contract.end_date)

    # A idempotência de verdade: pergunta ao banco quais semanas já existem e pula.
    # (Não dá para depender de try/except IntegrityError: no Postgres o erro aborta a
    # transação inteira e derrubaria as cobranças dos outros contratos junto.)
    ja_geradas = set(
        db.scalars(
            select(Revenue.period_start).where(
                Revenue.contract_id == contract.id,
                Revenue.period_start.is_not(None),
            )
        ).all()
    )

    novas: list[Revenue] = []
    period_start = contract.start_date
    for _ in range(MAX_WEEKS):
        if period_start > limite:
            break
        if period_start not in ja_geradas:
            # Nasce pelo service de receitas (ponto único onde uma receita nasce), já com
            # origin=contract + period_start/end — é o par que a UNIQUE protege.
            novas.append(
                revenues_service.create_revenue(
                    db,
                    vehicle_id=contract.vehicle_id,
                    driver_id=contract.driver_id,
                    contract_id=contract.id,
                    category=RevenueCategory.aluguel,
                    description=f"Aluguel semanal — contrato {contract.code}",
                    amount=contract.weekly_amount,
                    competence_date=period_start,
                    due_date=week_due_date(period_start, contract.billing_weekday),
                    origin=RevenueOrigin.contract,
                    period_start=period_start,
                    period_end=period_start + timedelta(days=6),
                )
            )
        period_start += timedelta(days=7)

    return novas


def generate_all_charges(db: Session) -> list[Revenue]:
    """Roda a geração para TODOS os contratos ativos. É o que o app chama ao abrir."""
    contratos = db.scalars(
        select(Contract).where(Contract.status == ContractStatus.active)
    ).unique().all()

    geradas: list[Revenue] = []
    for contract in contratos:
        geradas.extend(generate_charges(db, contract))

    db.commit()
    return geradas


# ---------------------------------------------------------------- interno


def _has_charges(db: Session, contract_id: UUID) -> bool:
    return (
        db.scalar(select(Revenue.id).where(Revenue.contract_id == contract_id).limit(1)) is not None
    )


def _cancel_charges_after(db: Session, contract: Contract, end_date: date) -> None:
    """Encerramento retroativo: cancela as cobranças de semanas que começam DEPOIS do fim.

    Acontece quando o contrato acabou há duas semanas e só agora foi encerrado no sistema:
    a geração automática já criou as semanas seguintes. Elas não são devidas — mas só as
    intocadas (pendentes, sem nenhum centavo pago) são canceladas. Cobrança com pagamento
    registrado é fato consumado e não se apaga.
    """
    pendentes = db.scalars(
        select(Revenue).where(
            Revenue.contract_id == contract.id,
            Revenue.origin == RevenueOrigin.contract,
            Revenue.status == RevenueStatus.pending,
            Revenue.paid_amount == ZERO,
            Revenue.period_start.is_not(None),
            Revenue.period_start > end_date,
        )
    ).all()

    for revenue in pendentes:
        revenue.status = RevenueStatus.canceled
        revenue.notes = "Cancelada no encerramento do contrato (semana posterior ao fim)."
