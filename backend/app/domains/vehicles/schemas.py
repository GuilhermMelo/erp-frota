import re
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, condecimal, field_validator, model_validator

from app.domains.vehicles.models import FuelType, VehicleStatus

# Dinheiro é SEMPRE Decimal (ARQUITETURA.md, regra 1). Espelha o Numeric(12,2) do banco.
Money = condecimal(max_digits=12, decimal_places=2, gt=0)
# Compra e valor de mercado aceitam ZERO: o CHECK do banco é `>= 0` e existe carro recebido
# de graça — ARQUITETURA.md lista `purchase_price = 0` como caso previsto (o ROI já trata a
# divisão por zero). Barrar aqui tornaria impossível cadastrar esse carro.
MoneyOrZero = condecimal(max_digits=12, decimal_places=2, ge=0)

_NOT_ALNUM = re.compile(r"[^A-Za-z0-9]")


class _VehicleFields(BaseModel):
    """Normalização compartilhada entre criação e edição."""

    @field_validator("renavam", "chassi", mode="before", check_fields=False)
    @classmethod
    def _empty_to_null(cls, v):
        """String vazia vira NULL.

        RENAVAM e chassi são UNIQUE e opcionais. Um formulário que manda `""` (o padrão de
        um input HTML não preenchido) gravaria a string vazia — e o SEGUNDO veículo sem
        RENAVAM violaria o índice UNIQUE, virando HTTP 500. No Postgres, NULLs são
        distintos entre si; strings vazias não.
        """
        if isinstance(v, str) and not v.strip():
            return None
        return v.strip() if isinstance(v, str) else v

    @field_validator("plate", mode="before", check_fields=False)
    @classmethod
    def _normalize_plate(cls, v):
        """`abc-1234` / `ABC 1234` → `ABC1234`.

        A placa é UNIQUE: sem normalizar, o mesmo carro entra duas vezes (uma com hífen,
        outra sem) e o lucro dele sai dividido entre dois registros.
        """
        if not isinstance(v, str):
            return v
        plate = _NOT_ALNUM.sub("", v).upper()
        if not 7 <= len(plate) <= 8:
            raise ValueError("A placa deve ter 7 caracteres (ex.: ABC1D23 ou ABC1234).")
        return plate


class VehicleCreate(_VehicleFields):
    # `code` (CAR000001) é gerado por SEQUENCE no banco — não é aceito no input.
    plate: str
    renavam: str | None = Field(default=None, max_length=20)
    chassi: str | None = Field(default=None, max_length=30)

    brand: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=60)
    version: str | None = Field(default=None, max_length=80)
    manufacture_year: int = Field(ge=1900, le=2100)
    model_year: int = Field(ge=1900, le=2100)
    color: str | None = Field(default=None, max_length=30)
    fuel_type: FuelType = FuelType.flex

    purchase_date: date
    purchase_price: MoneyOrZero
    purchase_odometer: int = Field(default=0, ge=0)
    current_odometer: int = Field(default=0, ge=0)

    estimated_market_value: MoneyOrZero | None = None

    status: VehicleStatus = VehicleStatus.available
    notes: str | None = None

    # sale_price / sale_date não entram aqui: a venda é um evento de ciclo de vida e tem
    # endpoint próprio (POST /vehicles/{id}/sell).


# Colunas NOT NULL: aceitar `null` nelas no PATCH viraria IntegrityError (HTTP 500).
_REQUIRED = {
    "plate",
    "brand",
    "model",
    "manufacture_year",
    "model_year",
    "fuel_type",
    "purchase_date",
    "purchase_price",
    "purchase_odometer",
    "current_odometer",
    "status",
}


class VehicleUpdate(_VehicleFields):
    plate: str | None = None
    renavam: str | None = Field(default=None, max_length=20)
    chassi: str | None = Field(default=None, max_length=30)

    brand: str | None = Field(default=None, min_length=1, max_length=60)
    model: str | None = Field(default=None, min_length=1, max_length=60)
    version: str | None = Field(default=None, max_length=80)
    manufacture_year: int | None = Field(default=None, ge=1900, le=2100)
    model_year: int | None = Field(default=None, ge=1900, le=2100)
    color: str | None = Field(default=None, max_length=30)
    fuel_type: FuelType | None = None

    purchase_date: date | None = None
    purchase_price: MoneyOrZero | None = None
    purchase_odometer: int | None = Field(default=None, ge=0)
    current_odometer: int | None = Field(default=None, ge=0)

    estimated_market_value: MoneyOrZero | None = None

    status: VehicleStatus | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _no_null_on_required(self):
        empty = sorted(f for f in self.model_fields_set & _REQUIRED if getattr(self, f) is None)
        if empty:
            raise ValueError(f"Estes campos não podem ficar vazios: {', '.join(empty)}.")
        return self


class VehicleSell(BaseModel):
    """A venda fecha o ciclo de vida do carro: é o último fato do cálculo de lucro."""

    sale_price: Money
    sale_date: date


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    plate: str
    renavam: str | None
    chassi: str | None

    brand: str
    model: str
    version: str | None
    manufacture_year: int
    model_year: int
    color: str | None
    fuel_type: FuelType

    purchase_date: date
    purchase_price: Decimal
    purchase_odometer: int
    current_odometer: int

    sale_date: date | None
    sale_price: Decimal | None
    estimated_market_value: Decimal | None

    status: VehicleStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime
