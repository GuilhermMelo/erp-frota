"""A conta do veículo — a razão de existir do produto.

    Lucro = receitas − despesas − valor_compra + valor_venda

Se algum teste deste arquivo falhar, o modelo financeiro está errado. Não é um teste de
regressão de código: é o contrato do produto.
"""

from datetime import date, timedelta
from decimal import Decimal


def _dia_de_mes_atras(hoje: date, n: int) -> date:
    """Dia 15 de `n` meses atrás.

    Dia 15 de propósito: qualquer outro dia faria o teste quebrar sozinho no dia 31 de um
    mês, ou em fevereiro — falha por calendário, não por regra de negócio.
    """
    ano, mes = hoje.year, hoje.month - n
    while mes <= 0:
        mes += 12
        ano -= 1
    return date(ano, mes, 15)


def test_ciclo_de_vida_do_veiculo_fecha_em_zero(
    auth_client, criar_veiculo, criar_motorista, lancar_receita, lancar_despesa, resultado, hoje
):
    """Comprado por 50.000 → 10 aluguéis de 800 → 3.000 de despesas → vendido por 45.000.

    8.000 − 3.000 − 50.000 + 45.000 = 0,00. Tem que fechar em ZERO, exato.
    """
    veiculo = criar_veiculo(
        purchase_price="50000.00", purchase_odometer=20000, current_odometer=45000
    )
    motorista = criar_motorista()

    for i in range(10):
        dia = hoje - timedelta(days=70 - i * 7)
        lancar_receita(
            veiculo["id"],
            "800.00",
            driver_id=motorista["id"],
            description=f"Aluguel semana {i + 1}",
            competence_date=str(dia),
            due_date=str(dia),
            paid_on=str(dia),
        )

    lancar_despesa(veiculo["id"], "1200.00", "manutencao")
    lancar_despesa(veiculo["id"], "1000.00", "ipva")
    lancar_despesa(veiculo["id"], "800.00", "pneus")

    # --- antes da venda: o carro ainda não se pagou ---
    r = resultado(veiculo["id"])
    assert Decimal(r["total_received"]) == Decimal("8000.00")
    assert Decimal(r["total_cost"]) == Decimal("3000.00")
    assert Decimal(r["investment"]) == Decimal("50000.00")
    assert Decimal(r["profit"]) == Decimal("-45000.00")
    assert r["km_driven"] == 25000
    assert Decimal(r["cost_per_km"]) == Decimal("0.12")  # 3.000 / 25.000 km

    # --- a venda fecha o ciclo ---
    venda = auth_client.post(
        f"/vehicles/{veiculo['id']}/sell",
        json={"sale_price": "45000.00", "sale_date": str(hoje)},
    )
    assert venda.status_code == 200, venda.text

    r = resultado(veiculo["id"])
    assert r["profit"] == "0.00", "8.000 − 3.000 − 50.000 + 45.000 tem que dar 0,00 exato"
    assert Decimal(r["profit"]) == Decimal("0.00")
    assert r["status"] == "sold"
    assert Decimal(r["sale_price"]) == Decimal("45000.00")


def test_nao_da_para_vender_um_carro_alugado(
    auth_client, criar_veiculo, criar_motorista, resultado, hoje
):
    """REGRESSÃO (bug real): vender um carro com contrato ativo corrompia a conta dele.

    O contrato continuava ATIVO depois da venda. Na semana seguinte a geração automática
    criava mais uma cobrança de aluguel — para um carro que não é mais do dono — e o lucro
    do veículo, que a venda tinha FECHADO em 0,00, subia sozinho. De quebra, a caução do
    motorista ficava presa num contrato de um carro que já não existe na frota.

    A regra espelho já existia do outro lado ("veículo vendido não pode ser alugado").
    """
    veiculo = criar_veiculo(purchase_price="50000.00")
    motorista = criar_motorista()

    contrato = auth_client.post(
        "/contracts",
        json={
            "vehicle_id": veiculo["id"],
            "driver_id": motorista["id"],
            "start_date": str(hoje),
            "weekly_amount": "800.00",
            "deposit_amount": "2000.00",
        },
    )
    assert contrato.status_code == 201, contrato.text

    venda = auth_client.post(
        f"/vehicles/{veiculo['id']}/sell",
        json={"sale_price": "50000.00", "sale_date": str(hoje)},
    )
    assert venda.status_code == 409, venda.text
    assert contrato.json()["code"] in venda.json()["error"]["message"]

    assert auth_client.get(f"/vehicles/{veiculo['id']}").json()["status"] != "sold"

    # Encerrado o contrato (e acertada a caução), a venda passa.
    encerrar = auth_client.post(
        f"/contracts/{contrato.json()['id']}/finish",
        json={"end_date": str(hoje), "deposit_returned_amount": "2000.00"},
    )
    assert encerrar.status_code == 200, encerrar.text

    venda = auth_client.post(
        f"/vehicles/{veiculo['id']}/sell",
        json={"sale_price": "50000.00", "sale_date": str(hoje)},
    )
    assert venda.status_code == 200, venda.text
    assert Decimal(resultado(veiculo["id"])["profit"]) == Decimal("0.00")


