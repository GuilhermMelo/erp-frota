from uuid import UUID

from fastapi import APIRouter, status

from app.domains.auth.deps import AdminUser, CurrentUser, Db
from app.domains.maintenances import service
from app.domains.maintenances.schemas import (
    MaintenanceCreate,
    MaintenanceOut,
    MaintenanceUpdate,
)

router = APIRouter(prefix="/maintenances", tags=["manutenções"])


@router.get("", response_model=list[MaintenanceOut])
def list_maintenances(db: Db, _: CurrentUser, vehicle_id: UUID | None = None):
    return service.list_maintenances(db, vehicle_id=vehicle_id)


@router.post("", response_model=MaintenanceOut, status_code=status.HTTP_201_CREATED)
def create_maintenance(data: MaintenanceCreate, db: Db, _: CurrentUser):
    """Salva a manutenção e gera a DESPESA do carro — o valor não é digitado duas vezes."""
    return service.create_maintenance(db, data)


@router.get("/{maintenance_id}", response_model=MaintenanceOut)
def get_maintenance(maintenance_id: UUID, db: Db, _: CurrentUser):
    return service.get_maintenance(db, maintenance_id)


@router.patch("/{maintenance_id}", response_model=MaintenanceOut)
def update_maintenance(
    maintenance_id: UUID, data: MaintenanceUpdate, db: Db, _: CurrentUser
):
    """Corrige a manutenção e a despesa vinculada na mesma operação."""
    maintenance = service.get_maintenance(db, maintenance_id)
    return service.update_maintenance(db, maintenance, data)


@router.delete("/{maintenance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_maintenance(maintenance_id: UUID, db: Db, _: AdminUser):
    """Apaga a manutenção e, por CASCADE, a despesa que ela gerou.

    Só admin: some dinheiro do resultado do veículo.
    """
    maintenance = service.get_maintenance(db, maintenance_id)
    service.delete_maintenance(db, maintenance)
