"""Saída financeira.

TODO valor é `Decimal`. Nunca `float` — em ERP financeiro, `float` é bug de dinheiro
(ARQUITETURA.md, regra 1).

Os campos que podem vir NULL (`roi`, `cost_per_km`, `profit_if_sold_today`) são
`Decimal | None` de propósito: dividir por um investimento zero ou por um carro que ainda
não rodou não dá zero, dá indefinido. A tela mostra "—". Devolver 0 seria mentir.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domains.vehicles.models import VehicleStatus


class VehicleResultOut(BaseModel):
    """A conta do veículo: receitas − despesas − valor_compra + valor_venda."""

    model_config = ConfigDict(from_attributes=True)

    vehicle_id: UUID
    code: str
    plate: str
    brand: str
    model: str
    status: VehicleStatus

    purchase_price: Decimal
    purchase_date: date
    sale_price: Decimal | None
    sale_date: date | None
    estimated_market_value: Decimal | None

    # Regime de caixa: o que ENTROU e o que SAIU de verdade.
    total_received: Decimal
    total_cost: Decimal
    total_capex: Decimal
    # O que está em aberto aparece separado — nunca escondido dentro do lucro.
    total_receivable: Decimal
    total_expense_pending: Decimal

    investment: Decimal
    profit: Decimal
    profit_if_sold_today: Decimal | None

    roi: Decimal | None
    cost_per_km: Decimal | None
    revenue_per_km: Decimal | None
    km_driven: int

    # Payback: em que mês o carro se pagou (ou quantos meses faltam, estimado).
    # Tudo `None` quando não dá para saber — melhor vazio do que um número inventado.
    payback_month: str | None = None
    payback_months_elapsed: int | None = None
    payback_months_remaining: int | None = None


class MonthlyPointOut(BaseModel):
    month: str  # "2026-07"
    revenue: Decimal
    expense: Decimal
    profit: Decimal


class DashboardOut(BaseModel):
    month: str  # o mês corrente, "2026-07"

    vehicles_total: int
    vehicles_by_status: dict[str, int]

    revenue_received_month: Decimal
    expense_paid_month: Decimal
    profit_month: Decimal

    total_receivable: Decimal
    # Inadimplência é DERIVADA (pending/partial + due_date < hoje), não armazenada.
    total_overdue: Decimal
    overdue_count: int