def test_a_conta_do_carro_vendido_nao_se_mexe_mais(
    auth_client, criar_veiculo, criar_motorista, resultado, hoje
):
    """Depois da venda, a geração semanal não pode inventar receita para o carro."""
    veiculo = criar_veiculo(purchase_price="50000.00")
    auth_client.post(
        f"/vehicles/{veiculo['id']}/sell",
        json={"sale_price": "50000.00", "sale_date": str(hoje)},
    )
    assert Decimal(resultado(veiculo["id"])["profit"]) == Decimal("0.00")

    # Não há como criar contrato para um carro vendido...
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
    assert r.status_code == 409, r.text

    # ...e a geração da frota inteira não cria nada para ele.
    assert auth_client.post("/contracts/generate-charges").json()["geradas"] == 0
    assert Decimal(resultado(veiculo["id"])["profit"]) == Decimal("0.00")


def test_venda_nao_vira_receita(auth_client, criar_veiculo, resultado, hoje):
    """O valor de venda mora em `vehicles.sale_price` e em lugar nenhum mais.

    Se a venda também virasse uma Revenue, o lucro sairia contado em dobro.
    """
    veiculo = criar_veiculo(purchase_price="50000.00")
    auth_client.post(
        f"/vehicles/{veiculo['id']}/sell",
        json={"sale_price": "45000.00", "sale_date": str(hoje)},
    )

    receitas = auth_client.get("/revenues", params={"vehicle_id": veiculo["id"]}).json()
    assert receitas == [], "a venda não pode ter criado receita nenhuma"

    r = resultado(veiculo["id"])
    assert Decimal(r["total_received"]) == Decimal("0")
    assert Decimal(r["profit"]) == Decimal("-5000.00")  # só a compra e a venda


def test_compra_nao_vira_despesa(criar_veiculo, auth_client, resultado):
    """O valor de compra mora em `vehicles.purchase_price`. Não é despesa."""
    veiculo = criar_veiculo(purchase_price="50000.00")

    despesas = auth_client.get("/expenses", params={"vehicle_id": veiculo["id"]}).json()
    assert despesas == []

    r = resultado(veiculo["id"])
    assert Decimal(r["total_cost"]) == Decimal("0")
    assert Decimal(r["investment"]) == Decimal("50000.00")


# ---------------------------------------------------------------------------
# CAPEX: melhoria é INVESTIMENTO no carro, não custo do mês.
# ---------------------------------------------------------------------------
def test_capex_entra_no_investimento_e_nao_no_custo(
    criar_veiculo, lancar_despesa, resultado, categorias
):
    """Uma blindagem de R$ 5.000 aumenta o INVESTIMENTO, não o custo de operação.

    Sem essa separação o custo por km ficaria absurdo no mês da melhoria — e o dono
    concluiria que o carro dá prejuízo justamente quando investiu nele.
    """
    veiculo = criar_veiculo(
        purchase_price="50000.00", purchase_odometer=20000, current_odometer=45000
    )
    lancar_despesa(veiculo["id"], "3000.00", "manutencao")

    antes = resultado(veiculo["id"])
    assert Decimal(antes["cost_per_km"]) == Decimal("0.12")  # 3.000 / 25.000

    lancar_despesa(veiculo["id"], "5000.00", "melhorias")  # is_capex=True

    depois = resultado(veiculo["id"])
    assert Decimal(depois["total_cost"]) == Decimal("3000.00"), "capex NÃO é custo"
    assert Decimal(depois["total_capex"]) == Decimal("5000.00")
    assert Decimal(depois["investment"]) == Decimal("55000.00"), "50.000 de compra + 5.000"
    assert Decimal(depois["cost_per_km"]) == Decimal("0.12"), "o custo por km não sente o capex"

    # O lucro sente: o dinheiro saiu do bolso do dono do mesmo jeito.
    # 0 de receita − 3.000 de custo − 55.000 de investimento = −58.000.
    assert Decimal(depois["profit"]) == Decimal("-58000.00")


