"""Correção de cadastro de veículo (PATCH /vehicles/{id}).

O endpoint existia desde o começo, mas sem consumo no frontend e sem teste — o que
significa que o número mais importante do sistema (`purchase_price`) não tinha como ser
corrigido nem garantia de que a correção funcionava.

O que estes testes protegem: corrigir a compra tem que REESCREVER o lucro do carro. Se o
PATCH gravasse sem o resultado acompanhar, o operador corrigiria o dígito, veria o valor
novo na tela de cadastro e continuaria com o lucro errado — pior que não ter edição.
"""

from decimal import Decimal


def test_corrigir_dados_de_identificacao(auth_client, criar_veiculo):
    veiculo = criar_veiculo(plate="ABC1D23", brand="Fiat", model="Cronos")

    r = auth_client.patch(
        f"/vehicles/{veiculo['id']}",
        json={"plate": "XYZ9W88", "brand": "Hyundai", "model": "HB20", "color": "Preto"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["plate"] == "XYZ9W88"
    assert r.json()["brand"] == "Hyundai"
    assert r.json()["color"] == "Preto"
    # O código é imutável: é a identidade do carro nos lançamentos já feitos.
    assert r.json()["code"] == veiculo["code"]


def test_corrigir_valor_de_compra_reescreve_o_lucro(auth_client, criar_veiculo, lucro):
    """O dígito errado na migração da planilha — o caso que motivou esta tela."""
    veiculo = criar_veiculo(purchase_price="50000.00")
    assert lucro(veiculo["id"]) == Decimal("-50000.00")

    r = auth_client.patch(f"/vehicles/{veiculo['id']}", json={"purchase_price": "68500.00"})
    assert r.status_code == 200, r.text

    # O lucro TEM que acompanhar. Sem isto, corrigir a tela seria só cosmético.
    assert lucro(veiculo["id"]) == Decimal("-68500.00")


def test_corrigir_odometro_recalcula_o_custo_por_km(auth_client, criar_veiculo, resultado):
    veiculo = criar_veiculo(purchase_odometer=20000, current_odometer=20000)
    # Carro que não rodou: dividir por zero devolve NULL, não 500 e não zero.
    assert resultado(veiculo["id"])["cost_per_km"] is None

    r = auth_client.patch(f"/vehicles/{veiculo['id']}", json={"current_odometer": 45000})
    assert r.status_code == 200, r.text
    assert resultado(veiculo["id"])["km_driven"] == 25000


def test_odometro_atual_menor_que_o_de_compra_e_recusado(auth_client, criar_veiculo):
    """Odômetro só anda para frente. Ao contrário, `km_driven` fica negativo e o custo
    por km some da tela sem o operador entender por quê."""
    veiculo = criar_veiculo(purchase_odometer=20000, current_odometer=45000)

    r = auth_client.patch(f"/vehicles/{veiculo['id']}", json={"current_odometer": 100})
    assert r.status_code in (400, 409, 422), r.text


def test_placa_duplicada_e_recusada(auth_client, criar_veiculo):
    criar_veiculo(plate="AAA1A11")
    outro = criar_veiculo(plate="BBB2B22")

    r = auth_client.patch(f"/vehicles/{outro['id']}", json={"plate": "AAA1A11"})
    assert r.status_code == 409, r.text


def test_veiculo_inexistente_da_404(auth_client):
    r = auth_client.patch(
        "/vehicles/00000000-0000-0000-0000-000000000000", json={"color": "Azul"}
    )
    assert r.status_code == 404, r.text


def test_edicao_de_veiculo_entra_no_log_de_auditoria(auth_client, criar_veiculo):
    """Corrigir o valor de compra muda o resultado histórico do carro. Se não ficasse
    registrado quem mudou e de quanto para quanto, o número perderia rastro."""
    veiculo = criar_veiculo(purchase_price="50000.00")
    auth_client.patch(f"/vehicles/{veiculo['id']}", json={"purchase_price": "68500.00"})

    # `entity_type` é o nome da TABELA (vehicles), não o do model — ver audit/listeners.py.
    logs = auth_client.get("/audit", params={"entity_type": "vehicles"}).json()
    edicoes = [x for x in logs if x["action"] == "update"]
    assert edicoes, "a edição do veículo não gerou log de auditoria"
    assert edicoes[0]["actor_email"] == "admin@erpfrota.com.br"
    assert "purchase_price" in (edicoes[0]["changes"] or {})
