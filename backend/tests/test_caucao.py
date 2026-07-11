"""A caução NÃO é receita.

É dinheiro do motorista, que o dono segura e devolve. Ela mora em
`contracts.deposit_amount` — nunca em `revenues`. Lançá-la como receita inflaria o lucro
do carro todos os dias, até o dia da devolução.

Só a parte efetivamente RETIDA no encerramento (avaria, dívida) vira receita, categoria
`caucao_retida`.
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.domains.revenues.models import Revenue, RevenueCategory, RevenueStatus


def _contrato(auth_client, veiculo, motorista, hoje, **kwargs) -> dict:
    payload = {
        "vehicle_id": veiculo["id"],
        "driver_id": motorista["id"],
        "start_date": str(hoje - timedelta(days=14)),
        "weekly_amount": "800.00",
        "billing_weekday": 0,
        "deposit_amount": "2000.00",
    }
    payload.update(kwargs)
    r = auth_client.post("/contracts", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_caucao_recebida_nao_muda_o_lucro(
    auth_client, criar_veiculo, criar_motorista, lucro, hoje
):
    """R$ 2.000 de caução entram no caixa do dono — e o lucro do carro NÃO se mexe."""
    veiculo = criar_veiculo(purchase_price="40000.00")
    motorista = criar_motorista()

    antes = lucro(veiculo["id"])
    assert antes == Decimal("-40000.00")

    contrato = _contrato(auth_client, veiculo, motorista, hoje, deposit_amount="2000.00")
    assert Decimal(contrato["deposit_amount"]) == Decimal("2000.00")
    assert contrato["deposit_status"] == "held", "a caução está com você, mas não é sua"

    assert lucro(veiculo["id"]) == antes, "a caução não pode inflar o lucro do veículo"


def test_caucao_nao_cria_receita(auth_client, criar_veiculo, criar_motorista, db, hoje):
    """Não existe (e não pode passar a existir) receita de categoria 'caucao'."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    _contrato(auth_client, veiculo, motorista, hoje, deposit_amount="2000.00")

    categorias = set(db.scalars(select(Revenue.category)).all())
    assert RevenueCategory.caucao_retida not in categorias
    assert not any(c.value == "caucao" for c in RevenueCategory), (
        "criar a categoria 'caucao' contaria o lucro em dobro (MANIFESTO.md)"
    )

    # As cobranças semanais nasceram (em aberto) — mas nenhuma é da caução.
    recebido = db.scalars(
        select(Revenue).where(Revenue.status == RevenueStatus.paid)
    ).all()
    assert recebido == []


def test_devolver_tudo_nao_muda_o_lucro(
    auth_client, criar_veiculo, criar_motorista, lucro, db, hoje
):
    """Encerrou devolvendo os R$ 2.000: o dinheiro nunca foi do dono. Lucro intacto."""
    veiculo = criar_veiculo(purchase_price="40000.00")
    motorista = criar_motorista()
    contrato = _contrato(auth_client, veiculo, motorista, hoje, deposit_amount="2000.00")

    antes = lucro(veiculo["id"])

    r = auth_client.post(
        f"/contracts/{contrato['id']}/finish",
        json={"end_date": str(hoje), "deposit_returned_amount": "2000.00"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["deposit_status"] == "settled"
    assert Decimal(r.json()["deposit_returned_amount"]) == Decimal("2000.00")

    assert lucro(veiculo["id"]) == antes, "devolveu tudo → o lucro não muda"

    retidas = db.scalars(
        select(Revenue).where(Revenue.category == RevenueCategory.caucao_retida)
    ).all()
    assert retidas == [], "não reteve nada → não existe receita de caução retida"


def test_reter_500_sobe_o_lucro_em_exatamente_500(
    auth_client, criar_veiculo, criar_motorista, lucro, db, hoje
):
    """Reteve R$ 500 por avaria: o lucro sobe R$ 500. Nem mais, nem menos."""
    veiculo = criar_veiculo(purchase_price="40000.00")
    motorista = criar_motorista()
    contrato = _contrato(auth_client, veiculo, motorista, hoje, deposit_amount="2000.00")

    antes = lucro(veiculo["id"])

    r = auth_client.post(
        f"/contracts/{contrato['id']}/finish",
        json={
            "end_date": str(hoje),
            "deposit_returned_amount": "1500.00",
            "notes": "Retido R$ 500 por avaria no para-choque",
        },
    )
    assert r.status_code == 200, r.text

    assert lucro(veiculo["id"]) == antes + Decimal("500.00")

    # ...e o dinheiro tem lastro: existe UMA receita de caução retida, de exatamente 500.
    retidas = db.scalars(
        select(Revenue).where(Revenue.category == RevenueCategory.caucao_retida)
    ).all()
    assert len(retidas) == 1
    retida = retidas[0]
    assert retida.amount == Decimal("500.00")
    assert str(retida.vehicle_id) == veiculo["id"]
    assert str(retida.contract_id) == contrato["id"]
    # Já nasce PAGA: o dinheiro está com o dono desde a assinatura do contrato.
    assert retida.status == RevenueStatus.paid
    assert retida.paid_amount == Decimal("500.00")


def test_reter_tudo(auth_client, criar_veiculo, criar_motorista, lucro, hoje):
    """Motorista sumiu com o carro batido: a caução inteira vira receita."""
    veiculo = criar_veiculo(purchase_price="40000.00")
    motorista = criar_motorista()
    contrato = _contrato(auth_client, veiculo, motorista, hoje, deposit_amount="2000.00")

    antes = lucro(veiculo["id"])

    r = auth_client.post(
        f"/contracts/{contrato['id']}/finish",
        json={"end_date": str(hoje), "deposit_returned_amount": "0.00"},
    )
    assert r.status_code == 200, r.text

    assert lucro(veiculo["id"]) == antes + Decimal("2000.00")


def test_devolver_mais_do_que_recebeu_e_recusado(
    auth_client, criar_veiculo, criar_motorista, hoje
):
    """R$ 2.500 devolvidos de uma caução de R$ 2.000 é dinheiro saindo do nada."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    contrato = _contrato(auth_client, veiculo, motorista, hoje, deposit_amount="2000.00")

    r = auth_client.post(
        f"/contracts/{contrato['id']}/finish",
        json={"end_date": str(hoje), "deposit_returned_amount": "2500.00"},
    )
    assert r.status_code == 400, r.text
    assert "error" in r.json()

    # E o contrato continua de pé — nada foi encerrado pela metade.
    contrato_agora = auth_client.get(f"/contracts/{contrato['id']}").json()
    assert contrato_agora["status"] == "active"
    assert contrato_agora["deposit_status"] == "held"


def test_encerrar_duas_vezes_e_recusado(auth_client, criar_veiculo, criar_motorista, lucro, hoje):
    """Sem isso, encerrar de novo retendo 500 criaria uma segunda receita de caução."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    contrato = _contrato(auth_client, veiculo, motorista, hoje, deposit_amount="2000.00")

    primeiro = auth_client.post(
        f"/contracts/{contrato['id']}/finish",
        json={"end_date": str(hoje), "deposit_returned_amount": "1500.00"},
    )
    assert primeiro.status_code == 200
    depois_do_primeiro = lucro(veiculo["id"])

    segundo = auth_client.post(
        f"/contracts/{contrato['id']}/finish",
        json={"end_date": str(hoje), "deposit_returned_amount": "1500.00"},
    )
    assert segundo.status_code == 409, segundo.text
    assert lucro(veiculo["id"]) == depois_do_primeiro
