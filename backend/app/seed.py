"""Dados iniciais. Idempotente: pode rodar a cada boot sem duplicar nada."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.domains.expenses.models import ExpenseCategory
from app.domains.inspections.models import ChecklistItem
from app.domains.users.models import User, UserRole

logger = logging.getLogger(__name__)

# (code, nome, is_capex)
# is_capex = investimento NO carro (aumenta o valor do bem), não custo de operação.
# Sem essa separação, uma blindagem de R$ 15 mil viraria "custo do mês" e o custo por km
# ficaria absurdo.
EXPENSE_CATEGORIES = [
    ("manutencao", "Manutenção", False),
    ("protecao", "Proteção veicular", False),
    ("seguro", "Seguro", False),
    ("ipva", "IPVA", False),
    ("licenciamento", "Licenciamento", False),
    ("multas", "Multas", False),
    ("pneus", "Pneus", False),
    ("pecas", "Peças", False),
    ("combustivel", "Combustível", False),
    ("lavagem", "Lavagem", False),
    ("documentacao", "Documentação", False),
    ("rastreador", "Rastreador", False),
    ("melhorias", "Melhorias e acessórios (investimento)", True),
    ("outros", "Outros", False),
]

# (key, label, grupo)
CHECKLIST_ITEMS = [
    ("lataria", "Lataria", "exterior"),
    ("para_brisa", "Para-brisa", "exterior"),
    ("vidros", "Vidros", "exterior"),
    ("farois", "Faróis", "exterior"),
    ("lanternas", "Lanternas", "exterior"),
    ("retrovisores", "Retrovisores", "exterior"),
    ("parachoque_dianteiro", "Para-choque dianteiro", "exterior"),
    ("parachoque_traseiro", "Para-choque traseiro", "exterior"),
    ("pneus", "Pneus", "exterior"),
    ("rodas", "Rodas / calotas", "exterior"),
    ("estepe", "Estepe", "exterior"),
    ("bancos", "Bancos", "interior"),
    ("cintos", "Cintos de segurança", "interior"),
    ("painel", "Painel", "interior"),
    ("multimidia", "Rádio / multimídia", "interior"),
    ("ar_condicionado", "Ar-condicionado", "interior"),
    ("tapetes", "Tapetes", "interior"),
    ("forro_teto", "Forro do teto", "interior"),
    ("motor", "Motor", "mecanica"),
    ("freios", "Freios", "mecanica"),
    ("suspensao", "Suspensão", "mecanica"),
    ("embreagem", "Embreagem", "mecanica"),
    ("bateria", "Bateria", "mecanica"),
    ("nivel_oleo", "Nível de óleo", "mecanica"),
    ("nivel_agua", "Nível de água", "mecanica"),
    ("crlv", "CRLV", "documentos"),
    ("manual", "Manual", "documentos"),
    ("chave_reserva", "Chave reserva", "documentos"),
    ("triangulo", "Triângulo", "documentos"),
    ("macaco", "Macaco", "documentos"),
    ("chave_roda", "Chave de roda", "documentos"),
    ("extintor", "Extintor", "documentos"),
]


def seed(db: Session) -> None:
    # Upsert por chave estável — um item novo na lista entra numa base já populada.
    for order, (code, name, is_capex) in enumerate(EXPENSE_CATEGORIES):
        cat = db.scalar(select(ExpenseCategory).where(ExpenseCategory.code == code))
        if cat is None:
            db.add(ExpenseCategory(code=code, name=name, is_capex=is_capex, sort_order=order))

    for order, (key, label, group) in enumerate(CHECKLIST_ITEMS):
        item = db.scalar(select(ChecklistItem).where(ChecklistItem.key == key))
        if item is None:
            db.add(ChecklistItem(key=key, label=label, group_name=group, sort_order=order))

    if db.scalar(select(User).limit(1)) is None:
        if not settings.is_dev and settings.ADMIN_PASSWORD == "admin123":
            logger.warning("Nenhum usuário e ADMIN_PASSWORD é o default. Admin NÃO criado.")
        else:
            db.add(
                User(
                    email=settings.ADMIN_EMAIL.strip().lower(),
                    full_name=settings.ADMIN_NAME,
                    hashed_password=hash_password(settings.ADMIN_PASSWORD),
                    role=UserRole.admin,
                )
            )
            logger.info("Admin criado: %s", settings.ADMIN_EMAIL)

    db.commit()
