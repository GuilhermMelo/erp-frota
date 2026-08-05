"""Multa: despesa + reembolso = líquido zero.

A despesa é lançada SEMPRE que o dono paga — reembolsada ou não. Se o motorista devolve
o dinheiro, entra uma receita `reembolso` ligada à mesma multa e o líquido zera sozinho.

Registrar só as multas não reembolsadas seria mais curto e perderia as duas coisas que
importam: quanto já se pagou de multa, e quanto cada motorista deve.
"""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.domains.expenses.models import Expense, ExpenseOrigin, ExpenseStatus
from app.domains.revenues.models import Revenue, RevenueCategory


def _multa(auth_client, veiculo, hoje, motorista=None, **kwargs) -> dict:
    payload = {
        "vehicle_id": veiculo["id"],
        "driver_id": motorista["id"] if motorista else None,
        "infraction_date": str(hoje - timedelta(days=20)),
        "description": "Excesso de velocidade",
        "amount": "300.00",
        "points": 5,
    }
    payload.update(kwargs)
    r = auth_client.post("/fines", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_multa_pendente_ainda_nao_custou_nada(
    auth_client, criar_veiculo, criar_motorista, lucro, hoje
):
    """A multa chegou, mas o dono ainda não pagou. O carro não sentiu nada."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    antes = lucro(veiculo["id"])

    multa = _multa(auth_client, veiculo, hoje, motorista)
    assert multa["status"] == "pending"

    assert lucro(veiculo["id"]) == antes
    assert auth_client.get("/expenses", params={"vehicle_id": veiculo["id"]}).json() == []


def test_multa_paga_derruba_o_lucro_e_vira_despesa(
    auth_client, criar_veiculo, criar_motorista, lucro, db, hoje
):
    """Pagou R$ 300 → o lucro do carro cai R$ 300 e nasce uma despesa `origin='fine'`."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    antes = lucro(veiculo["id"])

    multa = _multa(auth_client, veiculo, hoje, motorista, amount="300.00")
    r = auth_client.post(
        f"/fines/{multa['id']}/pay", json={"paid_on": str(hoje - timedelta(days=5))}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paid"

    assert lucro(veiculo["id"]) == antes - Decimal("300.00")

    despesas = db.scalars(select(Expense).where(Expense.fine_id == UUID(multa["id"]))).all()
    assert len(despesas) == 1, "uma multa paga gera UMA despesa (duas contariam o custo em dobro)"
    despesa = despesas[0]
    assert despesa.origin == ExpenseOrigin.fine
    assert despesa.status == ExpenseStatus.paid
    assert despesa.amount == Decimal("300.00")
    assert despesa.category.code == "multas"
    # Sem o motorista na despesa não dá para saber quanto cada um deve.
    assert str(despesa.driver_id) == motorista["id"]
    # Competência é o dia da INFRAÇÃO (o fato); o caixa é o paid_on.
    assert despesa.competence_date == hoje - timedelta(days=20)
    assert despesa.paid_on == hoje - timedelta(days=5)


def test_reembolso_do_motorista_zera_o_custo(
    auth_client, criar_veiculo, criar_motorista, lucro, db, hoje
):
    """O motorista devolveu os R$ 300: o lucro VOLTA ao que era e `net_cost` dá zero."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    antes = lucro(veiculo["id"])

    multa = _multa(auth_client, veiculo, hoje, motorista, amount="300.00")
    auth_client.post(f"/fines/{multa['id']}/pay", json={"paid_on": str(hoje - timedelta(days=5))})
    assert lucro(veiculo["id"]) == antes - Decimal("300.00")

    r = auth_client.post(
        f"/fines/{multa['id']}/reimburse",
        json={"amount": "300.00", "paid_on": str(hoje), "method": "pix"},
    )
    assert r.status_code == 200, r.text

    assert lucro(veiculo["id"]) == antes, "reembolsou tudo → o líquido da multa é ZERO"

    detalhe = auth_client.get(f"/fines/{multa['id']}").json()
    assert Decimal(detalhe["reimbursed_amount"]) == Decimal("300.00")
    assert Decimal(detalhe["net_cost"]) == Decimal("0.00")
    # A multa continua PAGA: o dono pagou mesmo. Quem conta a história é o net_cost.
    assert detalhe["status"] == "paid"

    # A despesa NÃO foi apagada: o rastro de quanto já se pagou de multa se perderia.
    assert db.scalar(select(Expense).where(Expense.fine_id == UUID(multa["id"]))) is not None

    reembolsos = db.scalars(
        select(Revenue).where(Revenue.category == RevenueCategory.reembolso)
    ).all()
    assert len(reembolsos) == 1
    assert reembolsos[0].amount == Decimal("300.00")
    assert str(reembolsos[0].fine_id) == multa["id"]


def test_reembolso_parcial(auth_client, criar_veiculo, criar_motorista, lucro, hoje):
    """Motorista pagou metade: o carro fica com metade do custo."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    antes = lucro(veiculo["id"])

    multa = _multa(auth_client, veiculo, hoje, motorista, amount="300.00")
    auth_client.post(f"/fines/{multa['id']}/pay", json={"paid_on": str(hoje)})
    auth_client.post(
        f"/fines/{multa['id']}/reimburse", json={"amount": "100.00", "paid_on": str(hoje)}
    )

    assert lucro(veiculo["id"]) == antes - Decimal("200.00")
    assert Decimal(auth_client.get(f"/fines/{multa['id']}").json()["net_cost"]) == Decimal("200.00")


def test_reembolso_maior_que_a_multa_e_recusado(
    auth_client, criar_veiculo, criar_motorista, lucro, hoje
):
    """R$ 400 de reembolso numa multa de R$ 300 viraria lucro do nada."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    multa = _multa(auth_client, veiculo, hoje, motorista, amount="300.00")
    auth_client.post(f"/fines/{multa['id']}/pay", json={"paid_on": str(hoje)})

    depois_de_pagar = lucro(veiculo["id"])

    r = auth_client.post(
        f"/fines/{multa['id']}/reimburse", json={"amount": "400.00", "paid_on": str(hoje)}
    )
    assert r.status_code == 400, r.text
    assert "error" in r.json()

    assert lucro(veiculo["id"]) == depois_de_pagar, "nada foi lançado"


def test_soma_dos_reembolsos_nao_passa_da_multa(
    auth_client, criar_veiculo, criar_motorista, hoje
):
    """Dois reembolsos de R$ 200 numa multa de R$ 300: o segundo é recusado."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    multa = _multa(auth_client, veiculo, hoje, motorista, amount="300.00")
    auth_client.post(f"/fines/{multa['id']}/pay", json={"paid_on": str(hoje)})

    primeiro = auth_client.post(
        f"/fines/{multa['id']}/reimburse", json={"amount": "200.00", "paid_on": str(hoje)}
    )
    assert primeiro.status_code == 200

    segundo = auth_client.post(
        f"/fines/{multa['id']}/reimburse", json={"amount": "200.00", "paid_on": str(hoje)}
    )
    assert segundo.status_code == 400, segundo.text

    assert Decimal(auth_client.get(f"/fines/{multa['id']}").json()["net_cost"]) == Decimal("100.00")


def test_reembolso_de_multa_sem_motorista_e_recusado(auth_client, criar_veiculo, hoje):
    """Ninguém sabe quem dirigia: não há de quem cobrar."""
    veiculo = criar_veiculo()
    multa = _multa(auth_client, veiculo, hoje, motorista=None, amount="300.00")
    assert multa["driver_id"] is None

    auth_client.post(f"/fines/{multa['id']}/pay", json={"paid_on": str(hoje)})

    r = auth_client.post(
        f"/fines/{multa['id']}/reimburse", json={"amount": "300.00", "paid_on": str(hoje)}
    )
    assert r.status_code == 400, r.text
    assert "motorista" in r.json()["error"]["message"].lower()


def test_multa_nao_paga_e_custo_real_do_carro(auth_client, criar_veiculo, criar_motorista, hoje):
    """A contraprova do líquido zero: sem reembolso, a multa é custo do carro."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    multa = _multa(auth_client, veiculo, hoje, motorista, amount="300.00")
    auth_client.post(f"/fines/{multa['id']}/pay", json={"paid_on": str(hoje)})

    detalhe = auth_client.get(f"/fines/{multa['id']}").json()
    assert Decimal(detalhe["reimbursed_amount"]) == Decimal("0.00")
    assert Decimal(detalhe["net_cost"]) == Decimal("300.00")


def test_corrigir_o_valor_da_multa_corrige_a_despesa(
    auth_client, criar_veiculo, criar_motorista, lucro, db, hoje
):
    """O AIT veio com outro valor: a despesa do carro segue a multa, na MESMA linha."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    antes = lucro(veiculo["id"])

    multa = _multa(auth_client, veiculo, hoje, motorista, amount="300.00")
    auth_client.post(f"/fines/{multa['id']}/pay", json={"paid_on": str(hoje)})

    r = auth_client.patch(f"/fines/{multa['id']}", json={"amount": "195.23"})
    assert r.status_code == 200, r.text

    assert lucro(veiculo["id"]) == antes - Decimal("195.23")

    despesas = db.scalars(select(Expense).where(Expense.fine_id == UUID(multa["id"]))).all()
    assert len(despesas) == 1, "corrigiu a mesma despesa; não criou uma segunda"
    assert despesas[0].amount == Decimal("195.23")


def test_apagar_a_multa_apaga_a_despesa_e_deixa_rastro(
    auth_client, criar_veiculo, criar_motorista, lucro, db, hoje
):
    """REGRESSÃO (bug real): a despesa sumia do resultado do carro SEM entrar no log.

    `expenses.fine_id` é ON DELETE CASCADE. Apagar a multa fazia o Postgres apagar a
    despesa por baixo do ORM — e o listener de auditoria é cego a cascata de banco
    (ARQUITETURA.md, regra 3). O custo do veículo caía R$ 300 e o log não tinha uma linha
    sequer dizendo quem apagou o quê.
    """
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    antes = lucro(veiculo["id"])

    multa = _multa(auth_client, veiculo, hoje, motorista, amount="300.00")
    auth_client.post(f"/fines/{multa['id']}/pay", json={"paid_on": str(hoje)})
    despesa = db.scalar(select(Expense).where(Expense.fine_id == UUID(multa["id"])))
    assert lucro(veiculo["id"]) == antes - Decimal("300.00")

    assert auth_client.delete(f"/fines/{multa['id']}").status_code == 204

    # A despesa foi junto (o custo volta)...
    assert db.scalar(select(Expense).where(Expense.fine_id == UUID(multa["id"]))) is None
    assert lucro(veiculo["id"]) == antes

    # ...e o log conta quem a apagou.
    logs = auth_client.get(
        "/audit", params={"entity_type": "expenses", "entity_id": str(despesa.id)}
    ).json()
    deletes = [x for x in logs if x["action"] == "delete"]
    assert len(deletes) == 1, "a despesa não pode sumir do resultado do carro sem rastro"
    assert deletes[0]["entity_code"] == despesa.code
    assert deletes[0]["actor_email"] != "sistema"


def test_multa_com_reembolso_nao_pode_ser_apagada(
    auth_client, criar_veiculo, criar_motorista, hoje
):
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    multa = _multa(auth_client, veiculo, hoje, motorista, amount="300.00")
    auth_client.post(f"/fines/{multa['id']}/pay", json={"paid_on": str(hoje)})
    auth_client.post(
        f"/fines/{multa['id']}/reimburse", json={"amount": "300.00", "paid_on": str(hoje)}
    )

    r = auth_client.delete(f"/fines/{multa['id']}")
    assert r.status_code == 409, r.text
    assert auth_client.get(f"/fines/{multa['id']}").status_code == 200