def test_categoria_melhorias_e_a_unica_capex(categorias, auth_client):
    """O seed marca `melhorias` como capex. Se isso mudar, o teste acima vira mentira."""
    todas = auth_client.get("/expense-categories").json()
    capex = {c["code"] for c in todas if c["is_capex"]}
    assert capex == {"melhorias"}
    assert "melhorias" in categorias


# ---------------------------------------------------------------------------
# Divisão por zero: o carro de graça e o carro que não rodou.
# ---------------------------------------------------------------------------
def test_roi_e_none_quando_o_carro_nao_custou_nada(criar_veiculo, resultado, hoje):
    """Carro recebido de graça: ROI dividiria por zero. Tem que ser NULL, não 500."""
    veiculo = criar_veiculo(
        purchase_price="0.00",
        purchase_date=str(hoje),
        purchase_odometer=100,
        current_odometer=5100,
    )
    r = resultado(veiculo["id"])

    assert r["roi"] is None, "investimento zero → ROI indefinido, não 0 e nem erro 500"
    assert Decimal(r["investment"]) == Decimal("0.00")


def test_custo_por_km_e_none_quando_o_carro_nao_rodou(criar_veiculo, lancar_despesa, resultado):
    """Carro novo (odômetro de compra == atual): custo/km dividiria por zero."""
    veiculo = criar_veiculo(purchase_odometer=100, current_odometer=100)
    lancar_despesa(veiculo["id"], "500.00")

    r = resultado(veiculo["id"])
    assert r["km_driven"] == 0
    assert r["cost_per_km"] is None
    assert r["revenue_per_km"] is None
    assert Decimal(r["total_cost"]) == Decimal("500.00"), "a despesa existe; só o /km é que não"


def test_roi_calculado_quando_ha_investimento(criar_veiculo, lancar_receita, resultado):
    """A contraprova: com investimento > 0 o ROI é um número de verdade."""
    veiculo = criar_veiculo(purchase_price="10000.00")
    lancar_receita(veiculo["id"], "1000.00")

    r = resultado(veiculo["id"])
    # (1.000 − 0 − 10.000) / 10.000 = −0,9
    assert Decimal(r["roi"]) == Decimal("-0.9")


# ---------------------------------------------------------------------------
# "Se eu vender hoje, saio no lucro?"
# ---------------------------------------------------------------------------
def test_profit_if_sold_today_usa_o_valor_de_mercado(
    criar_veiculo, lancar_receita, lancar_despesa, resultado
):
    veiculo = criar_veiculo(purchase_price="50000.00", estimated_market_value="48000.00")
    lancar_receita(veiculo["id"], "8000.00")
    lancar_despesa(veiculo["id"], "3000.00")

    r = resultado(veiculo["id"])
    # 8.000 − 3.000 − 50.000 + 48.000 = 3.000
    assert Decimal(r["profit_if_sold_today"]) == Decimal("3000.00")
    assert Decimal(r["profit"]) == Decimal("-45000.00"), "o lucro REALIZADO não usa estimativa"


def test_profit_if_sold_today_e_none_sem_estimativa(criar_veiculo, resultado):
    """Sem valor de mercado, a pergunta não tem resposta. Melhor vazio que inventado."""
    veiculo = criar_veiculo(purchase_price="50000.00")
    assert resultado(veiculo["id"])["profit_if_sold_today"] is None


def test_profit_if_sold_today_e_none_depois_da_venda(auth_client, criar_veiculo, resultado, hoje):
    """Carro vendido: "se eu vender hoje" deixou de fazer sentido."""
    veiculo = criar_veiculo(purchase_price="50000.00", estimated_market_value="48000.00")
    assert resultado(veiculo["id"])["profit_if_sold_today"] is not None

    auth_client.post(
        f"/vehicles/{veiculo['id']}/sell",
        json={"sale_price": "45000.00", "sale_date": str(hoje)},
    )

    r = resultado(veiculo["id"])
    assert r["profit_if_sold_today"] is None
    assert Decimal(r["profit"]) == Decimal("-5000.00"), "agora o que vale é a venda real"


