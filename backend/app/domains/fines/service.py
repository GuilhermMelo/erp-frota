"""Multas — e por que a despesa é lançada SEMPRE (ver MANIFESTO.md).

    1. A multa chega           → registra, vinculada ao CARRO e (se souber) ao MOTORISTA.
    2. O dono paga             → gera a DESPESA do carro (origin='fine', categoria multas).
    3. O motorista reembolsa   → gera a RECEITA (categoria 'reembolso') ligada à multa.

O líquido (`net_cost = amount − reimbursed_amount`) dá ZERO sozinho quando o motorista
paga, e vira custo real do carro quando ele não paga. Registrar só as multas não
reembolsadas seria mais curto e perderia as duas coisas que importam: quanto já se pagou
de multa e quanto cada motorista deve.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.domains.drivers.models import Driver
from app.domains.files import service as files_service
from app.domains.expenses import service as expenses_service
from app.domains.expenses.models import Expense, ExpenseOrigin, ExpenseStatus
from app.domains.fines.models import Fine, FineStatus
from app.domains.fines.schemas import FineCreate, FinePay, FineOut, FineReimburse, FineUpdate
from app.domains.revenues import service as revenues_service
from app.domains.revenues.models import (
    Revenue,
    RevenueCategory,
    RevenueOrigin,
    RevenueStatus,
)
from app.domains.vehicles.models import Vehicle

ZERO = Decimal("0.00")
CATEGORY_CODE = "multas"


# ---------------------------------------------------------------- leitura


def get_fine(db: Session, fine_id: UUID) -> Fine:
    fine = db.get(Fine, fine_id)
    if fine is None:
        raise NotFound("Multa não encontrada.")
    return fine


def list_fines(
    db: Session,
    *,
    vehicle_id: UUID | None = None,
    driver_id: UUID | None = None,
    status: FineStatus | None = None,
) -> list[Fine]:
    stmt = select(Fine)
    if vehicle_id:
        stmt = stmt.where(Fine.vehicle_id == vehicle_id)
    if driver_id:
        stmt = stmt.where(Fine.driver_id == driver_id)
    if status:
        stmt = stmt.where(Fine.status == status)
    stmt = stmt.order_by(Fine.infraction_date.desc(), Fine.code.desc())
    return list(db.scalars(stmt).unique().all())


def reimbursed_totals(db: Session, fine_ids: list[UUID]) -> dict[UUID, Decimal]:
    """Quanto já foi reembolsado de cada multa — em UMA query, não uma por linha."""
    if not fine_ids:
        return {}
    rows = db.execute(
        select(Revenue.fine_id, func.coalesce(func.sum(Revenue.amount), 0))
        .where(
            Revenue.fine_id.in_(fine_ids),
            # Receita cancelada não é dinheiro que entrou.
            Revenue.status != RevenueStatus.canceled,
        )
        .group_by(Revenue.fine_id)
    ).all()
    return {fine_id: Decimal(total) for fine_id, total in rows}


def reimbursed_total(db: Session, fine_id: UUID) -> Decimal:
    return reimbursed_totals(db, [fine_id]).get(fine_id, ZERO)


def to_out(fine: Fine, reimbursed: Decimal) -> FineOut:
    out = FineOut.model_validate(fine)
    out.reimbursed_amount = reimbursed
    return out


def list_out(db: Session, fines: list[Fine]) -> list[FineOut]:
    totais = reimbursed_totals(db, [f.id for f in fines])
    return [to_out(f, totais.get(f.id, ZERO)) for f in fines]


def one_out(db: Session, fine: Fine) -> FineOut:
    return to_out(fine, reimbursed_total(db, fine.id))


# ---------------------------------------------------------------- escrita


def create_fine(db: Session, data: FineCreate) -> Fine:
    _get_vehicle(db, data.vehicle_id)
    if data.driver_id is not None:
        _get_driver(db, data.driver_id)

    fine = Fine(
        vehicle_id=data.vehicle_id,
        driver_id=data.driver_id,
        infraction_date=data.infraction_date,
        ait_number=data.ait_number,
        description=data.description,
        location=data.location,
        amount=data.amount,
        due_date=data.due_date,
        points=data.points,
        driver_indication_deadline=data.driver_indication_deadline,
        notes=data.notes,
        status=FineStatus.pending,
    )
    db.add(fine)
    db.commit()
    return fine


def update_fine(db: Session, fine: Fine, data: FineUpdate) -> Fine:
    fields = data.model_dump(exclude_unset=True)

    novo_status = fields.get("status")
    if novo_status == FineStatus.paid:
        raise Conflict(
            "Use POST /fines/{id}/pay para registrar o pagamento — a despesa do carro é "
            "gerada junto."
        )
    if novo_status is not None and fine.status == FineStatus.paid:
        # O CHECK do banco exige (status='paid') = (paid_on IS NOT NULL): cancelar uma
        # multa paga quebraria isso — e, pior, deixaria a despesa órfã no resultado do carro.
        raise Conflict("Multa já paga — não é possível mudar o status.")

    if "driver_id" in fields and fields["driver_id"] is not None:
        _get_driver(db, fields["driver_id"])

    for key, value in fields.items():
        setattr(fine, key, value)

    # Corrigiu o valor de uma multa já paga? A despesa do carro acompanha.
    _sync_expense(db, fine)

    db.commit()
    return fine


def pay_fine(db: Session, fine: Fine, data: FinePay) -> Fine:
    """Paga a multa e joga o custo no carro.

    A despesa entra SEMPRE, reembolsada ou não. É ela que preserva o rastro de quanto já
    se pagou de multa por veículo.
    """
    if fine.status == FineStatus.paid:
        raise Conflict(f"Esta multa já foi paga em {fine.paid_on:%d/%m/%Y}.")
    if fine.status == FineStatus.canceled:
        raise Conflict("Multa cancelada — não há o que pagar.")
    if data.paid_on < fine.infraction_date:
        raise AppError("A data de pagamento não pode ser anterior à data da infração.")

    fine.status = FineStatus.paid
    fine.paid_on = data.paid_on
    _sync_expense(db, fine)

    db.commit()
    return fine


def reimburse_fine(
    db: Session, fine: Fine, data: FineReimburse, *, user_id: UUID | None = None
) -> Fine:
    """O motorista devolveu o dinheiro: vira RECEITA do carro, já paga.

    Não muda o status da multa (ela continua paga — o dono pagou mesmo). Quem conta a
    história é `reimbursed_amount` / `net_cost`.
    """
    if fine.driver_id is None:
        raise AppError("Multa sem motorista vinculado — não há de quem cobrar.")
    if fine.status == FineStatus.canceled:
        raise Conflict("Multa cancelada — não há o que reembolsar.")

    valor = Decimal(data.amount)
    if valor > fine.amount:
        raise AppError(
            f"O reembolso (R$ {valor}) não pode ser maior que o valor da multa "
            f"(R$ {fine.amount})."
        )

    ja_reembolsado = reimbursed_total(db, fine.id)
    restante = fine.amount - ja_reembolsado
    if valor > restante:
        raise AppError(
            f"Esta multa já teve R$ {ja_reembolsado} reembolsados. O máximo que ainda "
            f"pode ser lançado é R$ {restante}."
        )

    revenue = revenues_service.create_revenue(
        db,
        vehicle_id=fine.vehicle_id,
        driver_id=fine.driver_id,
        fine_id=fine.id,
        category=RevenueCategory.reembolso,
        amount=valor,
        description=f"Reembolso da multa {fine.code}",
        competence_date=data.paid_on,
        due_date=data.paid_on,
        origin=RevenueOrigin.manual,
    )
    # O dinheiro já está na mão — a receita nasce PAGA.
    revenues_service.register_payment(
        db,
        revenue,
        amount=valor,
        paid_on=data.paid_on,
        method=data.method,
        user_id=user_id,
    )

    db.commit()
    return fine


def delete_fine(db: Session, fine: Fine) -> None:
    if db.scalar(select(Revenue.id).where(Revenue.fine_id == fine.id).limit(1)) is not None:
        raise Conflict(
            "Esta multa já tem reembolso lançado e não pode ser excluída. "
            "Cancele-a (status) ou estorne a receita antes."
        )

    # A despesa vinculada é apagada pelo ORM, e NÃO pelo ON DELETE CASCADE do FK.
    # O FK continua lá como rede de proteção, mas a cascata do banco não passa pelo ORM:
    # o listener de auditoria é cego a ela (CLAUDE.md, regra 3) e o log ficaria com um
    # buraco exatamente onde o custo do veículo mudou — a despesa some do resultado do
    # carro e ninguém sabe quem a apagou.
    expense = db.scalar(select(Expense).where(Expense.fine_id == fine.id))
    if expense is not None:
        db.delete(expense)

    # Os anexos (notificação da multa) não têm FK — nada cascateia. Sem isto, o arquivo
    # fica no disco e a linha no banco para sempre, sem dono e sem como listar.
    keys = files_service.delete_documents_for(db, "fine", fine.id)

    db.delete(fine)
    db.commit()
    files_service.purge_files(keys)


# ---------------------------------------------------------------- interno


def _get_vehicle(db: Session, vehicle_id: UUID) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.deleted_at is not None:
        raise NotFound("Veículo não encontrado.")
    return vehicle


def _get_driver(db: Session, driver_id: UUID) -> Driver:
    driver = db.get(Driver, driver_id)
    if driver is None or driver.deleted_at is not None:
        raise NotFound("Motorista não encontrado.")
    return driver


def _expense_description(fine: Fine) -> str:
    return f"Multa {fine.code} — {fine.description}"[:200]


def _sync_expense(db: Session, fine: Fine) -> None:
    """Mantém a despesa da multa alinhada. Idempotente por `Expense.fine_id`.

    Só age em multa PAGA: multa pendente ainda não custou nada ao carro. Se a despesa já
    existe (multa paga e depois corrigida), corrige a mesma linha em vez de criar outra —
    duas despesas para a mesma multa contariam o custo em dobro.
    """
    if fine.status != FineStatus.paid or fine.paid_on is None:
        return

    expense = db.scalar(select(Expense).where(Expense.fine_id == fine.id))

    if expense is None:
        expenses_service.create_expense(
            db,
            vehicle_id=fine.vehicle_id,
            # Sem o motorista aqui não dá para saber quanto cada um deve.
            driver_id=fine.driver_id,
            category_code=CATEGORY_CODE,
            amount=fine.amount,
            # A competência é o dia da INFRAÇÃO (o fato). O caixa é o paid_on.
            competence_date=fine.infraction_date,
            paid_on=fine.paid_on,
            status=ExpenseStatus.paid,
            origin=ExpenseOrigin.fine,
            fine_id=fine.id,
            description=_expense_description(fine),
            document_number=fine.ait_number,
        )
        return

    expense.amount = fine.amount
    expense.driver_id = fine.driver_id
    expense.description = _expense_description(fine)
    expense.document_number = fine.ait_number
    expense.competence_date = fine.infraction_date
    if expense.status == ExpenseStatus.paid:
        expense.paid_on = fine.paid_on
