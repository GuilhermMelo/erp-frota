"""Frota fictícia para demonstração e para os screenshots do README.

NADA aqui é real: placas, CPFs, CNHs e nomes são inventados (regra 6 do ARQUITETURA.md).

Por que existe: demonstrar o sistema para alguém usando o banco de trabalho exporia CPF e
CNH de motoristas de verdade (LGPD). Este script monta uma cópia fictícia num banco à parte.

Uso:
    createdb -h 127.0.0.1 -p 5434 -U frota frota_demo
    DATABASE_URL=postgresql+psycopg://frota:frota@localhost:5434/frota_demo \
      ADMIN_PASSWORD=demo1234 uvicorn app.main:app --port 8011
    python scripts/seed_demo.py --api http://127.0.0.1:8011 --senha demo1234

A frota cobre de propósito os quatro estados que o sistema precisa saber tratar:
    CAR000001  rodando, perto do ponto de equilíbrio, com cobranças vencidas
    CAR000002  rodando, ainda em formação
    CAR000003  vendido — ciclo fechado, resultado travado
    CAR000004  comprado na semana passada — o caso da divisão por zero
"""

import argparse
from datetime import date, timedelta

import httpx

# ---------------------------------------------------------------------------
# Guard. Este script CRIA DADOS FALSOS: rodar contra o banco de trabalho
# misturaria frota inventada com a real, e separar depois seria manual.
# Mesma ideia do guard da suíte de testes (tests/conftest.py).
# ---------------------------------------------------------------------------
BANCOS_PROIBIDOS = ("/frota", "/frota_test")

parser = argparse.ArgumentParser(description="Popula um banco de DEMONSTRAÇÃO.")
parser.add_argument("--api", default="http://127.0.0.1:8011", help="URL da API de demonstração")
parser.add_argument("--senha", default="demo1234", help="senha do admin nessa instância")
args = parser.parse_args()

c = httpx.Client(base_url=args.api, timeout=60)

# A API não expõe a DATABASE_URL (e não deve). O guard possível é confirmar que a
# instância alvo NÃO é a de trabalho: a porta 8010 é a do dia a dia.
if args.api.rstrip("/").endswith(":8010"):
    raise SystemExit(
        "RECUSADO: 8010 é a porta da instalação de trabalho.\n"
        "Suba uma instância separada apontando para o banco de demonstração."
    )

HOJE = date.today()


def ok(r, o_que):
    if r.status_code >= 300:
        raise SystemExit(f"FALHOU {o_que}: {r.status_code} {r.text[:400]}")
    return r.json() if r.content else None


r = c.post("/auth/login", json={"email": "admin@erpfrota.com.br", "password": args.senha})
c.headers["Authorization"] = f"Bearer {ok(r, 'login')['access_token']}"

if ok(c.get("/vehicles"), "conferir banco vazio"):
    raise SystemExit("RECUSADO: já existem veículos nesta instância. Use um banco limpo.")

print("login ok, banco vazio confirmado")

# ------------------------------------------------------------------ usuário de demonstração
# Papel `demonstracao`: SOMENTE LEITURA. A credencial é publicada de propósito, então
# `operador` não serviria — ele escreve. O bloqueio é no `get_current_user`, por onde
# passa toda requisição autenticada, e um teste enumera as rotas para garantir que
# nenhuma escrita escapa (tests/test_demonstracao.py).
ok(
    c.post(
        "/users",
        json={
            "email": "demo@erpfrota.com.br",
            "full_name": "Usuário Demonstração",
            "role": "demonstracao",
            "password": "demo1234",
        },
    ),
    "usuário demo",
)
print("usuário demo@erpfrota.com.br criado (somente leitura)")

# ---------------------------------------------------------------- motoristas
MOTORISTAS = [
    ("Anderson Vieira Lima", "31877420165", "04128877310", "11987654321"),
    ("Rafael Souza Prado", "42906311478", "05233118140", "11976543210"),
    ("Marcelo Tavares Pinho", "50713628290", "06344992271", "11965432109"),
]
motoristas = []
for nome, cpf, cnh, fone in MOTORISTAS:
    motoristas.append(
        ok(
            c.post(
                "/drivers",
                json={
                    "full_name": nome,
                    "cpf": cpf,
                    "cnh_number": cnh,
                    "cnh_category": "B",
                    "phone": fone,
                    "cnh_expires_on": str(HOJE + timedelta(days=95)),
                },
            ),
            f"motorista {nome}",
        )
    )