# ---------------------------------------------------------------------------
# O ranking da frota: qual carro vender, qual comprar de novo.
# ---------------------------------------------------------------------------
def test_fleet_ordena_por_lucro_decrescente(
    auth_client, criar_veiculo, lancar_receita, lancar_despesa
):
    bom = criar_veiculo(purchase_price="10000.00")
    lancar_receita(bom["id"], "12000.00")  # lucro +2.000

    medio = criar_veiculo(purchase_price="10000.00")
    lancar_receita(medio["id"], "9000.00")  # lucro −1.000

    ruim = criar_veiculo(purchase_price="10000.00")
    lancar_despesa(ruim["id"], "5000.00")  # lucro −15.000

    frota = auth_client.get("/finance/fleet").json()
    assert len(frota) == 3

    lucros = [Decimal(v["profit"]) for v in frota]
    assert lucros == sorted(lucros, reverse=True), "a frota sai ordenada por lucro decrescente"
    assert [v["vehicle_id"] for v in frota] == [bom["id"], medio["id"], ruim["id"]]
    assert lucros == [Decimal("2000.00"), Decimal("-1000.00"), Decimal("-15000.00")]


def test_veiculo_excluido_some_da_frota(auth_client, criar_veiculo):
    """Soft delete: some da lista, mas o histórico financeiro continua no banco."""
    fica = criar_veiculo()
    sai = criar_veiculo()

    assert auth_client.delete(f"/vehicles/{sai['id']}").status_code == 204

    frota = auth_client.get("/finance/fleet").json()
    assert [v["vehicle_id"] for v in frota] == [fica["id"]]


# ---------------------------------------------------------------------------
# Regime de caixa: o que está em aberto não entra no lucro (mas aparece).
# ---------------------------------------------------------------------------
def test_receita_em_aberto_nao_entra_no_lucro(auth_client, criar_veiculo, resultado, hoje):
    """Cobrança emitida não é dinheiro no bolso. Ela aparece em `total_receivable`."""
    veiculo = criar_veiculo(purchase_price="10000.00")
    r = auth_client.post(
        "/revenues",
        json={
            "vehicle_id": veiculo["id"],
            "category": "aluguel",
            "amount": "800.00",
            "competence_date": str(hoje),
            "pay_now": False,
        },
    )
    assert r.status_code == 201, r.text

    conta = resultado(veiculo["id"])
    assert Decimal(conta["total_received"]) == Decimal("0")
    assert Decimal(conta["total_receivable"]) == Decimal("800.00")
    assert Decimal(conta["profit"]) == Decimal("-10000.00"), "o lucro não conta o que não entrou"


def test_despesa_pendente_nao_entra_no_lucro(
    auth_client, criar_veiculo, categorias, resultado, hoje
):
    veiculo = criar_veiculo(purchase_price="10000.00")
    r = auth_client.post(
        "/expenses",
        json={
            "vehicle_id": veiculo["id"],
            "category_id": categorias["ipva"],
            "amount": "1000.00",
            "competence_date": str(hoje),
            "status": "pending",
        },
    )
    assert r.status_code == 201, r.text

    conta = resultado(veiculo["id"])
    assert Decimal(conta["total_cost"]) == Decimal("0")
    assert Decimal(conta["total_expense_pending"]) == Decimal("1000.00")
    assert Decimal(conta["profit"]) == Decimal("-10000.00")


# ---------------------------------------------------------------------------
# Cada carro tem a SUA conta. Nada vaza de um para o outro.
# ---------------------------------------------------------------------------
def test_o_lancamento_de_um_carro_nao_vaza_no_outro(
    criar_veiculo, lancar_receita, lancar_despesa, resultado
):
    a = criar_veiculo(purchase_price="10000.00")
    b = criar_veiculo(purchase_price="10000.00")

    lancar_receita(a["id"], "900.00")
    lancar_despesa(a["id"], "500.00")

    conta_b = resultado(b["id"])
    assert Decimal(conta_b["total_received"]) == Decimal("0")
    assert Decimal(conta_b["total_cost"]) == Decimal("0")
    assert Decimal(conta_b["profit"]) == Decimal("-10000.00")

    conta_a = resultado(a["id"])
    assert Decimal(conta_a["profit"]) == Decimal("-9600.00")  # 900 − 500 − 10.000


