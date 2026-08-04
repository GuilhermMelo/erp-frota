"""Cobrança semanal: idempotente, nunca futura.

A idempotência (`UNIQUE(contract_id, period_start)` + a checagem prévia das semanas já
geradas) é o que permite ao frontend chamar `POST /contracts/generate-charges` toda vez
que o app abre. Sem cron, sem job noturno, sem duplicar. É o teste mais importante deste
arquivo: se ele falhar, o dono cobra o motorista duas vezes pela mesma semana.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest


@pytest.fixture
def contrato_de_3_semanas(auth_client, criar_veiculo, criar_motorista, hoje):
    """Contrato que começou há exatamente 3 semanas (21 dias)."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    r = auth_client.post(
        "/contracts",
        json={
            "vehicle_id": veiculo["id"],
            "driver_id": motorista["id"],
            "start_date": str(hoje - timedelta(days=21)),
            "weekly_amount": "800.00",
            "billing_weekday": 0,
            "deposit_amount": "0.00",
        },
    )
    assert r.status_code == 201, r.text
    contrato = r.json()
    contrato["_veiculo"] = veiculo
    contrato["_motorista"] = motorista
    return contrato


def _cobrancas(auth_client, contrato) -> list[dict]:
    r = auth_client.get("/revenues", params={"contract_id": contrato["id"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_gera_as_semanas_fechadas_e_a_corrente(auth_client, contrato_de_3_semanas, hoje):
    """3 semanas fechadas + a semana corrente = 4 cobranças. Nenhuma futura."""
    cobrancas = _cobrancas(auth_client, contrato_de_3_semanas)

    assert 3 <= len(cobrancas) <= 4
    assert len(cobrancas) == 4, "as 3 semanas fechadas + a corrente"

    inicios = sorted(date.fromisoformat(c["period_start"]) for c in cobrancas)
    assert inicios == [hoje - timedelta(days=d) for d in (21, 14, 7, 0)]

    assert all(i <= hoje for i in inicios), "uma semana só é cobrável depois de começar"

    for c in cobrancas:
        assert c["origin"] == "contract"
        assert c["category"] == "aluguel"
        assert Decimal(c["amount"]) == Decimal("800.00")
        assert c["status"] == "pending"
        # A semana tem 7 dias: começo + 6.
        assert date.fromisoformat(c["period_end"]) == date.fromisoformat(c["period_start"]) + timedelta(days=6)


def test_gerar_de_novo_nao_cria_nenhuma(auth_client, contrato_de_3_semanas):
    """O TESTE QUE SUSTENTA A ARQUITETURA: gerar duas vezes não duplica nada.

    É isto que permite chamar a geração toda vez que o app abre, sem cron.
    """
    antes = _cobrancas(auth_client, contrato_de_3_semanas)
    assert len(antes) == 4

    r = auth_client.post("/contracts/generate-charges")
    assert r.status_code == 200, r.text
    assert r.json()["geradas"] == 0, "as 4 semanas já existiam"

    # E de novo, e de novo. O app abre dez vezes por dia.
    for _ in range(3):
        assert auth_client.post("/contracts/generate-charges").json()["geradas"] == 0

    depois = _cobrancas(auth_client, contrato_de_3_semanas)
    assert len(depois) == 4
    assert {c["id"] for c in depois} == {c["id"] for c in antes}, "são as MESMAS cobranças"


def test_mudar_o_inicio_de_um_contrato_que_ja_cobrou_e_recusado(
    auth_client, contrato_de_3_semanas, hoje
):
    """REGRESSÃO. A idempotência é ancorada em `period_start`, e o `period_start` sai da
    `start_date`: mudar o início desloca TODA a grade de semanas. A
    `UNIQUE(contract_id, period_start)` não veria duplicata nenhuma — são chaves novas —
    e a próxima abertura do app geraria de novo as 4 semanas já cobradas.

    O `assert` que importa não é o 409: é o faturamento continuar em R$ 3.200.
    """
    antes = _cobrancas(auth_client, contrato_de_3_semanas)
    assert len(antes) == 4, "CONTROLE POSITIVO: existe grade gerada para ser deslocada"
    faturado = sum(Decimal(c["amount"]) for c in antes)
    assert faturado == Decimal("3200.00")

    r = auth_client.patch(
        f"/contracts/{contrato_de_3_semanas['id']}",
        json={"start_date": str(hoje - timedelta(days=19))},
    )
    assert r.status_code == 409, r.text

    assert auth_client.post("/contracts/generate-charges").json()["geradas"] == 0
    depois = _cobrancas(auth_client, contrato_de_3_semanas)
    assert len(depois) == 4
    assert sum(Decimal(c["amount"]) for c in depois) == faturado


def test_mudar_o_dia_de_cobranca_nao_duplica_as_semanas_ja_cobradas(
    auth_client, contrato_de_3_semanas
):
    """REGRESSÃO da decisão de desenho que separa `period_start` de `due_date`.

    `generate_charges` anda a grade a partir da `start_date`; o `billing_weekday` decide
    só o DIA DE VENCIMENTO dentro da semana (`week_due_date`). Se alguém ancorasse o
    `period_start` no dia da semana — que é a implementação "óbvia" —, trocar o dia de
    cobrança deslocaria todo `period_start` e a próxima geração criaria as 4 semanas de
    novo, R$ 3.200 cobrados em duplicidade, sem violar a UNIQUE.

    Aqui o PATCH é permitido (200) de propósito: o dono pode mudar o dia de pagamento.
    O que não pode é isso mexer no que já foi cobrado.
    """
    antes = _cobrancas(auth_client, contrato_de_3_semanas)
    assert len(antes) == 4, "CONTROLE POSITIVO: há 4 semanas para eventualmente duplicar"
    faturado = sum(Decimal(c["amount"]) for c in antes)

    r = auth_client.patch(
        f"/contracts/{contrato_de_3_semanas['id']}", json={"billing_weekday": 3}
    )
    assert r.status_code == 200, r.text
    assert r.json()["billing_weekday"] == 3

    assert auth_client.post("/contracts/generate-charges").json()["geradas"] == 0
    depois = _cobrancas(auth_client, contrato_de_3_semanas)
    assert len(depois) == 4
    assert sum(Decimal(c["amount"]) for c in depois) == faturado
    assert {c["period_start"] for c in depois} == {c["period_start"] for c in antes}


def test_gerar_por_contrato_tambem_e_idempotente(auth_client, contrato_de_3_semanas):
    r = auth_client.post(f"/contracts/{contrato_de_3_semanas['id']}/generate-charges")
    assert r.status_code == 200, r.text
    assert r.json()["geradas"] == 0
    assert len(_cobrancas(auth_client, contrato_de_3_semanas)) == 4


def test_a_semana_que_passou_e_gerada_na_proxima_chamada(
    auth_client, criar_veiculo, criar_motorista, hoje, db
):
    """O contrato começou hoje: 1 cobrança. Uma semana depois, a geração cria a segunda.

    Simula a passagem do tempo mexendo no `start_date` do contrato — que é o mesmo que
    olhar para ele daqui a uma semana.
    """
    from app.domains.contracts.models import Contract

    veiculo = criar_veiculo()
    motorista = criar_motorista()
    r = auth_client.post(
        "/contracts",
        json={
            "vehicle_id": veiculo["id"],
            "driver_id": motorista["id"],
            "start_date": str(hoje),
            "weekly_amount": "800.00",
        },
    )
    assert r.status_code == 201, r.text
    contrato = r.json()
    assert len(_cobrancas(auth_client, contrato)) == 1, "só a semana corrente"

    # "Uma semana se passou": o contrato agora começou há 7 dias.
    obj = db.get(Contract, UUID(contrato["id"]))
    obj.start_date = hoje - timedelta(days=7)
    db.commit()

    assert auth_client.post("/contracts/generate-charges").json()["geradas"] == 1
    cobrancas = _cobrancas(auth_client, contrato)
    assert len(cobrancas) == 2, "a semana que fechou entrou; a de agora já estava lá"

    # E continua idempotente.
    assert auth_client.post("/contracts/generate-charges").json()["geradas"] == 0


def test_dois_contratos_ativos_para_o_mesmo_veiculo_e_recusado(
    auth_client, criar_veiculo, criar_motorista, hoje
):
    """Um carro não pode estar alugado para dois motoristas ao mesmo tempo."""
    veiculo = criar_veiculo()
    primeiro = criar_motorista()
    segundo = criar_motorista()

    r1 = auth_client.post(
        "/contracts",
        json={
            "vehicle_id": veiculo["id"],
            "driver_id": primeiro["id"],
            "start_date": str(hoje),
            "weekly_amount": "800.00",
        },
    )
    assert r1.status_code == 201, r1.text

    r2 = auth_client.post(
        "/contracts",
        json={
            "vehicle_id": veiculo["id"],
            "driver_id": segundo["id"],
            "start_date": str(hoje),
            "weekly_amount": "900.00",
        },
    )
    assert r2.status_code == 409, r2.text
    assert r1.json()["code"] in r2.json()["error"]["message"], "a mensagem diz qual contrato"

    ativos = auth_client.get(
        "/contracts", params={"vehicle_id": veiculo["id"], "status": "active"}
    ).json()
    assert len(ativos) == 1


def test_encerrar_libera_o_veiculo_para_um_novo_contrato(
    auth_client, criar_veiculo, criar_motorista, hoje
):
    veiculo = criar_veiculo()
    primeiro = criar_motorista()
    segundo = criar_motorista()

    c1 = auth_client.post(
        "/contracts",
        json={
            "vehicle_id": veiculo["id"],
            "driver_id": primeiro["id"],
            "start_date": str(hoje - timedelta(days=30)),
            "weekly_amount": "800.00",
        },
    ).json()

    assert auth_client.get(f"/vehicles/{veiculo['id']}").json()["status"] == "rented"

    r = auth_client.post(
        f"/contracts/{c1['id']}/finish",
        json={"end_date": str(hoje), "deposit_returned_amount": "0.00"},
    )
    assert r.status_code == 200, r.text
    assert auth_client.get(f"/vehicles/{veiculo['id']}").json()["status"] == "available"

    r2 = auth_client.post(
        "/contracts",
        json={
            "vehicle_id": veiculo["id"],
            "driver_id": segundo["id"],
            "start_date": str(hoje),
            "weekly_amount": "900.00",
        },
    )
    assert r2.status_code == 201, r2.text


def test_contrato_de_veiculo_vendido_e_recusado(auth_client, criar_veiculo, criar_motorista, hoje):
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    auth_client.post(
        f"/vehicles/{veiculo['id']}/sell",
        json={"sale_price": "40000.00", "sale_date": str(hoje)},
    )

    r = auth_client.post(
        "/contracts",
        json={
            "vehicle_id": veiculo["id"],
            "driver_id": motorista["id"],
            "start_date": str(hoje),
            "weekly_amount": "800.00",
        },
    )
    assert r.status_code == 409, r.text


def test_encerramento_retroativo_cancela_as_semanas_posteriores(
    auth_client, contrato_de_3_semanas, hoje
):
    """O contrato acabou há 2 semanas e só agora foi encerrado no sistema.

    As semanas geradas depois do fim não são devidas — mas só as intocadas somem.
    """
    contrato = contrato_de_3_semanas
    fim = hoje - timedelta(days=10)

    r = auth_client.post(
        f"/contracts/{contrato['id']}/finish",
        json={"end_date": str(fim), "deposit_returned_amount": "0.00"},
    )
    assert r.status_code == 200, r.text

    cobrancas = _cobrancas(auth_client, contrato)
    posteriores = [c for c in cobrancas if date.fromisoformat(c["period_start"]) > fim]
    assert posteriores, "havia semanas geradas depois do fim"
    assert all(c["status"] == "canceled" for c in posteriores)

    anteriores = [c for c in cobrancas if date.fromisoformat(c["period_start"]) <= fim]
    assert all(c["status"] == "pending" for c in anteriores), "o que ele rodou continua devido"


def test_contrato_encerrado_nao_gera_mais_cobranca(auth_client, contrato_de_3_semanas, hoje):
    """Depois do fim, a geração automática não pode continuar cobrando o motorista."""
    contrato = contrato_de_3_semanas
    auth_client.post(
        f"/contracts/{contrato['id']}/finish",
        json={"end_date": str(hoje), "deposit_returned_amount": "0.00"},
    )
    antes = len(_cobrancas(auth_client, contrato))

    assert auth_client.post("/contracts/generate-charges").json()["geradas"] == 0
    assert len(_cobrancas(auth_client, contrato)) == antes


def test_pagar_a_cobranca_semanal_sobe_o_lucro_do_carro(auth_client, contrato_de_3_semanas, lucro):
    """A cobrança semanal só vira lucro quando o dinheiro entra (regime de caixa)."""
    contrato = contrato_de_3_semanas
    veiculo = contrato["_veiculo"]
    antes = lucro(veiculo["id"])

    cobrancas = _cobrancas(auth_client, contrato)
    r = auth_client.post(f"/revenues/{cobrancas[0]['id']}/payments", json={"amount": "800.00"})
    assert r.status_code == 201, r.text

    assert lucro(veiculo["id"]) == antes + Decimal("800.00")


def test_cobranca_de_contrato_nao_e_editavel_a_mao(auth_client, contrato_de_3_semanas):
    """Cobrança de contrato é reflexo do contrato, não um lançamento avulso."""
    cobranca = _cobrancas(auth_client, contrato_de_3_semanas)[0]

    r = auth_client.patch(f"/revenues/{cobranca['id']}", json={"amount": "50.00"})
    assert r.status_code == 400, r.text

    r = auth_client.delete(f"/revenues/{cobranca['id']}")
    assert r.status_code == 400, r.text

    # Mas RECEBER funciona: receber não é editar.
    assert auth_client.post(
        f"/revenues/{cobranca['id']}/payments", json={"amount": "800.00"}
    ).status_code == 201


def test_cobranca_paga_nao_e_cancelada_no_encerramento(auth_client, contrato_de_3_semanas, hoje):
    """Cobrança com dinheiro em cima é fato consumado. Não se apaga."""
    contrato = contrato_de_3_semanas
    cobrancas = _cobrancas(auth_client, contrato)
    ultima = max(cobrancas, key=lambda c: c["period_start"])

    auth_client.post(f"/revenues/{ultima['id']}/payments", json={"amount": "800.00"})

    fim = hoje - timedelta(days=10)
    auth_client.post(
        f"/contracts/{contrato['id']}/finish",
        json={"end_date": str(fim), "deposit_returned_amount": "0.00"},
    )

    paga = auth_client.get(f"/revenues/{ultima['id']}").json()
    assert paga["status"] == "paid", "semana posterior ao fim, mas paga: não pode ser cancelada"