print(f"{len(motoristas)} motoristas")

# ------------------------------------------------------------------ veículos
# As datas são relativas a HOJE: o script continua contando a mesma história
# daqui a um ano, sem virar uma frota comprada "no passado remoto".
VEICULOS = [
    ("RJA1B23", "Fiat", "Cronos", 2023, 2024, "68500.00", 876, 21000, 118400),
    ("RJB2C34", "Hyundai", "HB20", 2022, 2023, "61900.00", 427, 34000, 88200),
    ("RJC3D45", "Chevrolet", "Onix", 2021, 2021, "54000.00", 931, 48000, 112500),
    ("RJD4E56", "Renault", "Kwid", 2024, 2025, "72300.00", 6, 800, 950),
]
veiculos = []
for placa, marca, modelo, ano_f, ano_m, preco, dias_atras, km0, km1 in VEICULOS:
    veiculos.append(
        ok(
            c.post(
                "/vehicles",
                json={
                    "plate": placa,
                    "brand": marca,
                    "model": modelo,
                    "manufacture_year": ano_f,
                    "model_year": ano_m,
                    "color": "Prata",
                    "fuel_type": "flex",
                    "purchase_date": str(HOJE - timedelta(days=dias_atras)),
                    "purchase_price": preco,
                    "purchase_odometer": km0,
                    "current_odometer": km1,
                },
            ),
            f"veiculo {placa}",
        )
    )
print(f"{len(veiculos)} veiculos")

# ----------------------------------------------------------------- contratos
CONTRATOS = [(0, 0, 868, "620.00", "1500.00"), (1, 1, 420, "580.00", "1200.00"), (2, 2, 924, "540.00", "1000.00")]
contratos = []
for iv, im, dias_atras, semanal, caucao in CONTRATOS:
    contratos.append(
        ok(
            c.post(
                "/contracts",
                json={
                    "vehicle_id": veiculos[iv]["id"],
                    "driver_id": motoristas[im]["id"],
                    "start_date": str(HOJE - timedelta(days=dias_atras)),
                    "weekly_amount": semanal,
                    "billing_weekday": 0,
                    "deposit_amount": caucao,
                },
            ),
            "contrato",
        )
    )
c.post("/contracts/generate-charges", json={})
print(f"{len(contratos)} contratos")

# Pagar quase tudo. O que sobra é a inadimplência que a tela de Cobranças mede:
# restantes 1-2 = semana corrente (no prazo); 5, 7 e 10 = semanas anteriores VENCIDAS;
# 3 = pago pela metade, porque parcial é o caso real, não o feliz.
receitas = sorted(ok(c.get("/revenues", params={"limit": 500}), "receitas"), key=lambda x: x["due_date"])
EM_ABERTO = {1, 2, 5, 7, 10}
for i, rc in enumerate(receitas):
    restantes = len(receitas) - i
    if restantes in EM_ABERTO:
        continue
    valor = f"{float(rc['amount']) / 2:.2f}" if restantes == 3 else rc["amount"]
    ok(
        c.post(
            f"/revenues/{rc['id']}/payments",
            json={"amount": valor, "paid_on": rc["due_date"], "method": "pix"},
        ),
        "pagamento",
    )
print(f"{len(receitas)} cobrancas: {len(EM_ABERTO)} em aberto (3 vencidas) e 1 parcial")

