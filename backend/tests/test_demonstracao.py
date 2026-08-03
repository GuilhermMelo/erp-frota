"""A conta de demonstração — credencial pública, e nenhuma escrita.

O teste central aqui NÃO escolhe alguns endpoints para verificar: ele **enumera todas as
rotas registradas no app** e exige 403 em cada uma que escreve. É de propósito.

Uma credencial publicada na internet é atacada por quem tem tempo. Se a proteção fosse
testada por amostragem, o endpoint criado na semana que vem entraria sem cobertura e
ninguém perceberia — que é exatamente como esse tipo de falha acontece.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.main import app

DEMO_EMAIL = "demo@erpfrota.com.br"
DEMO_SENHA = "demonstracao123"

# `POST /auth/login` é a única escrita sem usuário autenticado — tem que ser, senão
# ninguém entra. Ela não passa pelo `get_current_user` e portanto não é bloqueável ali.
FORA = {"/auth/login"}

ESCRITA = {"POST", "PATCH", "PUT", "DELETE"}


def _rotas_de_escrita() -> list[tuple[str, str]]:
    achadas = []
    for rota in app.routes:
        caminho = getattr(rota, "path", "")
        if caminho in FORA or not caminho.startswith("/"):
            continue
        for metodo in getattr(rota, "methods", set()) & ESCRITA:
            achadas.append((metodo, caminho))
    return sorted(achadas)


@pytest.fixture
def demo(db, login):
    """Cria o usuário de demonstração e devolve um cliente logado com ele."""
    from app.core.security import hash_password

    db.execute(
        text(
            "INSERT INTO users (email, full_name, hashed_password, role, is_active) "
            "VALUES (:e, 'Demonstração', :s, 'demonstracao', true)"
        ),
        {"e": DEMO_EMAIL, "s": hash_password(DEMO_SENHA)},
    )
    db.commit()
    return login(DEMO_EMAIL, DEMO_SENHA)


def test_o_papel_existe_no_banco(demo):
    """Se o CHECK da migração 0003 não tivesse rodado, o INSERT do fixture falharia."""
    assert demo is not None


def test_demonstracao_le_normalmente(demo, criar_veiculo, auth_client):
    criar_veiculo(plate="DEM1A23")  # criado pelo admin, não pelo demo

    for rota in ("/vehicles", "/drivers", "/contracts", "/finance/fleet", "/revenues"):
        r = demo.get(rota)
        assert r.status_code == 200, f"{rota} deveria ser legível: {r.text[:200]}"

    assert any(v["plate"] == "DEM1A23" for v in demo.get("/vehicles").json())


@pytest.mark.parametrize("metodo,caminho", _rotas_de_escrita())
def test_nenhuma_rota_de_escrita_aceita_a_demonstracao(demo, metodo, caminho):
    """Toda rota que muda estado responde 403 para a conta de vitrine.

    O 403 vem da dependência, ANTES da validação do corpo — por isso mandar corpo vazio
    não devolve 422. Se um dia devolver, é sinal de que o bloqueio saiu do lugar certo.
    """
    url = caminho.replace("{vehicle_id}", str(uuid4())).replace("{driver_id}", str(uuid4()))
    url = url.replace("{contract_id}", str(uuid4())).replace("{revenue_id}", str(uuid4()))
    url = url.replace("{expense_id}", str(uuid4())).replace("{fine_id}", str(uuid4()))
    url = url.replace("{inspection_id}", str(uuid4())).replace("{maintenance_id}", str(uuid4()))
    url = url.replace("{user_id}", str(uuid4())).replace("{photo_id}", str(uuid4()))
    url = url.replace("{item_id}", str(uuid4())).replace("{key:path}", "x/y.jpg")
    url = url.replace("{payment_id}", str(uuid4()))

    r = demo.request(metodo, url, json={})
    assert r.status_code == 403, (
        f"{metodo} {caminho} devolveu {r.status_code} para a conta de demonstração "
        f"(esperado 403). Corpo: {r.text[:300]}"
    )


def test_admin_continua_escrevendo(auth_client, criar_veiculo):
    """A trava não pode ter pegado quem tem direito de escrever."""
    v = criar_veiculo(plate="ADM1A23")
    r = auth_client.patch(f"/vehicles/{v['id']}", json={"color": "Verde"})
    assert r.status_code == 200, r.text


def test_a_mensagem_explica_sem_parecer_erro(demo):
    r = demo.post("/vehicles", json={})
    assert r.status_code == 403
    assert "demonstração" in r.json()["error"]["message"].lower()
