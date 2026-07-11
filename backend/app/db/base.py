"""Importa TODOS os models.

O Alembic só enxerga uma tabela se a classe tiver sido importada. Model novo que não
apareça aqui simplesmente não entra na migração — e o bug só aparece em produção.
"""

from app.db.base_class import Base  # noqa: F401
from app.domains.audit.models import AuditLog  # noqa: F401
from app.domains.contracts.models import Contract  # noqa: F401
from app.domains.drivers.models import Driver  # noqa: F401
from app.domains.expenses.models import Expense, ExpenseCategory  # noqa: F401
from app.domains.files.models import Document  # noqa: F401
from app.domains.fines.models import Fine  # noqa: F401
from app.domains.inspections.models import (  # noqa: F401
    ChecklistItem,
    Inspection,
    InspectionItem,
    InspectionPhoto,
)
from app.domains.maintenances.models import Maintenance  # noqa: F401
from app.domains.revenues.models import Revenue, RevenuePayment  # noqa: F401
from app.domains.users.models import User  # noqa: F401
from app.domains.vehicles.models import Vehicle  # noqa: F401

# As sequences que geram os códigos legíveis (CAR000001...). Criadas na migração 0001,
# antes das tabelas — o DEFAULT das colunas `code` depende delas.
CODE_SEQUENCES = [
    "user_code_seq",
    "vehicle_code_seq",
    "driver_code_seq",
    "contract_code_seq",
    "revenue_code_seq",
    "expense_code_seq",
    "maintenance_code_seq",
    "fine_code_seq",
    "inspection_code_seq",
]