def test_apagar_a_receita_devolve_o_lucro(auth_client, criar_veiculo, lancar_receita, lucro):
    """Ação de admin, e o lucro do carro acompanha na hora."""
    veiculo = criar_veiculo(purchase_price="10000.00")
    antes = lucro(veiculo["id"])

    receita = lancar_receita(veiculo["id"], "800.00")
    assert lucro(veiculo["id"]) == antes + Decimal("800.00")

    assert auth_client.delete(f"/revenues/{receita['id']}").status_code == 204
    assert lucro(veiculo["id"]) == antes


def test_corrigir_o_valor_de_compra_move_o_investimento(auth_client, criar_veiculo, resultado):
    veiculo = criar_veiculo(purchase_price="50000.00")

    r = auth_client.patch(f"/vehicles/{veiculo['id']}", json={"purchase_price": "45000.00"})
    assert r.status_code == 200, r.text

    conta = resultado(veiculo["id"])
    assert Decimal(conta["investment"]) == Decimal("45000.00")
    assert Decimal(conta["profit"]) == Decimal("-45000.00")


def test_veiculo_inexistente_ou_excluido_nao_tem_conta(auth_client, criar_veiculo, lancar_receita):
    assert auth_client.get("/finance/vehicles/" + "0" * 8 + "-0000-0000-0000-" + "0" * 12).status_code == 404

    veiculo = criar_veiculo()
    lancar_receita(veiculo["id"], "800.00")
    auth_client.delete(f"/vehicles/{veiculo['id']}")

    assert auth_client.get(f"/finance/vehicles/{veiculo['id']}").status_code == 404


# ---------------------------------------------------------------------------
# O carro que saiu da frota não pode continuar cobrando na tela inicial.
# ---------------------------------------------------------------------------
def test_cobranca_de_carro_excluido_sai_do_a_receber_e_da_inadimplencia(
    auth_client, criar_veiculo, hoje
):
    """BUG REAL, corrigido nesta sessão.

    `/finance/fleet` e `/finance/vehicles/{id}` já ignoravam o veículo soft-deletado (o
    segundo responde 404). `/finance/dashboard` e `/revenues/receivables` não ignoravam:
    a tela inicial anunciava "R$ 800 em atraso" de um carro que sumiu da frota, o dono
    clicava no número, chegava na cobrança e não conseguia abrir o veículo. Dois números
    sobre o mesmo dinheiro, e o auditável dizia o contrário do exibido.

    Como falha se o filtro sumir: os quatro `assert` de "depois" voltam a ver os R$ 800.
    """
    veiculo = criar_veiculo()
    ontem = hoje - timedelta(days=1)

    cobranca = auth_client.post(
        "/revenues",
        json={
            "vehicle_id": veiculo["id"],
            "category": "aluguel",
            "amount": "800.00",
            "competence_date": str(ontem),
            "due_date": str(ontem),
            "pay_now": False,
        },
    )
    assert cobranca.status_code == 201, cobranca.text

    # CONTROLE POSITIVO. Sem ele, o teste passaria também se a cobrança nunca tivesse
    # existido — que é a segunda armadilha do CLAUDE.md ("passar por ausência").
    antes = auth_client.get("/finance/dashboard").json()
    assert Decimal(antes["total_receivable"]) == Decimal("800.00")
    assert Decimal(antes["total_overdue"]) == Decimal("800.00")
    assert antes["overdue_count"] == 1
    em_atraso = auth_client.get("/revenues/receivables").json()
    assert [x["id"] for x in em_atraso] == [cobranca.json()["id"]]

    assert auth_client.delete(f"/vehicles/{veiculo['id']}").status_code == 204

    depois = auth_client.get("/finance/dashboard").json()
    assert Decimal(depois["total_receivable"]) == Decimal("0.00")
    assert Decimal(depois["total_overdue"]) == Decimal("0.00")
    assert depois["overdue_count"] == 0
    assert auth_client.get("/revenues/receivables").json() == []
    # A razão de tudo isso: a conta desse carro já não pode ser aberta.
    assert auth_client.get(f"/finance/vehicles/{veiculo['id']}").status_code == 404


