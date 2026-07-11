from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, condecimal

# Dinheiro é SEMPRE Decimal — nunca float (CLAUDE.md, regra 1).
# >= 0 e não > 0: serviço em garantia custa zero e mesmo assim vai para o histórico.
MoneyNonNegative = condecimal(max_digits=12, decimal_places=2, ge=0)


class VehicleBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    plate: str
    brand: str
    model: str


class MaintenanceCreate(BaseModel):
    vehicle_id: UUID
    # Texto livre ("troca de óleo", "pastilhas de freio") — enum aqui só engessaria.
    kind: str = Field(min_length=2, max_length=60)
    description: str | None = None
    supplier_name: str | None = Field(default=None, max_length=120)
    amount: MoneyNonNegative
    performed_on: date
    odometer: int = Field(ge=0)
    notes: str | None = None


class MaintenanceUpdate(BaseModel):
    """O veículo não é editável: a despesa vinculada já está no resultado daquele carro."""

    kind: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = None
    supplier_name: str | None = Field(default=None, max_length=120)
    amount: MoneyNonNegative | None = None
    performed_on: date | None = None
    odometer: int | None = Field(default=None, ge=0)
    notes: str | None = None


class MaintenanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    vehicle_id: UUID
    kind: str
    description: str | None
    supplier_name: str | None
    amount: Decimal
    performed_on: date
    odometer: int
    notes: str | None
    created_at: datetime
    vehicle: VehicleBrief | None = None
