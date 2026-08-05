"""Auditoria: o log registra O QUÊ, QUEM e QUANDO.

Duas armadilhas moram aqui, e as duas são silenciosas:

1. **`actor_email` = 'sistema'.** O listener lê o usuário de um ContextVar preenchido pelo
   `get_current_user`. Se essa dependência virar `def` (em vez de `async def`), o FastAPI
   a roda numa thread do pool, que recebe uma CÓPIA do contexto — e todo log passa a sair
   como "sistema". O log registraria o quê e perderia o quem, que é a razão de ele existir.

2. **`entity_id` NULL.** O `id` (gen_random_uuid) e o `code` (nextval) só existem DEPOIS
   do flush. Registrar a criação em `before_flush` gravaria entity_id nulo — e o log de
   criação de um veículo nunca apareceria na busca por aquele veículo.
"""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from tests.conftest import ADMIN_EMAIL


def _logs(auth_client, **params) -> list[dict]:
    r = auth_client.get("/audit", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_criacao_de_veiculo_registra_quem_e_qual(auth_client, criar_veiculo):
    veiculo = criar_veiculo()
    assert veiculo["code"] == "CAR000001", "primeiro veículo do teste"

    logs = _logs(auth_client, entity_type="vehicles", entity_id=veiculo["id"])
    criacoes = [x for x in logs if x["action"] == "create"]
    assert len(criacoes) == 1, "o log de criação tem que ser achável pelo entity_id"

    log = criacoes[0]
    assert log["entity_id"] == veiculo["id"], "entity_id não pode ser nulo"
    assert log["entity_code"] == "CAR000001"
    assert log["entity_code"] == veiculo["code"]
    assert log["entity_type"] == "vehicles"
    assert log["actor_email"] == ADMIN_EMAIL, "quem fez, não 'sistema'"
    assert log["actor_email"] != "sistema"
    assert log["actor_user_id"] is not None

    # O "para" da criação traz o estado inicial do veículo.
    assert log["changes"]["plate"]["para"] == veiculo["plate"]
    assert log["changes"]["purchase_price"]["para"] == "50000.00"


def test_venda_aparece_no_log_com_o_de_para(auth_client, criar_veiculo, hoje):
    veiculo = criar_veiculo(purchase_price="50000.00")

    r = auth_client.post(
        f"/vehicles/{veiculo['id']}/sell",
        json={"sale_price": "45000.00", "sale_date": str(hoje)},
    )
    assert r.status_code == 200, r.text

    logs = _logs(auth_client, entity_type="vehicles", entity_id=veiculo["id"])
    vendas = [
        x for x in logs if x["action"] == "update" and "sale_price" in (x["changes"] or {})
    ]
    assert len(vendas) == 1, "a venda TEM que aparecer no log"

    log = vendas[0]
    assert log["changes"]["sale_price"]["de"] is None
    assert log["changes"]["sale_price"]["para"] == "45000.00"
    assert log["changes"]["sale_date"]["para"] == str(hoje)
    assert log["changes"]["status"] == {"de": "available", "para": "sold"}
    assert log["actor_email"] == ADMIN_EMAIL
    assert log["entity_code"] == veiculo["code"]


def test_exclusao_registra_o_delete(auth_client, criar_veiculo):
    """Soft delete de veículo é um UPDATE em `deleted_at` — e aparece como tal."""
    veiculo = criar_veiculo()
    assert auth_client.delete(f"/vehicles/{veiculo['id']}").status_code == 204

    logs = _logs(auth_client, entity_type="vehicles", entity_id=veiculo["id"])
    updates = [x for x in logs if x["action"] == "update" and "deleted_at" in (x["changes"] or {})]
    assert len(updates) == 1
    assert updates[0]["changes"]["deleted_at"]["de"] is None
    assert updates[0]["changes"]["deleted_at"]["para"] is not None
    assert updates[0]["actor_email"] == ADMIN_EMAIL


def test_delete_fisico_de_despesa_registra_o_que_sumiu(
    auth_client, criar_veiculo, lancar_despesa
):
    veiculo = criar_veiculo()
    despesa = lancar_despesa(veiculo["id"], "500.00")

    assert auth_client.delete(f"/expenses/{despesa['id']}").status_code == 204

    logs = _logs(auth_client, entity_type="expenses", entity_id=despesa["id"])
    deletes = [x for x in logs if x["action"] == "delete"]
    assert len(deletes) == 1
    assert deletes[0]["entity_code"] == despesa["code"]
    assert deletes[0]["actor_email"] == ADMIN_EMAIL


def test_o_dinheiro_que_entra_e_auditado(auth_client, criar_veiculo, lancar_receita):
    """Receita e pagamento nascem no mesmo flush — os DOIS têm que estar no log."""
    veiculo = criar_veiculo()
    receita = lancar_receita(veiculo["id"], "800.00")

    receitas = _logs(auth_client, entity_type="revenues", entity_id=receita["id"])
    assert [x["action"] for x in receitas].count("create") == 1
    assert receitas[0]["actor_email"] == ADMIN_EMAIL

    pagamento = receita["payments"][0]
    pagamentos = _logs(auth_client, entity_type="revenue_payments", entity_id=pagamento["id"])
    assert len(pagamentos) == 1
    assert pagamentos[0]["action"] == "create"
    assert pagamentos[0]["changes"]["amount"]["para"] == "800.00"
    assert pagamentos[0]["actor_email"] == ADMIN_EMAIL


def test_login_e_registrado(auth_client, client):
    """O `auth_client` já fez login — e o falho também tem que aparecer."""
    client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": "errada"})

    logs = _logs(auth_client, entity_type="users")
    acoes = [x["action"] for x in logs]
    assert "login" in acoes
    assert "login_failed" in acoes

    falha = next(x for x in logs if x["action"] == "login_failed")
    assert falha["actor_email"] == ADMIN_EMAIL


def test_apagar_manutencao_deixa_rastro_da_despesa(auth_client, criar_veiculo, lucro, hoje, db):
    """REGRESSÃO (bug real): a despesa da manutenção sumia do custo do carro SEM log.

    `expenses.maintenance_id` é ON DELETE CASCADE. Apagar a manutenção fazia o Postgres
    apagar a despesa por baixo do ORM, e o listener é cego a cascata de banco (ARQUITETURA.md,
    regra 3): o custo do veículo caía e o log não registrava nada.
    """
    from sqlalchemy import select

    from app.domains.expenses.models import Expense

    veiculo = criar_veiculo()
    antes = lucro(veiculo["id"])

    r = auth_client.post(
        "/maintenances",
        json={
            "vehicle_id": veiculo["id"],
            "kind": "Troca de óleo",
            "amount": "450.00",
            "performed_on": str(hoje),
            "odometer": 46000,
        },
    )
    assert r.status_code == 201, r.text
    manutencao = r.json()

    assert lucro(veiculo["id"]) == antes - Decimal("450.00")
    despesa = db.scalar(select(Expense).where(Expense.maintenance_id == UUID(manutencao["id"])))
    assert despesa is not None

    assert auth_client.delete(f"/maintenances/{manutencao['id']}").status_code == 204
    assert lucro(veiculo["id"]) == antes

    logs = _logs(auth_client, entity_type="expenses", entity_id=str(despesa.id))
    deletes = [x for x in logs if x["action"] == "delete"]
    assert len(deletes) == 1, "a despesa não pode sumir do custo do carro sem rastro"
    assert deletes[0]["actor_email"] == ADMIN_EMAIL


def test_catalogo_do_seed_nao_polui_o_log(auth_client, criar_veiculo):
    """`expense_categories` e `checklist_items` são catálogo, não operação."""
    criar_veiculo()
    tabelas = {x["entity_type"] for x in _logs(auth_client, limit=500)}
    assert "expense_categories" not in tabelas
    assert "checklist_items" not in tabelas
    assert "audit_logs" not in tabelas, "o log não pode se auditar (recursão)"


def test_o_log_nao_e_editavel_nem_apagavel(auth_client, criar_veiculo):
    """Append-only: se existisse endpoint de escrita, o log deixaria de ser prova."""
    criar_veiculo()
    log = _logs(auth_client)[0]

    for method in ("PATCH", "PUT", "DELETE"):
        r = auth_client.request(method, f"/audit/{log['id']}")
        assert r.status_code in (404, 405), f"{method} /audit/{{id}} não pode existir"


def test_a_caucao_retida_deixa_rastro(
    auth_client, criar_veiculo, criar_motorista, hoje
):
    """O dinheiro que o dono ficou tem nome, valor e autor no log."""
    veiculo = criar_veiculo()
    motorista = criar_motorista()
    contrato = auth_client.post(
        "/contracts",
        json={
            "vehicle_id": veiculo["id"],
            "driver_id": motorista["id"],
            "start_date": str(hoje - timedelta(days=7)),
            "weekly_amount": "800.00",
            "deposit_amount": "2000.00",
        },
    ).json()

    auth_client.post(
        f"/contracts/{contrato['id']}/finish",
        json={"end_date": str(hoje), "deposit_returned_amount": "1500.00"},
    )

    logs = _logs(auth_client, entity_type="revenues", limit=500)
    retidas = [
        x
        for x in logs
        if x["action"] == "create" and x["changes"]["category"]["para"] == "caucao_retida"
    ]
    assert len(retidas) == 1
    assert Decimal(retidas[0]["changes"]["amount"]["para"]) == Decimal("500.00")
    assert retidas[0]["actor_email"] == ADMIN_EMAIL
