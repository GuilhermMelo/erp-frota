"""Autenticação, envelope de erro e o que NUNCA pode vazar numa resposta."""

import pytest

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

# Endpoints que não podem responder nada a quem não está logado.
PROTEGIDOS = [
    ("GET", "/vehicles"),
    ("GET", "/drivers"),
    ("GET", "/contracts"),
    ("GET", "/revenues"),
    ("GET", "/revenues/receivables"),
    ("GET", "/expenses"),
    ("GET", "/expense-categories"),
    ("GET", "/fines"),
    ("GET", "/finance/fleet"),
    ("GET", "/finance/dashboard"),
    ("GET", "/audit"),
    ("GET", "/users"),
    ("GET", "/auth/me"),
]


def test_login_do_admin_funciona(client):
    r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text

    corpo = r.json()
    assert corpo["token_type"] == "bearer"
    assert corpo["access_token"]
    assert corpo["user"]["email"] == ADMIN_EMAIL
    assert corpo["user"]["role"] == "admin"


def test_senha_errada_da_401_no_envelope_padrao(client):
    r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": "senha-errada"})
    assert r.status_code == 401

    corpo = r.json()
    assert set(corpo) == {"error"}, "toda resposta de erro tem a MESMA forma"
    assert corpo["error"]["code"] == "nao_autenticado"
    assert corpo["error"]["message"] == "E-mail ou senha inválidos."
    assert "access_token" not in corpo


def test_usuario_inexistente_da_a_mesma_resposta(client):
    """A mensagem não pode revelar quais e-mails estão cadastrados."""
    r = client.post("/auth/login", json={"email": "ninguem@erpfrota.com.br", "password": "x"})
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "E-mail ou senha inválidos."


@pytest.mark.parametrize("method,path", PROTEGIDOS)
def test_endpoint_sem_token_da_401(client, method, path):
    r = client.request(method, path)
    assert r.status_code == 401, f"{method} {path} respondeu {r.status_code}"
    assert r.json()["error"]["code"] == "nao_autenticado"


def test_token_invalido_da_401(client):
    r = client.get("/vehicles", headers={"Authorization": "Bearer nao-e-um-jwt"})
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Token inválido."


