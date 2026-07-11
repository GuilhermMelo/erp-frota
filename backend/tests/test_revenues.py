"""Receita é CONTA A RECEBER desde o dia 1.

`paid_amount` e `status` são CONSEQUÊNCIA dos pagamentos — nunca entrada do usuário.
Ninguém "marca como pago": registra-se o dinheiro que entrou, e o status sai sozinho.

E a inadimplência é DERIVADA (`status IN (pending, partial) AND due_date < hoje`). Não
existe status 'overdue' no banco: estado armazenado precisaria de um job noturno e estaria
errado toda manhã, antes de ele rodar.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.domains.revenues.models import RevenueStatus


@pytest.fixture
def cobranca(auth_client, criar_veiculo, criar_motorista, hoje):
    """Uma cobrança de R$ 800 em aberto, vencida há 10 dias."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    r = auth_client.post(
        "/revenues",
        json={
            "vehicle_id": veiculo["id"],
            "driver_id": motorista["id"],
            "category": "aluguel",
            "description": "Aluguel da semana",
            "amount": "800.00",
            "competence_date": str(hoje - timedelta(days=10)),
            "due_date": str(hoje - timedelta(days=10)),
            "pay_now": False,
        },
    )
    assert r.status_code == 201, r.text
    receita = r.json()
    receita["_veiculo"] = veiculo
    receita["_motorista"] = motorista
    return receita


def test_cobranca_nasce_pendente(cobranca):
    assert cobranca["status"] == "pending"
    assert Decimal(cobranca["paid_amount"]) == Decimal("0.00")
    assert cobranca["payments"] == []


def test_pagamento_parcial_deixa_a_cobranca_partial(auth_client, cobranca, hoje):
    """R$ 300 de R$ 800: metade do caminho. Nem pendente, nem paga."""
    r = auth_client.post(
        f"/revenues/{cobranca['id']}/payments",
        json={"amount": "300.00", "paid_on": str(hoje), "method": "pix"},
    )
    assert r.status_code == 201, r.text

    receita = r.json()
    assert receita["status"] == "partial"
    assert Decimal(receita["paid_amount"]) == Decimal("300.00")
    assert len(receita["payments"]) == 1
    assert Decimal(receita["payments"][0]["amount"]) == Decimal("300.00")


def test_quitar_o_resto_fecha_a_cobranca(auth_client, cobranca, hoje, resultado):
    auth_client.post(f"/revenues/{cobranca['id']}/payments", json={"amount": "300.00"})

    r = auth_client.post(
        f"/revenues/{cobranca['id']}/payments",
        json={"amount": "500.00", "paid_on": str(hoje), "method": "dinheiro"},
    )
    assert r.status_code == 201, r.text

    receita = r.json()
    assert receita["status"] == "paid"
    assert Decimal(receita["paid_amount"]) == Decimal("800.00")
    assert len(receita["payments"]) == 2

    # O caixa do veículo enxerga os DOIS pagamentos.
    conta = resultado(cobranca["_veiculo"]["id"])
    assert Decimal(conta["total_received"]) == Decimal("800.00")
    assert Decimal(conta["total_receivable"]) == Decimal("0")


def test_pagamento_acima_do_saldo_e_recusado(auth_client, cobranca):
    """R$ 900 numa cobrança de R$ 800 — o CHECK do banco (paid_amount <= amount) recusaria."""
    r = auth_client.post(f"/revenues/{cobranca['id']}/payments", json={"amount": "900.00"})
    assert r.status_code == 400, r.text
    assert "error" in r.json()

    atual = auth_client.get(f"/revenues/{cobranca['id']}").json()
    assert atual["status"] == "pending"
    assert Decimal(atual["paid_amount"]) == Decimal("0.00")


def test_pagamento_acima_do_saldo_restante_e_recusado(auth_client, cobranca):
    """Já recebeu 300 de 800: um pagamento de 600 estoura o saldo de 500."""
    auth_client.post(f"/revenues/{cobranca['id']}/payments", json={"amount": "300.00"})

    r = auth_client.post(f"/revenues/{cobranca['id']}/payments", json={"amount": "600.00"})
    assert r.status_code == 400, r.text

    atual = auth_client.get(f"/revenues/{cobranca['id']}").json()
    assert Decimal(atual["paid_amount"]) == Decimal("300.00"), "nada foi gravado pela metade"