# ------------------------------------------------------------------ despesas
cats = {x["code"]: x["id"] for x in ok(c.get("/expense-categories"), "categorias")}
DESPESAS = [
    (0, "seguro", "Seguro anual", "3180.00", 115),
    (0, "ipva", "IPVA do ano", "1420.00", 164),
    (0, "pneus", "Quatro pneus 195/65 R15", "2260.00", 52),
    (1, "seguro", "Seguro anual", "2940.00", 80),
    (1, "licenciamento", "Licenciamento", "180.00", 148),
    (2, "protecao", "Protecao veicular (12 meses)", "2400.00", 489),
    (3, "licenciamento", "Emplacamento", "890.00", 5),
]
for iv, cat, desc, valor, dias in DESPESAS:
    quando = str(HOJE - timedelta(days=dias))
    ok(
        c.post(
            "/expenses",
            json={
                "vehicle_id": veiculos[iv]["id"],
                "category_id": cats[cat],
                "description": desc,
                "amount": valor,
                "competence_date": quando,
                "paid_on": quando,
                "status": "paid",
            },
        ),
        f"despesa {desc}",
    )
print(f"{len(DESPESAS)} despesas")

# --------------------------------------------------------------- manutenções
MANUTENCOES = [
    (0, "Troca de oleo e filtros", "Oficina do Ze", "480.00", 62, 74100),
    (0, "Pastilhas de freio dianteiras", "Oficina do Ze", "620.00", 20, 78200),
    (1, "Revisao de 80 mil km", "Concessionaria", "1340.00", 39, 80400),
    (2, "Embreagem", "Auto Center Sul", "2180.00", 197, 104800),
]
for iv, tipo, fornecedor, valor, dias, km in MANUTENCOES:
    ok(
        c.post(
            "/maintenances",
            json={
                "vehicle_id": veiculos[iv]["id"],
                "kind": tipo,
                "supplier_name": fornecedor,
                "amount": valor,
                "performed_on": str(HOJE - timedelta(days=dias)),
                "odometer": km,
            },
        ),
        f"manutencao {tipo}",
    )
print(f"{len(MANUTENCOES)} manutencoes (cada uma gerou a despesa do carro)")

# -------------------------------------------------------------------- multas
m1 = ok(
    c.post(
        "/fines",
        json={
            "vehicle_id": veiculos[0]["id"],
            "driver_id": motoristas[0]["id"],
            "infraction_date": str(HOJE - timedelta(days=55)),
            "ait_number": "AA00123456",
            "description": "Velocidade acima da permitida em ate 20%",
            "location": "Av. das Nacoes Unidas, km 12",
            "amount": "130.16",
            "due_date": str(HOJE - timedelta(days=25)),
            "points": 4,
        },
    ),
    "multa 1",
)
ok(c.post(f"/fines/{m1['id']}/pay", json={"paid_on": str(HOJE - timedelta(days=29))}), "pagar multa")
ok(
    c.post(
        "/fines",
        json={
            "vehicle_id": veiculos[1]["id"],
            "driver_id": motoristas[1]["id"],
            "infraction_date": str(HOJE - timedelta(days=13)),
            "ait_number": "AA00987654",
            "description": "Estacionar em local proibido",
            "location": "R. Coronel Xavier, 400",
            "amount": "88.38",
            "due_date": str(HOJE + timedelta(days=17)),
            "points": 3,
        },
    ),
    "multa 2",
)
print("2 multas (uma paga -> virou despesa do carro)")

# ------------------------------------------------------------------ vistoria
ok(
    c.post(
        "/inspections",
        json={
            "vehicle_id": veiculos[0]["id"],
            "driver_id": motoristas[0]["id"],
            "contract_id": contratos[0]["id"],
            "kind": "entrega",
            "odometer": 21000,
            "fuel_level": 75,
            "notes": "Risco leve no para-choque traseiro, registrado na entrega.",
        },
    ),
    "vistoria",
)
print("1 vistoria")

# ------------------------------------------- encerrar contrato e vender carro
ok(
    c.post(
        f"/contracts/{contratos[2]['id']}/finish",
        json={
            "end_date": str(HOJE - timedelta(days=49)),
            "deposit_returned_amount": "1000.00",
        },
    ),
    "encerrar contrato",
)
ok(
    c.post(
        f"/vehicles/{veiculos[2]['id']}/sell",
        json={"sale_price": "59900.00", "sale_date": str(HOJE - timedelta(days=44))},
    ),
    "vender veiculo",
)
print("CAR000003 vendido — ciclo fechado")

print("\nPRONTO. Entre com demo@erpfrota.com.br / demo1234")
