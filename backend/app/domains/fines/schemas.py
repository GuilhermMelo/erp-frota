from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, condecimal

from app.domains.fines.models import FineStatus
from app.domains.revenues.models import PaymentMethod

# Dinheiro é SEMPRE Decimal — nunca float (ARQUITETURA.md, regra 1).
MoneyPositive = condecimal(max_digits=12, decimal_places=2, gt=0)


class VehicleBrief(BaseModel):
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


class FineCreate(BaseModel):
    vehicle_id: UUID
    # Nem sempre se sabe quem estava dirigindo. Sem motorista não há quem reembolse.
    driver_id: UUID | None = None
    infraction_date: date
    ait_number: str | None = Field(default=None, max_length=40)
    description: str = Field(min_length=2, max_length=200)
    location: str | None = Field(default=None, max_length=160)
    amount: MoneyPositive
    due_date: date | None = None
    points: int | None = Field(default=None, ge=0, le=20)
    driver_indication_deadline: date | None = None
    notes: str | None = None


class FineUpdate(BaseModel):
    """`status` só aceita pending/canceled — pagamento é POST /fines/{id}/pay.

    Pagar por PATCH pularia a geração da despesa do carro, e o custo da multa sumiria
    do resultado do veículo.
    """

    driver_id: UUID | None = None
    infraction_date: date | None = None
    ait_number: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, min_length=2, max_length=200)
    location: str | None = Field(default=None, max_length=160)
    amount: MoneyPositive | None = None
    due_date: date | None = None
    points: int | None = Field(default=None, ge=0, le=20)
    driver_indication_deadline: date | None = None
    status: FineStatus | None = None
    notes: str | None = None


class FinePay(BaseModel):
    paid_on: date


class FineReimburse(BaseModel):
    """O motorista devolveu o dinheiro da multa."""

    amount: MoneyPositive
    paid_on: date
    method: PaymentMethod = PaymentMethod.pix


class FineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    vehicle_id: UUID
    driver_id: UUID | None
    infraction_date: date
    ait_number: str | None
    description: str
    location: str | None
    amount: Decimal
    due_date: date | None
    points: int | None
    driver_indication_deadline: date | None
    status: FineStatus
    paid_on: date | None
    notes: str | None
    created_at: datetime
    vehicle: VehicleBrief | None = None
    driver: DriverBrief | None = None

    # Preenchido pelo service (soma das receitas de reembolso ligadas a esta multa).
    reimbursed_amount: Decimal = Decimal("0.00")

    @computed_field
    @property
    def net_cost(self) -> Decimal:
        """Quanto a multa custou DE VERDADE ao carro.

        Zera sozinho quando o motorista reembolsa tudo; vira custo real quando ele não
        reembolsa. É o número que o dono precisa ver (ver MANIFESTO.md).
        """
        return self.amount - self.reimbursed_amount
