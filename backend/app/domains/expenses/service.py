"""Regras de despesa — o ponto único por onde uma despesa nasce.

Manutenção e multa NÃO montam um `Expense` na mão: chamam `create_expense()` daqui com
`origin=maintenance/fine` e a categoria resolvida por `code`. Assim a despesa sempre nasce
com veículo validado e categoria certa, e o router de despesas consegue recusar a edição
dela (quem manda é o registro de origem).

Nenhuma função aqui dá commit: quem chama é dono da transação. É isso que permite a uma
manutenção criar sua despesa e, se algo falhar depois, tudo voltar atrás junto.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.domains.drivers.models import Driver
from app.domains.expenses.models import Expense, ExpenseCategory, ExpenseOrigin, ExpenseStatus
from app.domains.vehicles.models import Vehicle


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


def require_category(db: Session, category_id: int) -> ExpenseCategory:
    category = db.get(ExpenseCategory, category_id)
    if category is None:
        raise NotFound("Categoria de despesa não encontrada.")
    return category


def resolve_category(db: Session, code: str) -> ExpenseCategory:
    """Categoria por `code` estável (`manutencao`, `multas`...).

    Manutenção e multa referenciam a categoria por code, não por id: os ids são seriais e
    mudam entre bancos (dev, produção, restore) — o code, não.
    """
    category = db.scalar(select(ExpenseCategory).where(ExpenseCategory.code == code))
    if category is None:
        raise NotFound(f"Categoria de despesa '{code}' não encontrada.")
    return category


def validate_payment_state(status: ExpenseStatus, paid_on: date | None) -> None:
    """Espelha o CHECK `(status = 'paid') = (paid_on IS NOT NULL)`.

    Despesa paga sem data some do regime de caixa; pendente com data entra num mês em que
    não foi paga. O banco recusa as duas — aqui a recusa vem com texto legível.
    """
    if status == ExpenseStatus.paid and paid_on is None:
        raise AppError("Informe a data de pagamento para lançar a despesa como paga.")
    if status == ExpenseStatus.pending and paid_on is not None:
        raise AppError("Despesa pendente não pode ter data de pagamento. Marque-a como paga.")


def create_expense(
    db: Session,
    *,
    vehicle_id: UUID,
    category_code: str,
    amount: Decimal,
    competence_date: date,
    driver_id: UUID | None = None,
    supplier_name: str | None = None,
    description: str | None = None,
    paid_on: date | None = None,
    status: ExpenseStatus = ExpenseStatus.paid,
    origin: ExpenseOrigin = ExpenseOrigin.manual,
    maintenance_id: UUID | None = None,
    fine_id: UUID | None = None,
    odometer: int | None = None,
    document_number: str | None = None,
    notes: str | None = None,
) -> Expense:
    """Cria a despesa resolvendo a categoria por `code`. NÃO faz commit.

    Usada pelo router de despesas (origin=manual) e pelos domínios de manutenção e multa
    (origin=maintenance/fine), que passam o `maintenance_id`/`fine_id` para amarrar a
    despesa ao registro de origem.

    ATENÇÃO: o valor de COMPRA do carro nunca passa por aqui — ele mora em
    `vehicles.purchase_price`. Lançá-lo como despesa contaria o custo em dobro.
    """
    require_vehicle(db, vehicle_id)
    require_driver(db, driver_id)
    category = resolve_category(db, category_code)
    validate_payment_state(status, paid_on)

    expense = Expense(
        vehicle_id=vehicle_id,
        driver_id=driver_id,
        category_id=category.id,
        maintenance_id=maintenance_id,
        fine_id=fine_id,
        supplier_name=supplier_name,
        description=description,
        amount=amount,
        competence_date=competence_date,
        paid_on=paid_on,
        status=status,
        origin=origin,
        odometer=odometer,
        document_number=document_number,
        notes=notes,
    )
    db.add(expense)
    # Flush (não commit): a despesa já sai daqui com `id` e `code` preenchidos pelo banco,
    # para quem chamou poder amarrá-la ao registro de origem na mesma transação.
    db.flush()
    return expense
