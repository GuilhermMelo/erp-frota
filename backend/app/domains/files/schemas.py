from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field

from app.domains.files.models import DocumentKind


class EntityType(str, Enum):
    """A quem o anexo pertence. Enum fechado: o ponteiro é polimórfico e sem FK, então a
    lista de destinos válidos é a única trava que existe."""

    contract = "contract"
    fine = "fine"
    maintenance = "maintenance"
    vehicle = "vehicle"
    driver = "driver"
    # Comprovante do recebimento (print do PIX, recibo) e da despesa (cupom, boleto pago).
    # Fica na RECEITA/DESPESA, que já têm código (REC000001 / DES000001) — a chave do arquivo
    # no disco precisa de um: `revenues/REC000001/pix.jpg`. O pagamento em si
    # (revenue_payments) não tem código legível.
    revenue = "revenue"
    expense = "expense"


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: str
    entity_id: UUID
    kind: DocumentKind
    storage_key: str
    original_filename: str | None
    mime_type: str
    size_bytes: int
    uploaded_by_user_id: UUID | None
    created_at: datetime

    @computed_field
    @property
    def download_url(self) -> str:
        """O único caminho para o arquivo. Não existe URL pública para `storage/`."""
        return f"/files/{self.id}/download"
