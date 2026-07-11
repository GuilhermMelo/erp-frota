from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from sqlalchemy import select

from app.domains.auth.deps import CurrentUser, Db
from app.domains.files import service as files_service
from app.domains.inspections import service
from app.domains.inspections.models import Inspection, InspectionKind, PhotoCategory
from app.domains.inspections.schemas import (
    ChecklistItemOut,
    InspectionCreate,
    InspectionDetailOut,
    InspectionOut,
    InspectionPhotoOut,
    InspectionUpdate,
)

# Sem prefixo: o catálogo (/checklist-items) e as vistorias (/inspections) são o mesmo
# domínio, mas moram em raízes diferentes da API.
router = APIRouter(tags=["vistorias"])


@router.get("/checklist-items", response_model=list[ChecklistItemOut])
def list_checklist_items(db: Db, _: CurrentUser):
    """Catálogo do checklist, na ordem em que a tela desenha as seções.

    Item novo ("suporte de celular") é uma linha no banco, não um deploy.
    """
    return service.active_checklist_items(db)


@router.post("/inspections", response_model=InspectionDetailOut, status_code=status.HTTP_201_CREATED)
def create_inspection(data: InspectionCreate, db: Db, user: CurrentUser):
    return service.create_inspection(db, data, user)


@router.get("/inspections", response_model=list[InspectionOut])
def list_inspections(
    db: Db,
    _: CurrentUser,
    vehicle_id: UUID | None = None,
    driver_id: UUID | None = None,
    kind: InspectionKind | None = None,
):
    stmt = select(Inspection).order_by(Inspection.inspected_at.desc())
    if vehicle_id:
        stmt = stmt.where(Inspection.vehicle_id == vehicle_id)
    if driver_id:
        stmt = stmt.where(Inspection.driver_id == driver_id)
    if kind:
        stmt = stmt.where(Inspection.kind == kind)
    return db.scalars(stmt).all()


@router.get("/inspections/photos/{photo_id}/download")
def download_photo(db: Db, _: CurrentUser, photo_id: UUID) -> Response:
    """AUTENTICADO. `storage/` nunca é pasta estática (CLAUDE.md, regra 5)."""
    photo = service.get_photo(db, photo_id)
    return files_service.download(photo.storage_key, photo.mime_type, photo.original_filename)


@router.delete("/inspections/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(db: Db, _: CurrentUser, photo_id: UUID) -> None:
    service.delete_photo(db, service.get_photo(db, photo_id))


@router.get("/inspections/{inspection_id}", response_model=InspectionDetailOut)
def get_inspection(db: Db, _: CurrentUser, inspection_id: UUID):
    return service.get_inspection(db, inspection_id)


@router.patch("/inspections/{inspection_id}", response_model=InspectionDetailOut)
def update_inspection(inspection_id: UUID, data: InspectionUpdate, db: Db, _: CurrentUser):
    inspection = service.get_inspection(db, inspection_id)
    return service.update_inspection(db, inspection, data)


@router.post(
    "/inspections/{inspection_id}/photos",
    response_model=list[InspectionPhotoOut],
    status_code=status.HTTP_201_CREATED,
)
def upload_photos(
    db: Db,
    _: CurrentUser,
    inspection_id: UUID,
    category: Annotated[PhotoCategory, Form()],
    files: Annotated[list[UploadFile], File()],
    caption: Annotated[str | None, Form()] = None,
):
    """Aceita vários arquivos por request (o frontend sobe 3-4 em paralelo, com barra de
    progresso). A categoria `assinatura` é a foto da vistoria assinada — nada de especial
    aqui, é só mais uma categoria."""
    inspection = service.get_inspection(db, inspection_id)
    return service.add_photos(db, inspection, files, category, caption)
