from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.storage import storage
from app.domains.auth.deps import CurrentUser, Db
from app.domains.contracts.models import Contract
from app.domains.drivers.models import Driver
from app.domains.files import service
from app.domains.files.models import Document, DocumentKind
from app.domains.files.schemas import DocumentOut, EntityType
from app.domains.fines.models import Fine
from app.domains.maintenances.models import Maintenance
from app.domains.vehicles.models import Vehicle

router = APIRouter(prefix="/files", tags=["arquivos"])

# entity_type -> (model, pasta no storage). A pasta é o plural do tipo: a chave do arquivo
# vira `contracts/CTR000007/a1b2c3-contrato.pdf` — legível quando alguém abrir o disco.
_ENTITIES: dict[EntityType, tuple[type, str]] = {
    EntityType.contract: (Contract, "contracts"),
    EntityType.fine: (Fine, "fines"),
    EntityType.maintenance: (Maintenance, "maintenances"),
    EntityType.vehicle: (Vehicle, "vehicles"),
    EntityType.driver: (Driver, "drivers"),
}


def _entity_code(db: Session, entity_type: EntityType, entity_id: UUID) -> tuple[str, str]:
    """Devolve (código da entidade, namespace). Anexo órfão não entra."""
    model, namespace = _ENTITIES[entity_type]
    entity = db.get(model, entity_id)
    # `deleted_at` só existe em veículo e motorista (soft delete); excluído é inexistente.
    if entity is None or getattr(entity, "deleted_at", None) is not None:
        raise NotFound("Registro não encontrado.")
    return entity.code, namespace


def _get_document(db: Session, document_id: UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFound("Documento não encontrado.")
    return document


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    db: Db,
    user: CurrentUser,
    entity_type: Annotated[EntityType, Form()],
    entity_id: Annotated[UUID, Form()],
    kind: Annotated[DocumentKind, Form()],
    file: Annotated[UploadFile, File()],
):
    entity_code, namespace = _entity_code(db, entity_type, entity_id)
    upload = service.read_upload(file)  # valida ANTES de tocar o disco
    storage_key = service.save(namespace, entity_code, upload)

    document = Document(
        entity_type=entity_type.value,
        entity_id=entity_id,
        kind=kind,
        storage_key=storage_key,
        original_filename=upload.filename,
        mime_type=upload.mime_type,
        size_bytes=upload.size,
        uploaded_by_user_id=user.id,
    )
    db.add(document)
    db.commit()
    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Db, _: CurrentUser, entity_type: EntityType, entity_id: UUID):
    return db.scalars(
        select(Document)
        .where(Document.entity_type == entity_type.value, Document.entity_id == entity_id)
        .order_by(Document.created_at.desc())
    ).all()


@router.get("/{document_id}/download")
def download_document(db: Db, _: CurrentUser, document_id: UUID) -> Response:
    """AUTENTICADO, sempre. Aqui dentro tem CNH, CPF e contrato assinado."""
    document = _get_document(db, document_id)
    return service.download(document.storage_key, document.mime_type, document.original_filename)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(db: Db, _: CurrentUser, document_id: UUID) -> None:
    document = _get_document(db, document_id)
    storage_key = document.storage_key

    # O banco é o índice do que existe: primeiro sai a linha (com log de auditoria),
    # depois o arquivo. Se o unlink falhar, sobra lixo invisível no disco — ruim, mas
    # muito melhor que uma linha na tela apontando para um arquivo que não existe mais.
    db.delete(document)
    db.commit()
    storage.delete(storage_key)
