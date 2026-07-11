from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.domains.inspections.models import (
    InspectionKind,
    ItemCondition,
    PhotoCategory,
)


class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    label: str
    group_name: str
    sort_order: int


class VehicleBrief(BaseModel):
    """O suficiente para a lista de vistorias não precisar de um segundo request."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    plate: str
    brand: str
    model: str


class DriverBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    full_name: str


class InspectionItemIn(BaseModel):
    checklist_item_id: int
    condition: ItemCondition = ItemCondition.ok
    notes: str | None = Field(default=None, max_length=200)


class InspectionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    checklist_item_id: int
    condition: ItemCondition
    notes: str | None
    checklist_item: ChecklistItemOut


class InspectionPhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inspection_id: UUID
    category: PhotoCategory
    caption: str | None
    original_filename: str | None
    mime_type: str
    size_bytes: int
    sort_order: int
    created_at: datetime

    @computed_field
    @property
    def download_url(self) -> str:
        return f"/inspections/photos/{self.id}/download"


class InspectionCreate(BaseModel):
    vehicle_id: UUID
    driver_id: UUID | None = None
    contract_id: UUID | None = None
    kind: InspectionKind
    odometer: int = Field(ge=0)
    fuel_level: int = Field(default=100, ge=0, le=100)
    notes: str | None = None
    # Vazio = a vistoria nasce com o checklist completo, tudo em `ok`, pronto para marcar.
    items: list[InspectionItemIn] = Field(default_factory=list)


class InspectionUpdate(BaseModel):
    """`vehicle_id` não está aqui de propósito: trocar o carro de uma vistoria já feita
    reescreveria a história do veículo. Vistoria errada se apaga, não se remaneja."""

    driver_id: UUID | None = None
    contract_id: UUID | None = None
    kind: InspectionKind | None = None
    odometer: int | None = Field(default=None, ge=0)
    fuel_level: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = None
    items: list[InspectionItemIn] | None = None


class InspectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    vehicle_id: UUID
    driver_id: UUID | None
    contract_id: UUID | None
    user_id: UUID | None
    kind: InspectionKind
    inspected_at: datetime
    odometer: int
    fuel_level: int
    notes: str | None
    vehicle: VehicleBrief
    driver: DriverBrief | None
    # Vem da propriedade `Inspection.photos_count` (models.py). A relação `photos` já é
    # lazy="selectin", então contar não custa query nenhuma — e evita a listagem ter que
    # buscar o detalhe de cada linha só para mostrar "12 fotos".
    photos_count: int


class InspectionDetailOut(InspectionOut):
    items: list[InspectionItemOut]
    photos: list[InspectionPhotoOut]

    @field_validator("items")
    @classmethod
    def _in_checklist_order(cls, items: list[InspectionItemOut]) -> list[InspectionItemOut]:
        # A tela renderiza seções (exterior, interior, mecânica, documentos) nesta ordem.
        return sorted(items, key=lambda i: (i.checklist_item.group_name, i.checklist_item.sort_order))