def test_usuario_inativo_nao_entra(auth_client, client, db):
    """Desativar o usuário derruba o acesso dele — inclusive com um token já emitido."""
    novo = auth_client.post(
        "/users",
        json={
            "email": "operador@erpfrota.com.br",
            "full_name": "Operador",
            "role": "operador",
            "password": "operador123",
        },
    ).json()

    logado = client.post(
        "/auth/login", json={"email": "operador@erpfrota.com.br", "password": "operador123"}
    )
    assert logado.status_code == 200
    token = logado.json()["access_token"]

    r = auth_client.patch(f"/users/{novo['id']}", json={"is_active": False})
    assert r.status_code == 200

    # Token continua válido criptograficamente — mas o usuário não é mais.
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert "inativo" in r.json()["error"]["message"].lower()

    # E o login também não passa mais.
    r = client.post(
        "/auth/login", json={"email": "operador@erpfrota.com.br", "password": "operador123"}
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# O hash da senha NUNCA sai numa resposta.
# ---------------------------------------------------------------------------
def test_hashed_password_nunca_aparece_em_nenhuma_resposta(auth_client, client):
    r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert "hashed_password" not in r.text
    assert "hashed_password" not in r.json()["user"]

    eu = auth_client.get("/auth/me")
    assert eu.status_code == 200
    assert "hashed_password" not in eu.json()
    assert "hashed_password" not in eu.text
    assert "password" not in eu.json()

    criado = auth_client.post(
        "/users",
        json={
            "email": "operador@erpfrota.com.br",
            "full_name": "Operador",
            "role": "operador",
            "password": "operador123",
        },
    )
    assert criado.status_code == 201
    assert "hashed_password" not in criado.text
    assert "$2b$" not in criado.text, "nem o hash bcrypt cru"

    lista = auth_client.get("/users")
    assert lista.status_code == 200
    assert "hashed_password" not in lista.text
    assert "$2b$" not in lista.text
    for usuario in lista.json():
        assert set(usuario) == {
            "id",
            "code",
            "email",
            "full_name",
            "role",
            "is_active",
            "last_login_at",
        }


def test_auditoria_mascara_a_senha(auth_client):
    """O log registra que a senha mudou, nunca o hash dela."""
    auth_client.post(
        "/users",
        json={
            "email": "operador@erpfrota.com.br",
            "full_name": "Operador",
            "role": "operador",
            "password": "operador123",
        },
    )
    logs = auth_client.get("/audit", params={"entity_type": "users"}).json()
    criacao = [x for x in logs if x["action"] == "create"]
    assert criacao, "a criação do usuário foi registrada"
    assert criacao[0]["changes"]["hashed_password"] == {"de": "***", "para": "***"}
    assert "$2b$" not in auth_client.get("/audit").text


# ---------------------------------------------------------------------------
# Papéis: operador não é administrador.
# ---------------------------------------------------------------------------
@pytest.fixture
def operador(auth_client, login):
    r = auth_client.post(
        "/users",
        json={
            "email": "operador@erpfrota.com.br",
            "full_name": "Operador",
            "role": "operador",
            "password": "operador123",
        },
    )
    assert r.status_code == 201, r.text
    return login("operador@erpfrota.com.br", "operador123")


def test_operador_nao_acessa_endpoint_de_admin(operador, criar_veiculo):
    """403 (sem permissão), não 401 (sem login): ele ESTÁ logado."""
    veiculo = criar_veiculo()

    proibidos = [
        operador.get("/users"),
        operador.get("/audit"),
        operador.post("/users", json={
            "email": "outro@erpfrota.com.br",
            "full_name": "Outro",
            "password": "outro1234",
        }),
        operador.delete(f"/vehicles/{veiculo['id']}"),
        operador.post(
            f"/vehicles/{veiculo['id']}/sell",
            json={"sale_price": "1000.00", "sale_date": "2026-01-01"},
        ),
    ]
    for r in proibidos:
        assert r.status_code == 403, f"{r.request.method} {r.request.url}: {r.status_code}"
        assert r.json()["error"]["code"] == "sem_permissao"


# ---------------------------------------------------------------------------
# Tem que sobrar um administrador. Não há caminho de volta.
# ---------------------------------------------------------------------------
def test_o_ultimo_admin_nao_consegue_se_rebaixar(auth_client):
    """BUG REAL, corrigido nesta sessão: o sistema podia ficar sem administrador.

    `PATCH /users/{id}` aceitava `role` sem nenhuma guarda. Um admin que se pusesse como
    operador perdia, na requisição seguinte, `/users`, `/audit`, todo `DELETE` e a venda de
    veículo — e não havia recuperação: `seed()` só cria o admin com a tabela VAZIA, e este
    sistema não tem "esqueci minha senha". O conserto seria SQL na unha, no Postgres.

    O `assert` que importa não é o 409: é continuar administrador DE VERDADE depois.
    """
    eu = auth_client.get("/auth/me").json()

    r = auth_client.patch(f"/users/{eu['id']}", json={"role": "operador"})
    assert r.status_code == 409, r.text

    assert auth_client.get("/auth/me").json()["role"] == "admin"
    assert auth_client.get("/users").status_code == 200, "continua administrando o sistema"


def test_o_ultimo_admin_nao_consegue_se_desativar(auth_client):
    """A outra porta para o mesmo estado: `is_active: false` em si mesmo.

    Pior que o rebaixamento — `get_current_user` recusa usuário inativo, então nem entrar
    no sistema seria possível.
    """
    eu = auth_client.get("/auth/me").json()

    r = auth_client.patch(f"/users/{eu['id']}", json={"is_active": False})
    assert r.status_code == 409, r.text

    assert auth_client.get("/auth/me").status_code == 200, "o token continua valendo"
    assert auth_client.get("/users").json()[0]["is_active"] is True


def test_com_outro_admin_no_sistema_o_rebaixamento_passa(auth_client, login):
    """CONTRAPROVA, e ela é obrigatória: a trava é "sobrar um admin ATIVO", não
    "administrador nunca muda de papel". Sem este teste, um `PATCH` que recusasse todo
    mundo o tempo todo passaria nos dois testes acima.
    """
    eu = auth_client.get("/auth/me").json()
    r = auth_client.post(
        "/users",
        json={
            "email": "segundo.admin@erpfrota.com.br",
            "full_name": "Segundo Admin",
            "role": "admin",
            "password": "segundo123",
        },
    )
    assert r.status_code == 201, r.text
    outro = login("segundo.admin@erpfrota.com.br", "segundo123")

    assert auth_client.patch(f"/users/{eu['id']}", json={"role": "operador"}).status_code == 200

    # O rebaixamento valeu na requisição seguinte, e o sistema continua administrável.
    assert auth_client.get("/users").status_code == 403
    assert outro.get("/users").status_code == 200


def test_o_penultimo_admin_ativo_nao_pode_desativar_o_ultimo(auth_client, login):
    """A trava conta admins ATIVOS, não admins cadastrados.

    Dois administradores, um deles já desativado: rebaixar o que sobrou tem que ser
    recusado do mesmo jeito — senão o sistema fica com um admin no banco e ninguém
    conseguindo entrar.
    """
    eu = auth_client.get("/auth/me").json()
    r = auth_client.post(
        "/users",
        json={
            "email": "admin.ferias@erpfrota.com.br",
            "full_name": "Admin de Férias",
            "role": "admin",
            "password": "ferias1234",
        },
    )
    assert r.status_code == 201, r.text
    dormindo = r.json()

    # Desativar o segundo é permitido: ainda sobra este.
    assert auth_client.patch(f"/users/{dormindo['id']}", json={"is_active": False}).status_code == 200

    # Agora o único ATIVO sou eu — e o rebaixamento volta a ser recusado.
    assert auth_client.patch(f"/users/{eu['id']}", json={"role": "operador"}).status_code == 409
    assert auth_client.get("/users").status_code == 200


def test_operador_faz_o_trabalho_do_dia_a_dia(operador, criar_veiculo, hoje):
    """O 403 acima não pode ter travado a operação: operador lança receita e despesa."""
    veiculo = criar_veiculo()

    assert operador.get("/vehicles").status_code == 200
    assert operador.get("/finance/fleet").status_code == 200

    r = operador.post(
        "/revenues",
        json={
            "vehicle_id": veiculo["id"],
            "category": "aluguel",
            "amount": "800.00",
            "competence_date": str(hoje),
        },
    )
    assert r.status_code == 201, r.text
