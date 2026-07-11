"""Decimal ponta a ponta. Em ERP financeiro, `float` é bug de dinheiro.

Estes testes provam que não existe um único `float` no caminho entre o JSON que entra e o
JSON que sai. Se alguém trocar `Numeric` por `Float` — ou fizer a conta em Python com
`float()` — a dízima aparece aqui.
"""

from decimal import Decimal

import pytest

from app.domains.expenses.models import Expense
from app.domains.revenues.models import Revenue, RevenuePayment
from app.domains.vehicles.models import Vehicle

VALORES = ["0.01", "9999999.99", "1234.56", "0.10", "1000000.00"]


@pytest.mark.parametrize("valor", VALORES)
def test_valor_volta_identico_da_api(auth_client, criar_veiculo, lancar_receita, valor):
    """O que entrou é o que sai. Sem dízima, sem centavo arredondado."""
    veiculo = criar_veiculo()
    receita = lancar_receita(veiculo["id"], valor, category="outros", description=f"teste {valor}")

    # String, não float: é a prova de que o Pydantic serializou um Decimal.
    assert isinstance(receita["amount"], str)
    assert receita["amount"] == valor
    assert Decimal(receita["amount"]) == Decimal(valor)

    # E depois de dar uma volta pelo banco, continua igual.
    de_volta = auth_client.get(f"/revenues/{receita['id']}").json()
    assert de_volta["amount"] == valor
    assert de_volta["paid_amount"] == valor
    assert de_volta["payments"][0]["amount"] == valor


@pytest.mark.parametrize("valor", VALORES)
def test_despesa_volta_identica(auth_client, criar_veiculo, lancar_despesa, valor):
    veiculo = criar_veiculo()
    despesa = lancar_despesa(veiculo["id"], valor)

    assert despesa["amount"] == valor
    assert auth_client.get(f"/expenses/{despesa['id']}").json()["amount"] == valor


def test_tres_centavos_de_dez_somam_trinta_exatos(criar_veiculo, lancar_receita, resultado):
    """0,10 + 0,10 + 0,10 = 0,30.

    Com float daria 0.30000000000000004 — e o dono veria um centavo aparecer do nada no
    relatório do carro.
    """
    veiculo = criar_veiculo(purchase_price="0.00")
    for _ in range(3):
        lancar_receita(veiculo["id"], "0.10")

    conta = resultado(veiculo["id"])
    assert conta["total_received"] == "0.30", "a soma tem que ser 0,30 EXATO"
    assert Decimal(conta["total_received"]) == Decimal("0.30")
    assert Decimal(conta["total_received"]) != Decimal(str(0.1 + 0.1 + 0.1))


def test_a_conta_do_veiculo_fecha_no_centavo(
    auth_client, criar_veiculo, lancar_receita, lancar_despesa, resultado, hoje
):
    """Centavos ímpares dos dois lados da conta, e o lucro sai exato."""
    veiculo = criar_veiculo(purchase_price="33333.33")
    lancar_receita(veiculo["id"], "1111.11")
    lancar_despesa(veiculo["id"], "222.22")
    auth_client.post(
        f"/vehicles/{veiculo['id']}/sell",
        json={"sale_price": "32444.44", "sale_date": str(hoje)},
    )

    # 1.111,11 − 222,22 − 33.333,33 + 32.444,44 = 0,00
    conta = resultado(veiculo["id"])
    assert conta["profit"] == "0.00"


def test_a_soma_da_api_bate_com_a_soma_do_banco(
    criar_veiculo, lancar_receita, lancar_despesa, resultado, db
):
    """Centavos ímpares dos dois lados: a conta da API tem que bater com um SUM cru."""
    from sqlalchemy import func, select

    veiculo = criar_veiculo(purchase_price="50000.00")
    for valor in ["100.01", "200.02", "300.03"]:
        lancar_receita(veiculo["id"], valor)
    for valor in ["10.11", "20.22"]:
        lancar_despesa(veiculo["id"], valor)

    conta = resultado(veiculo["id"])
    recebido_no_banco = db.scalar(select(func.sum(RevenuePayment.amount)))
    pago_no_banco = db.scalar(select(func.sum(Expense.amount)))

    assert Decimal(conta["total_received"]) == recebido_no_banco == Decimal("600.06")
    assert Decimal(conta["total_cost"]) == pago_no_banco == Decimal("30.33")
    assert Decimal(conta["profit"]) == Decimal("600.06") - Decimal("30.33") - Decimal("50000.00")
    assert conta["profit"] == "-49430.27"


def test_as_colunas_de_dinheiro_sao_numeric_e_nunca_float(db):
    """A prova estrutural: nenhuma coluna de dinheiro é ponto flutuante.

    O teste acima poderia passar por sorte com valores redondos. Este não passa por sorte.
    """
    colunas = [
        (Vehicle.__table__, "purchase_price"),
        (Vehicle.__table__, "sale_price"),
        (Vehicle.__table__, "estimated_market_value"),
        (Revenue.__table__, "amount"),
        (Revenue.__table__, "paid_amount"),
        (RevenuePayment.__table__, "amount"),
        (Expense.__table__, "amount"),
    ]
    for tabela, nome in colunas:
        coluna = tabela.c[nome]
        tipo = coluna.type
        assert tipo.__class__.__name__ == "Numeric", f"{tabela.name}.{nome} não é Numeric"
        assert tipo.python_type is Decimal
        assert (tipo.precision, tipo.scale) == (12, 2), f"{tabela.name}.{nome} não é Numeric(12,2)"


def test_valor_com_mais_de_dois_decimais_e_recusado(auth_client, criar_veiculo, hoje):
    """R$ 10,555 não existe. O schema recusa antes de o banco arredondar em silêncio."""
    veiculo = criar_veiculo()
    r = auth_client.post(
        "/revenues",
        json={
            "vehicle_id": veiculo["id"],
            "category": "aluguel",
            "amount": "10.555",
            "competence_date": str(hoje),
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "dados_invalidos"


@pytest.mark.parametrize("valor", ["0.00", "-100.00"])
def test_receita_de_valor_zero_ou_negativo_e_recusada(auth_client, criar_veiculo, hoje, valor):
    """O CHECK do banco é `amount > 0`. O schema recusa antes, com mensagem legível."""
    veiculo = criar_veiculo()
    r = auth_client.post(
        "/revenues",
        json={
            "vehicle_id": veiculo["id"],
            "category": "aluguel",
            "amount": valor,
            "competence_date": str(hoje),
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "dados_invalidos"