def test_o_caixa_do_mes_nao_muda_quando_o_carro_sai_da_frota(
    auth_client, criar_veiculo, lancar_receita
):
    """A FRONTEIRA do filtro acima, escrita de propósito.

    "A receber" é uma promessa sobre o futuro e some junto com o carro. O caixa do mês é
    extrato: aqueles R$ 800 entraram na conta do dono e apagar o cadastro não desfaz isso.
    Se alguém "consertar" o filtro de um jeito abrangente demais, este teste quebra.
    """
    veiculo = criar_veiculo()
    lancar_receita(veiculo["id"], "800.00")  # recebida hoje

    antes = auth_client.get("/finance/dashboard").json()
    assert Decimal(antes["revenue_received_month"]) == Decimal("800.00")

    assert auth_client.delete(f"/vehicles/{veiculo['id']}").status_code == 204

    depois = auth_client.get("/finance/dashboard").json()
    assert Decimal(depois["revenue_received_month"]) == Decimal("800.00")


# ---------------------------------------------------------------------------
# PAYBACK — "em quanto tempo o carro se pagou".
#
# Estava sem um único teste, e é a única armadilha da lista do CLAUDE.md sem cobertura:
# "payback cobre só a OPERAÇÃO (a venda não entra)". Todos os testes abaixo são de
# REGRESSÃO: o comportamento já estava certo em `finance/queries.py:payback`.
# ---------------------------------------------------------------------------
def test_payback_marca_o_mes_em_que_o_carro_se_pagou(
    criar_veiculo, lancar_receita, resultado, hoje
):
    """Comprado por 1.200, rendeu 500 por mês: no 3º mês o acumulado (1.500) passa dos 1.200."""
    veiculo = criar_veiculo(purchase_price="1200.00")
    for n in (3, 2, 1):
        dia = _dia_de_mes_atras(hoje, n)
        lancar_receita(
            veiculo["id"],
            "500.00",
            competence_date=str(dia),
            due_date=str(dia),
            paid_on=str(dia),
        )

    r = resultado(veiculo["id"])
    assert r["payback_month"] == _dia_de_mes_atras(hoje, 1).strftime("%Y-%m")
    assert r["payback_months_elapsed"] == 3
    assert r["payback_months_remaining"] == 0


def test_payback_projeta_o_que_falta_pela_media_dos_ultimos_meses(
    criar_veiculo, lancar_receita, resultado, hoje
):
    """Contraprova do teste acima: quando ainda não se pagou, sai a PROJEÇÃO, não o mês.

    10.000 de investimento, 2.500 por mês em 2 meses: faltam 5.000, média 2.500 → 2 meses.
    """
    veiculo = criar_veiculo(purchase_price="10000.00")
    for n in (2, 1):
        dia = _dia_de_mes_atras(hoje, n)
        lancar_receita(
            veiculo["id"],
            "2500.00",
            competence_date=str(dia),
            due_date=str(dia),
            paid_on=str(dia),
        )

    r = resultado(veiculo["id"])
    assert r["payback_month"] is None, "ainda não se pagou: não há mês de retorno"
    assert r["payback_months_elapsed"] is None
    assert r["payback_months_remaining"] == 2


def test_a_venda_nao_conta_como_payback(auth_client, criar_veiculo, resultado, hoje):
    """A ARMADILHA do CLAUDE.md: payback é o carro se pagar RODANDO, não na revenda.

    Comprado por 50.000 e vendido por 60.000, sem ter rodado um dia: o LUCRO é 10.000 (a
    venda entra na conta de lucro), e o payback é vazio (a venda não entra nele).

    A asserção é dupla de propósito. Um teste que só checasse `payback_month is None`
    passaria igual se o payback nunca fosse calculado — o `profit` prova que a conta rodou.
    """
    veiculo = criar_veiculo(purchase_price="50000.00")
    venda = auth_client.post(
        f"/vehicles/{veiculo['id']}/sell",
        json={"sale_price": "60000.00", "sale_date": str(hoje)},
    )
    assert venda.status_code == 200, venda.text

    r = resultado(veiculo["id"])
    assert Decimal(r["profit"]) == Decimal("10000.00")
    assert r["payback_month"] is None
    assert r["payback_months_remaining"] is None


