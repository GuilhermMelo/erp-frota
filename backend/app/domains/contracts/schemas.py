from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, condecimal

from app.domains.contracts.models import ContractStatus, DepositStatus

# Dinheiro é SEMPRE Decimal — nunca float (CLAUDE.md, regra 1).
MoneyPositive = condecimal(max_digits=12, decimal_places=2, gt=0)
MoneyNonNegative = condecimal(max_digits=12, decimal_places=2, ge=0)


class VehicleBrief(BaseModel):
    """O suficiente para a tela mostrar 'ABC1D23 — Fiat Cronos' sem uma segunda chamada."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    plate: str
    brand: str
    model: str


class DriverBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    full_name: str


class ContractCreate(BaseModel):
    vehicle_id: UUID
    driver_id: UUID
    start_date: date
    weekly_amount: MoneyPositive
    billing_weekday: int = Field(default=0, ge=0, le=6, description="0 = segunda ... 6 = domingo")
    deposit_amount: MoneyNonNegative = Decimal("0.00")
    notes: str | None = None


class ContractUpdate(BaseModel):
    """Veículo, motorista e status NÃO são editáveis.

    Trocar o carro ou o motorista no meio do contrato é, na vida real, outro contrato —
    e as cobranças já geradas ficariam apontando para a pessoa errada. Encerre e crie
    um novo. O status muda por /finish, não por PATCH.
    """

    weekly_amount: MoneyPositive | None = None
    billing_weekday: int | None = Field(default=None, ge=0, le=6)
    deposit_amount: MoneyNonNegative | None = None
    # Só enquanto o contrato não tiver nenhuma cobrança gerada (o service barra).
    start_date: date | None = None
    notes: str | None = None


class ContractFinish(BaseModel):
    end_date: date
    # Quanto da caução voltou para o motorista. O que sobrar (retido) vira receita.
    deposit_returned_amount: MoneyNonNegative = Decimal("0.00")
    notes: str | None = None


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    vehicle_id: UUID
    driver_id: UUID
    start_date: date
    end_date: date | None
    weekly_amount: Decimal
    billing_weekday: int
    deposit_amount: Decimal
    deposit_status: DepositStatus
    deposit_returned_amount: Decimal
    deposit_settled_at: datetime | None
    status: ContractStatus
    notes: str | None
    created_at: datetime
    vehicle: VehicleBrief | None = None
    driver: DriverBrief | None = None


class ChargesGeneratedOut(BaseModel):
    """Resposta da geração de cobranças. O frontend chama isso ao abrir o app."""

    geradas: int
