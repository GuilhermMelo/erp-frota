from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, condecimal, model_validator

from app.domains.revenues.models import (
    PaymentMethod,
    RevenueCategory,
    RevenueOrigin,
    RevenueStatus,
)

# Dinheiro é SEMPRE Decimal (CLAUDE.md, regra 1). O CHECK do banco é `amount > 0`.
Money = condecimal(max_digits=12, decimal_places=2, gt=0)


class RevenuePaymentIn(BaseModel):
    """Um recebimento. Parcial é o caso normal: motorista que paga R$ 400 de R$ 800."""

    amount: Money
    paid_on: date = Field(default_factory=date.today)
    method: PaymentMethod = PaymentMethod.pix
    receipt_ref: str | None = Field(default=None, max_length=80)


class RevenueCreate(BaseModel):
    """Receita é CONTA A RECEBER — mas o operador não precisa saber disso.

    No caminho comum ("recebi R$ 800 hoje") `pay_now=True` já registra o pagamento integral
    e a receita nasce `paid`. Quem quiser lançar uma cobrança em aberto manda `pay_now=false`.

    `contract_id`/`fine_id` não entram aqui: cobrança de contrato nasce no domínio de
    contratos (via `revenues.service.create_revenue`), com `origin=contract`.
    """

    vehicle_id: UUID
    driver_id: UUID | None = None

    category: RevenueCategory = RevenueCategory.aluguel
    description: str | None = Field(default=None, max_length=200)
    amount: Money

    competence_date: date
    # Cobrança à vista vence no mesmo dia do fato — não faz o operador digitar duas datas.
    due_date: date | None = None
    notes: str | None = None

    pay_now: bool = True
    paid_on: date | None = None
    method: PaymentMethod = PaymentMethod.pix

    @model_validator(mode="after")
    def _defaults(self):
        if self.due_date is None:
            self.due_date = self.competence_date
        if self.pay_now:
            if self.paid_on is None:
                self.paid_on = date.today()
        elif self.paid_on is not None:
            raise ValueError("Para registrar o pagamento junto, envie pay_now = true.")
        return self


# Colunas NOT NULL: aceitar `null` nelas no PATCH viraria IntegrityError (HTTP 500).
_REQUIRED = {"vehicle_id", "category", "amount", "competence_date", "due_date"}


class RevenueUpdate(BaseModel):
    """`status` e `paid_amount` não são editáveis: são DERIVADOS dos pagamentos.

    Quem quiser mudá-los registra (ou apaga) um pagamento — deixar a mão livre no status
    criaria receita "paga" sem dinheiro nenhum atrás dela.
    """

    driver_id: UUID | None = None
    category: RevenueCategory | None = None
    description: str | None = Field(default=None, max_length=200)
    amount: Money | None = None
    competence_date: date | None = None
    due_date: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _no_null_on_required(self):
        empty = sorted(f for f in self.model_fields_set & _REQUIRED if getattr(self, f) is None)
        if empty:
            raise ValueError(f"Estes campos não podem ficar vazios: {', '.join(empty)}.")
        return self


class RevenuePaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount: Decimal
    paid_on: date
    method: PaymentMethod
    receipt_ref: str | None
    created_at: datetime


class RevenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    vehicle_id: UUID
    driver_id: UUID | None
    contract_id: UUID | None
    fine_id: UUID | None

    category: RevenueCategory
    description: str | None
    amount: Decimal
    paid_amount: Decimal

    competence_date: date
    due_date: date

    status: RevenueStatus
    # `origin` diz se a cobrança pode ser editada aqui: só as `manual` podem.
    origin: RevenueOrigin
    period_start: date | None
    period_end: date | None

    notes: str | None
    created_at: datetime
    updated_at: datetime


class RevenueDetailOut(RevenueOut):
    payments: list[RevenuePaymentOut] = []


class ReceivableOut(BaseModel):
    """Linha da tela de INADIMPLÊNCIA.

    `dias_em_atraso` é DERIVADO na hora da consulta — não existe status 'overdue' no banco
    (seria estado armazenado, dependeria de job noturno e ficaria desatualizado).
    """

    id: UUID
    code: str
    vehicle_id: UUID
    vehicle_plate: str
    driver_id: UUID | None
    driver_name: str | None
    contract_id: UUID | None

    category: RevenueCategory
    description: str | None
    amount: Decimal
    paid_amount: Decimal
    saldo: Decimal
    dias_em_atraso: int

    competence_date: date
    due_date: date
    status: RevenueStatus