def test_cobranca_quitada_nao_aceita_mais_pagamento(auth_client, cobranca):
    auth_client.post(f"/revenues/{cobranca['id']}/payments", json={"amount": "800.00"})

    r = auth_client.post(f"/revenues/{cobranca['id']}/payments", json={"amount": "0.01"})
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# Inadimplência: derivada na hora da pergunta.
# ---------------------------------------------------------------------------
def test_receivables_mostra_dias_em_atraso(auth_client, cobranca, hoje):
    receivables = auth_client.get("/revenues/receivables").json()
    assert len(receivables) == 1

    linha = receivables[0]
    assert linha["id"] == cobranca["id"]
    assert linha["dias_em_atraso"] == 10, "vencida há 10 dias"
    assert Decimal(linha["saldo"]) == Decimal("800.00")
    assert linha["vehicle_plate"] == cobranca["_veiculo"]["plate"]
    assert linha["driver_name"] == cobranca["_motorista"]["full_name"]
    assert linha["status"] == "pending", "o atraso NÃO vira status no banco"


def test_atraso_e_derivado_nao_armazenado(auth_client, cobranca, db):
    """Não existe (nem pode passar a existir) o status 'overdue'."""
    assert not any(s.value == "overdue" for s in RevenueStatus), (
        "status armazenado precisaria de job noturno e ficaria errado toda manhã"
    )

    # A cobrança está vencida há 10 dias e continua `pending` no banco. O atraso só existe
    # na resposta da consulta.
    guardado = auth_client.get(f"/revenues/{cobranca['id']}").json()
    assert guardado["status"] == "pending"
    assert "dias_em_atraso" not in guardado

    atrasadas = auth_client.get("/revenues/receivables", params={"only_overdue": True}).json()
    assert [x["id"] for x in atrasadas] == [cobranca["id"]]


def test_cobranca_a_vencer_nao_esta_em_atraso(auth_client, criar_veiculo, hoje):
    """Adiantado não é '−3 dias de atraso'. É zero."""
    veiculo = criar_veiculo()
    auth_client.post(
        "/revenues",
        json={
            "vehicle_id": veiculo["id"],
            "category": "aluguel",
            "amount": "800.00",
            "competence_date": str(hoje),
            "due_date": str(hoje + timedelta(days=3)),
            "pay_now": False,
        },
    )

    receivables = auth_client.get("/revenues/receivables").json()
    assert len(receivables) == 1
    assert receivables[0]["dias_em_atraso"] == 0

    atrasadas = auth_client.get("/revenues/receivables", params={"only_overdue": True}).json()
    assert atrasadas == [], "vence daqui a 3 dias — não está em atraso"


def test_parcial_continua_na_inadimplencia_pelo_saldo(auth_client, cobranca):
    """Recebeu 300 de 800: ainda deve 500, e continua na lista de quem te deve."""
    auth_client.post(f"/revenues/{cobranca['id']}/payments", json={"amount": "300.00"})

    receivables = auth_client.get("/revenues/receivables").json()
    assert len(receivables) == 1
    assert receivables[0]["status"] == "partial"
    assert Decimal(receivables[0]["saldo"]) == Decimal("500.00")
    assert Decimal(receivables[0]["paid_amount"]) == Decimal("300.00")


def test_cobranca_quitada_sai_da_inadimplencia(auth_client, cobranca):
    auth_client.post(f"/revenues/{cobranca['id']}/payments", json={"amount": "800.00"})
    assert auth_client.get("/revenues/receivables").json() == []


def test_dashboard_soma_a_inadimplencia(auth_client, cobranca):
    dashboard = auth_client.get("/finance/dashboard").json()
    assert Decimal(dashboard["total_overdue"]) == Decimal("800.00")
    assert dashboard["overdue_count"] == 1
    assert Decimal(dashboard["total_receivable"]) == Decimal("800.00")
