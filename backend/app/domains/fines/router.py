from uuid import UUID

from fastapi import APIRouter, status

from app.domains.auth.deps import AdminUser, CurrentUser, Db
from app.domains.fines import service
from app.domains.fines.models import FineStatus
from app.domains.fines.schemas import (
    FineCreate,
    FineOut,
    FinePay,
    FineReimburse,
    FineUpdate,
)

router = APIRouter(prefix="/fines", tags=["multas"])


@router.get("", response_model=list[FineOut])
def list_fines(
    db: Db,
    _: CurrentUser,
    vehicle_id: UUID | None = None,
    driver_id: UUID | None = None,
    status: FineStatus | None = None,
):
    """Lista as multas com `reimbursed_amount` e `net_cost` (o custo real para o carro)."""
    fines = service.list_fines(db, vehicle_id=vehicle_id, driver_id=driver_id, status=status)
    return service.list_out(db, fines)


@router.post("", response_model=FineOut, status_code=status.HTTP_201_CREATED)
def create_fine(data: FineCreate, db: Db, _: CurrentUser):
    fine = service.create_fine(db, data)
    return service.one_out(db, fine)


@router.get("/{fine_id}", response_model=FineOut)
def get_fine(fine_id: UUID, db: Db, _: CurrentUser):
    fine = service.get_fine(db, fine_id)
    return service.one_out(db, fine)


@router.patch("/{fine_id}", response_model=FineOut)
def update_fine(fine_id: UUID, data: FineUpdate, db: Db, _: CurrentUser):
    fine = service.get_fine(db, fine_id)
    fine = service.update_fine(db, fine, data)
    return service.one_out(db, fine)


@router.post("/{fine_id}/pay", response_model=FineOut)
def pay_fine(fine_id: UUID, data: FinePay, db: Db, _: CurrentUser):
    """Registra o pagamento da multa e gera a DESPESA do veículo (categoria multas)."""
    fine = service.get_fine(db, fine_id)
    fine = service.pay_fine(db, fine, data)
    return service.one_out(db, fine)


@router.post("/{fine_id}/reimburse", response_model=FineOut)
def reimburse_fine(fine_id: UUID, data: FineReimburse, db: Db, user: CurrentUser):
    """O motorista devolveu o dinheiro: gera a RECEITA de reembolso, já paga."""
    fine = service.get_fine(db, fine_id)
    fine = service.reimburse_fine(db, fine, data, user_id=user.id)
    return service.one_out(db, fine)


@router.delete("/{fine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fine(fine_id: UUID, db: Db, _: AdminUser):
    """Apaga a multa e, por CASCADE, a despesa dela. Bloqueado se já houve reembolso."""
    fine = service.get_fine(db, fine_id)
    service.delete_fine(db, fine)
