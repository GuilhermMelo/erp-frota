from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, condecimal, model_validator

from app.domains.expenses.models import ExpenseOrigin, ExpenseStatus

# Dinheiro é SEMPRE Decimal (ARQUITETURA.md, regra 1). O CHECK do banco é `amount > 0`.
Money = condecimal(max_digits=12, decimal_places=2, gt=0)


class ExpenseCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    # is_capex separa INVESTIMENTO no carro (blindagem, kit gás) de CUSTO de operação.
    # A tela precisa saber disso para não chamar melhoria de "gasto do mês".
    is_capex: bool
    sort_order: int


def _check_payment_state(status: ExpenseStatus | None, paid_on: date | None) -> None:
    """Espelha o CHECK `(status = 'paid') = (paid_on IS NOT NULL)` com mensagem em português.

    Sem isso o banco recusa e o operador vê "erro interno" em vez de saber o que faltou.
    """
    if status == ExpenseStatus.paid and paid_on is None:
        raise ValueError("Informe a data de pagamento para lançar a despesa como paga.")
    if status == ExpenseStatus.pending and paid_on is not None:
        raise ValueError("Despesa pendente não pode ter data de pagamento. Marque-a como paga.")


class ExpenseCreate(BaseModel):
    # `code` (DES000001) é gerado por SEQUENCE. `origin` é sempre `manual` neste endpoint:
    # despesa de manutenção/multa nasce no domínio de origem, via expenses.service.
    vehicle_id: UUID
    driver_id: UUID | None = None
    category_id: int

    supplier_name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=200)
    amount: Money

    competence_date: date
    paid_on: date | None = None
    status: ExpenseStatus = ExpenseStatus.paid

    odometer: int | None = Field(default=None, ge=0)
    document_number: str | None = Field(default=None, max_length=60)
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_payment_state(self):
        _check_payment_state(self.status, self.paid_on)
        return self


# Colunas NOT NULL: aceitar `null` nelas no PATCH viraria IntegrityError (HTTP 500).
_REQUIRED = {"vehicle_id", "category_id", "amount", "competence_date", "status"}


class ExpenseUpdate(BaseModel):
    vehicle_id: UUID | None = None
    driver_id: UUID | None = None
    category_id: int | None = None

    supplier_name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=200)
    amount: Money | None = None

    competence_date: date | None = None
    paid_on: date | None = None
    status: ExpenseStatus | None = None

    odometer: int | None = Field(default=None, ge=0)
    document_number: str | None = Field(default=None, max_length=60)
    notes: str | None = None

    @model_validator(mode="after")
    def _no_null_on_required(self):
        empty = sorted(f for f in self.model_fields_set & _REQUIRED if getattr(self, f) is None)
        if empty:
            raise ValueError(f"Estes campos não podem ficar vazios: {', '.join(empty)}.")
        return self

    # A coerência status × paid_on depende do estado FINAL da despesa (o PATCH pode mandar
    # só um dos dois), então é validada no router, depois de aplicar as mudanças.


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    vehicle_id: UUID
    driver_id: UUID | None
    category_id: int
    category: ExpenseCategoryOut
    maintenance_id: UUID | None
    fine_id: UUID | None

    supplier_name: str | None
    description: str | None
    amount: Decimal

    competence_date: date
    paid_on: date | None
    status: ExpenseStatus
    # `origin` diz se a despesa pode ser editada aqui: só as `manual` podem.
    origin: ExpenseOrigin

    odometer: int | None
    document_number: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
