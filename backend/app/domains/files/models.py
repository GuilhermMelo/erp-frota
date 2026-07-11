from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, UUIDPrimaryKey


class DocumentKind(str, Enum):
    contrato_pdf = "contrato_pdf"
    confissao_divida = "confissao_divida"
    assinatura = "assinatura"
    nota_fiscal = "nota_fiscal"
    cnh = "cnh"
    crlv = "crlv"
    notificacao = "notificacao"  # notificação de multa
    foto = "foto"
    outro = "outro"


class Document(UUIDPrimaryKey, Base):
    """Anexo genérico: PDF do contrato, foto da assinatura, nota fiscal, CNH, CRLV.

    Usa ponteiro polimórfico (entity_type + entity_id), o que sacrifica integridade
    referencial — e por isso é PROIBIDO em tabela financeira. Aqui é aceitável: anexo é
    folha, não entra em conta nenhuma. As fotos de vistoria ficam em `inspection_photos`
    (tabela própria) por serem centenas por vistoria e terem categoria e ordem.
    """

    __tablename__ = "documents"

    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # contract/fine/maintenance/vehicle/driver
    entity_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    kind: Mapped[DocumentKind] = mapped_column(
        SAEnum(DocumentKind, native_enum=False, length=30, name="document_kind"),
        default=DocumentKind.outro,
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(60), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_documents_entidade", "entity_type", "entity_id"),)
