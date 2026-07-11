"""Manutenção: histórico simples + a despesa que ela gera.

Regra do produto: quem lança a manutenção NÃO digita o valor de novo na tela de despesas.
Salvar a manutenção CRIA a despesa (`origin='maintenance'`, categoria `manutencao`), e
editar a manutenção corrige a mesma despesa. Ela é encontrada por `Expense.maintenance_id`.
Apagar a manutenção derruba a despesa por CASCADE do FK.

FORA DE ESCOPO (decidido, não reintroduzir): plano preventivo, lembrete de revisão,
"próxima troca". `odometer` e `performed_on` já guardam o que esse cálculo pediria um dia.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.domains.expenses import service as expenses_service
from app.domains.expenses.models import Expense, ExpenseOrigin, ExpenseStatus
from app.domains.files import service as files_service
from app.domains.maintenances.models import Maintenance
from app.domains.maintenances.schemas import MaintenanceCreate, MaintenanceUpdate
from app.domains.vehicles.models import Vehicle

CATEGORY_CODE = "manutencao"


def get_maintenance(db: Session, maintenance_id: UUID) -> Maintenance:
    maintenance = db.get(Maintenance, maintenance_id)
    if maintenance is None:
        raise NotFound("Manutenção não encontrada.")
    return maintenance


def list_maintenances(db: Session, *, vehicle_id: UUID | None = None) -> list[Maintenance]:
    stmt = select(Maintenance)
    if vehicle_id:
        stmt = stmt.where(Maintenance.vehicle_id == vehicle_id)
    stmt = stmt.order_by(Maintenance.performed_on.desc(), Maintenance.code.desc())
    return list(db.scalars(stmt).unique().all())


def create_maintenance(db: Session, data: MaintenanceCreate) -> Maintenance:
    vehicle = _get_vehicle(db, data.vehicle_id)

    maintenance = Maintenance(
        vehicle_id=data.vehicle_id,
        kind=data.kind,
        description=data.description,
        supplier_name=data.supplier_name,
        amount=data.amount,
        performed_on=data.performed_on,
        odometer=data.odometer,
        notes=data.notes,
    )
    db.add(maintenance)
    db.flush()  # precisa do id para ligar a despesa (Expense.maintenance_id)

    _sync_expense(db, maintenance)
    _bump_odometer(vehicle, maintenance.odometer)

    db.commit()
    return maintenance


def update_maintenance(
    db: Session, maintenance: Maintenance, data: MaintenanceUpdate
) -> Maintenance:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(maintenance, key, value)

    # A despesa é a mesma linha, corrigida — não uma segunda despesa.
    _sync_expense(db, maintenance)

    vehicle = maintenance.vehicle or db.get(Vehicle, maintenance.vehicle_id)
    if vehicle is not None:
        _bump_odometer(vehicle, maintenance.odometer)

    db.commit()
    return maintenance


def delete_maintenance(db: Session, maintenance: Maintenance) -> None:
    # A despesa vinculada é apagada pelo ORM, e NÃO pelo ON DELETE CASCADE do FK.
    # O FK continua lá como rede de proteção, mas a cascata do banco não passa pelo ORM:
    # o listener de auditoria é cego a ela (CLAUDE.md, regra 3) e o log ficaria com um
    # buraco exatamente onde o custo do veículo mudou.
    expense = db.scalar(select(Expense).where(Expense.maintenance_id == maintenance.id))
    if expense is not None:
        db.delete(expense)

    # Os anexos (nota fiscal) não têm FK — nada cascateia. Sem isto, o arquivo fica no
    # disco e a linha no banco para sempre, sem dono e sem como listar.
    keys = files_service.delete_documents_for(db, "maintenance", maintenance.id)

    db.delete(maintenance)
    db.commit()
    files_service.purge_files(keys)


# ---------------------------------------------------------------- interno


def _get_vehicle(db: Session, vehicle_id: UUID) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.deleted_at is not None:
        raise NotFound("Veículo não encontrado.")
    return vehicle


def _bump_odometer(vehicle: Vehicle, odometer: int) -> None:
    """A quilometragem só anda para frente.

    Uma manutenção antiga lançada depois de uma recente não pode fazer o hodômetro do
    carro voltar — isso corromperia o custo por km, que divide por (atual − compra).
    Objeto carregado, atributo alterado: nada de bulk DML (CLAUDE.md, regra 3).
    """
    if odometer > vehicle.current_odometer:
        vehicle.current_odometer = odometer


def _expense_description(maintenance: Maintenance) -> str:
    return f"Manutenção — {maintenance.kind}"[:200]


def _sync_expense(db: Session, maintenance: Maintenance) -> None:
    """Cria, corrige ou remove a despesa da manutenção. Idempotente por `maintenance_id`.

    Manutenção de valor ZERO (garantia, cortesia) não gera despesa: `expenses` exige
    `amount > 0` no banco, e uma despesa de R$ 0,00 não é um fato financeiro.
    """
    expense = db.scalar(select(Expense).where(Expense.maintenance_id == maintenance.id))

    if maintenance.amount <= 0:
        if expense is not None:
            db.delete(expense)
        return

    if expense is None:
        expenses_service.create_expense(
            db,
            vehicle_id=maintenance.vehicle_id,
            category_code=CATEGORY_CODE,
            amount=maintenance.amount,
            competence_date=maintenance.performed_on,
            paid_on=maintenance.performed_on,
            status=ExpenseStatus.paid,
            origin=ExpenseOrigin.maintenance,
            maintenance_id=maintenance.id,
            supplier_name=maintenance.supplier_name,
            description=_expense_description(maintenance),
            odometer=maintenance.odometer,
        )
        return

    expense.amount = maintenance.amount
    expense.supplier_name = maintenance.supplier_name
    expense.description = _expense_description(maintenance)
    expense.competence_date = maintenance.performed_on
    expense.odometer = maintenance.odometer
    # O CHECK do banco exige (status='paid') = (paid_on IS NOT NULL). Se alguém deixou a
    # despesa pendente na tela de despesas, respeita-se isso.
    if expense.status == ExpenseStatus.paid:
        expense.paid_on = maintenance.performed_on
