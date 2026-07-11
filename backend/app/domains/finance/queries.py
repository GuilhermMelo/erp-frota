"""A conta do veículo — a razão de existir do produto.

    Lucro = receitas − despesas − valor_compra + valor_venda

Tudo derivado em tempo de query, nada materializado. Com dezenas de veículos isso responde
em milissegundos; pré-agregar seria criar um número que pode ficar errado.

Regime de CAIXA: receita é o que foi efetivamente recebido (revenue_payments), despesa é o
que foi efetivamente pago. O que está em aberto aparece separado — nunca escondido.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.domains.expenses.models import Expense, ExpenseCategory, ExpenseStatus
from app.domains.revenues.models import Revenue, RevenuePayment, RevenueStatus
from app.domains.vehicles.models import Vehicle

ZERO = Decimal("0.00")


def _received_cte():
    """Receita EFETIVAMENTE recebida, por veículo."""
    return (
        select(
            Revenue.vehicle_id.label("vehicle_id"),
            func.coalesce(func.sum(RevenuePayment.amount), 0).label("received"),
        )
        .join(RevenuePayment, RevenuePayment.revenue_id == Revenue.id)
        .group_by(Revenue.vehicle_id)
        .cte("received")
    )


def _receivable_cte():
    """O que ainda falta receber (cobranças em aberto), por veículo."""
    return (
        select(
            Revenue.vehicle_id.label("vehicle_id"),
            func.coalesce(func.sum(Revenue.amount - Revenue.paid_amount), 0).label("receivable"),
        )
        .where(Revenue.status.in_([RevenueStatus.pending, RevenueStatus.partial]))
        .group_by(Revenue.vehicle_id)
        .cte("receivable")
    )


def _expense_cte():
    """Despesa paga, separada entre CUSTO de operação e CAPEX (investimento no carro).

    A separação é o que faz o custo por km ficar honesto: uma blindagem de R$ 15 mil é
    investimento, não "custo do mês".
    """
    paid = Expense.status == ExpenseStatus.paid
    return (
        select(
            Expense.vehicle_id.label("vehicle_id"),
            func.coalesce(
                func.sum(case((ExpenseCategory.is_capex.is_(False), Expense.amount), else_=0)), 0
            ).label("cost"),
            func.coalesce(
                func.sum(case((ExpenseCategory.is_capex.is_(True), Expense.amount), else_=0)), 0
            ).label("capex"),
        )
        .join(ExpenseCategory, ExpenseCategory.id == Expense.category_id)
        .where(paid)
        .group_by(Expense.vehicle_id)
        .cte("expense_paid")
    )


def _pending_expense_cte():
    return (
        select(
            Expense.vehicle_id.label("vehicle_id"),
            func.coalesce(func.sum(Expense.amount), 0).label("pending"),
        )
        .where(Expense.status == ExpenseStatus.pending)
        .group_by(Expense.vehicle_id)
        .cte("expense_pending")
    )


def vehicle_result_statement(vehicle_id: UUID | None = None):
    received, receivable = _received_cte(), _receivable_cte()
    exp, exp_pending = _expense_cte(), _pending_expense_cte()

    revenues = func.coalesce(received.c.received, 0)
    costs = func.coalesce(exp.c.cost, 0)
    capex = func.coalesce(exp.c.capex, 0)

    # Investimento = o que você colocou no carro: preço de compra + melhorias (capex).
    investment = Vehicle.purchase_price + capex
    # Venda: se ainda não vendeu, entra 0 no resultado REALIZADO.
    sale = func.coalesce(Vehicle.sale_price, 0)

    profit = revenues - costs - investment + sale

    # "Se eu vender hoje": usa o valor de mercado estimado no lugar da venda.
    # NULL quando o carro já foi vendido (a pergunta não faz sentido) ou quando não há
    # estimativa — melhor mostrar vazio do que um número inventado.
    profit_if_sold_today = case(
        (
            Vehicle.sale_price.is_(None) & Vehicle.estimated_market_value.isnot(None),
            revenues - costs - investment + func.coalesce(Vehicle.estimated_market_value, 0),
        ),
        else_=None,
    )

    km_driven = Vehicle.current_odometer - Vehicle.purchase_odometer

    return (
        select(
            Vehicle.id.label("vehicle_id"),
            Vehicle.code,
            Vehicle.plate,
            Vehicle.brand,
            Vehicle.model,
            Vehicle.status,
            Vehicle.purchase_price,
            Vehicle.purchase_date,
            Vehicle.sale_price,
            Vehicle.sale_date,
            Vehicle.estimated_market_value,
            revenues.label("total_received"),
            func.coalesce(receivable.c.receivable, 0).label("total_receivable"),
            costs.label("total_cost"),
            capex.label("total_capex"),
            func.coalesce(exp_pending.c.pending, 0).label("total_expense_pending"),
            investment.label("investment"),
            profit.label("profit"),
            profit_if_sold_today.label("profit_if_sold_today"),
            # ROI e custo/km dividem por valores que podem ser ZERO (carro recém-comprado,
            # carro recebido de graça). Divisão por zero aqui viraria HTTP 500 — por isso
            # o CASE devolve NULL, e a tela mostra "—".
            case((investment > 0, profit / investment), else_=None).label("roi"),
            case((km_driven > 0, costs / km_driven), else_=None).label("cost_per_km"),
            case((km_driven > 0, revenues / km_driven), else_=None).label("revenue_per_km"),
            km_driven.label("km_driven"),
        )
        .select_from(Vehicle)
        .outerjoin(received, received.c.vehicle_id == Vehicle.id)
        .outerjoin(receivable, receivable.c.vehicle_id == Vehicle.id)
        .outerjoin(exp, exp.c.vehicle_id == Vehicle.id)
        .outerjoin(exp_pending, exp_pending.c.vehicle_id == Vehicle.id)
        .where(Vehicle.deleted_at.is_(None))
        .where(Vehicle.id == vehicle_id if vehicle_id else True)
    )


def vehicle_result(db: Session, vehicle_id: UUID):
    return db.execute(vehicle_result_statement(vehicle_id)).mappings().first()


def fleet_results(db: Session):
    """Ranking da frota por lucro — a tela que decide qual carro vender e qual comprar."""
    stmt = vehicle_result_statement().order_by(None)
    rows = db.execute(stmt).mappings().all()
    return sorted(rows, key=lambda r: r["profit"], reverse=True)


VAZIO = {"month": None, "months_elapsed": None, "months_remaining": None}


def payback(db: Session, vehicle_id: UUID, investment: Decimal, *, is_sold: bool = False) -> dict:
    """Em quanto tempo o carro se pagou — ou quanto falta.

    Percorre o resultado mês a mês (regime de caixa) acumulando `receita − despesa` da
    OPERAÇÃO, e devolve o primeiro mês em que o acumulado alcança o investimento.

    A VENDA não entra nesta conta: payback é sobre o carro se pagar rodando, não sobre
    revendê-lo. Por isso, para um carro JÁ VENDIDO que não se pagou pela operação, a
    resposta é vazia — estimar "faltam 8 meses" para um carro que não é mais seu seria
    mentira. O resultado dele é o lucro final realizado, não uma projeção.

    Quando o carro não gera lucro mensal, a estimativa também é `None` — a resposta honesta
    é "não dá para saber", não um número inventado.
    """
    if investment <= 0:
        return dict(VAZIO)

    acumulado = ZERO
    for i, m in enumerate(monthly_series(db, vehicle_id)):
        acumulado += m["profit"]
        if acumulado >= investment:
            return {"month": m["month"], "months_elapsed": i + 1, "months_remaining": 0}

    if is_sold:
        return dict(VAZIO)

    meses = monthly_series(db, vehicle_id)
    ultimos = [m["profit"] for m in meses[-3:] if m["profit"] > 0]
    if not ultimos:
        return dict(VAZIO)

    media = sum(ultimos) / len(ultimos)
    falta = investment - acumulado
    restantes = int((falta / media).to_integral_value(rounding="ROUND_CEILING"))
    return {"month": None, "months_elapsed": None, "months_remaining": restantes}


def monthly_series(db: Session, vehicle_id: UUID | None = None):
    """Receita e despesa por mês (regime de caixa), para o gráfico."""
    month = func.to_char(RevenuePayment.paid_on, "YYYY-MM")
    rev_stmt = (
        select(month.label("month"), func.sum(RevenuePayment.amount).label("revenue"))
        .join(Revenue, Revenue.id == RevenuePayment.revenue_id)
        .group_by(month)
    )
    exp_month = func.to_char(Expense.paid_on, "YYYY-MM")
    exp_stmt = (
        select(exp_month.label("month"), func.sum(Expense.amount).label("expense"))
        .where(Expense.status == ExpenseStatus.paid)
        .group_by(exp_month)
    )
    if vehicle_id:
        rev_stmt = rev_stmt.where(Revenue.vehicle_id == vehicle_id)
        exp_stmt = exp_stmt.where(Expense.vehicle_id == vehicle_id)

    revenues = {r.month: r.revenue for r in db.execute(rev_stmt)}
    expenses = {r.month: r.expense for r in db.execute(exp_stmt)}

    out = []
    for m in sorted(set(revenues) | set(expenses)):
        rev, exp = revenues.get(m, ZERO), expenses.get(m, ZERO)
        out.append({"month": m, "revenue": rev, "expense": exp, "profit": rev - exp})
    return out