def test_carro_vendido_nao_recebe_projecao_de_payback(
    auth_client, criar_veiculo, lancar_receita, resultado, hoje
):
    """Projetar "faltam 49 meses" para um carro que não é mais seu seria mentira.

    O controle positivo aqui é o MESMO carro antes da venda: ele recebia projeção. Sem
    isso, o teste passaria com um payback que nunca calcula nada.
    """
    veiculo = criar_veiculo(purchase_price="50000.00")
    mes_passado = _dia_de_mes_atras(hoje, 1)
    lancar_receita(
        veiculo["id"],
        "1000.00",
        competence_date=str(mes_passado),
        due_date=str(mes_passado),
        paid_on=str(mes_passado),
    )

    antes = resultado(veiculo["id"])
    assert antes["payback_months_remaining"] == 49, "50.000 − 1.000 recebido, a 1.000/mês"

    venda = auth_client.post(
        f"/vehicles/{veiculo['id']}/sell",
        json={"sale_price": "60000.00", "sale_date": str(hoje)},
    )
    assert venda.status_code == 200, venda.text

    depois = resultado(veiculo["id"])
    assert depois["payback_months_remaining"] is None
    assert depois["payback_month"] is None
    # O resultado dele agora é o lucro final realizado: 1.000 − 50.000 + 60.000.
    assert Decimal(depois["profit"]) == Decimal("11000.00")


def test_payback_e_vazio_quando_o_carro_nao_custou_nada(
    criar_veiculo, lancar_receita, resultado, hoje
):
    """Investimento zero: não há o que pagar de volta. Vazio, não zero e não erro 500."""
    veiculo = criar_veiculo(purchase_price="0.00", purchase_date=str(hoje - timedelta(days=60)))
    lancar_receita(veiculo["id"], "1000.00")

    r = resultado(veiculo["id"])
    # CONTROLE POSITIVO: a operação existiu, então o vazio não é "não havia nada a somar".
    assert Decimal(r["total_received"]) == Decimal("1000.00")
    assert Decimal(r["investment"]) == Decimal("0.00")
    assert r["payback_month"] is None
    assert r["payback_months_elapsed"] is None
    assert r["payback_months_remaining"] is None


def test_carro_que_so_da_prejuizo_nao_ganha_prazo_inventado(
    auth_client, criar_veiculo, lancar_despesa, resultado, hoje
):
    """Sem nenhum mês de lucro não há média para projetar. A resposta honesta é vazio.

    (Dividir pela média de meses negativos daria um prazo NEGATIVO — "se pagou mês que
    vem", para um carro que só consome dinheiro.)
    """
    veiculo = criar_veiculo(purchase_price="50000.00")
    mes_passado = _dia_de_mes_atras(hoje, 1)
    lancar_despesa(
        veiculo["id"],
        "900.00",
        competence_date=str(mes_passado),
        paid_on=str(mes_passado),
    )

    # CONTROLE POSITIVO: a série mensal EXISTE e é negativa — o laço do payback rodou.
    meses = auth_client.get("/finance/monthly", params={"vehicle_id": veiculo["id"]}).json()
    assert [m["month"] for m in meses] == [mes_passado.strftime("%Y-%m")]
    assert Decimal(meses[0]["profit"]) == Decimal("-900.00")

    r = resultado(veiculo["id"])
    assert r["payback_month"] is None
    assert r["payback_months_remaining"] is None


def test_serie_mensal(auth_client, criar_veiculo, lancar_receita, lancar_despesa, hoje):
    """O gráfico do mês: caixa que entrou menos caixa que saiu."""
    veiculo = criar_veiculo()
    lancar_receita(veiculo["id"], "800.00")  # recebida hoje
    lancar_despesa(veiculo["id"], "200.00", paid_on=str(hoje), competence_date=str(hoje))

    meses = auth_client.get("/finance/monthly", params={"vehicle_id": veiculo["id"]}).json()
    mes = next(m for m in meses if m["month"] == hoje.strftime("%Y-%m"))

    assert Decimal(mes["revenue"]) == Decimal("800.00")
    assert Decimal(mes["expense"]) == Decimal("200.00")
    assert Decimal(mes["profit"]) == Decimal("600.00")
