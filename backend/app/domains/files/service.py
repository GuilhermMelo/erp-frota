"""Política de upload: o que pode entrar no storage, e como sai de lá.

Mora aqui porque `files` é o domínio dono dos anexos — mas as FOTOS DE VISTORIA usam
exatamente a mesma validação (ver `inspections/service.py`). Um .exe renomeado para .jpg
não pode entrar por porta nenhuma; ter duas validações diferentes seria ter uma porta
esquecida.

O mime que o navegador envia vem da EXTENSÃO do arquivo, não do conteúdo. Por isso ele é
só o primeiro filtro: quem decide o que fica gravado — e o que volta no `Content-Type` do
download — são os BYTES.
"""

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import quote
from uuid import UUID

from fastapi import Response, UploadFile
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.storage import ALLOWED_MIME, MAX_FILE_BYTES, storage
from app.domains.files.models import Document

ACEITOS = "JPEG, PNG, WebP, PDF"

_PDF_MAGIC = b"%PDF"
_MAX_MB = MAX_FILE_BYTES // 1024 // 1024
# Formato que o Pillow detecta -> mime que vamos gravar.
_IMAGE_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
# Tudo que não é isso quebraria o header (aspas, CR/LF) — nome de arquivo é entrada do usuário.
_UNSAFE_IN_HEADER = re.compile(r"[^A-Za-z0-9._ -]")


@dataclass(frozen=True)
class Upload:
    """Arquivo já lido e validado — pronto para ir ao disco."""

    data: bytes
    mime_type: str
    filename: str
    size: int


def _tipo_nao_permitido(mime: str) -> AppError:
    return AppError(f"Tipo de arquivo não permitido: {mime or 'desconhecido'}. Aceitos: {ACEITOS}.")


def _sniff(data: bytes, declared: str, filename: str) -> str:
    """Confere que os BYTES são mesmo do tipo declarado e devolve o mime REAL.

    Imagem: o Pillow abre e faz `verify()`. Um executável renomeado para .jpg morre aqui —
    e morre ANTES de tocar o disco. PDF: os bytes têm que começar com `%PDF`.
    """
    if declared == "application/pdf":
        if not data.startswith(_PDF_MAGIC):
            raise AppError(f"O arquivo {filename} não é um PDF válido.")
        return declared

    try:
        image = Image.open(io.BytesIO(data))
        detected = (image.format or "").upper()
        image.verify()  # levanta se os bytes não formam uma imagem íntegra
    except Exception:
        raise AppError(f"O arquivo {filename} não é uma imagem válida.") from None

    mime = _IMAGE_FORMATS.get(detected)
    if mime is None:
        # Ex.: um .bmp renomeado para .png. É imagem de verdade, mas não é aceita.
        raise _tipo_nao_permitido(detected.lower())
    # Vale o que os bytes dizem, não o que o navegador chutou pela extensão: é este mime
    # que volta no Content-Type do download.
    return mime


def read_upload(file: UploadFile) -> Upload:
    """Lê, valida (tipo, tamanho, conteúdo real) e devolve o arquivo pronto para gravar."""
    filename = (file.filename or "arquivo").strip()
    declared = (file.content_type or "").split(";")[0].strip().lower()

    if declared not in ALLOWED_MIME:
        raise _tipo_nao_permitido(declared)
    # `size` vem do multipart e evita ler 500 MB na memória só para depois recusar.
    if file.size is not None and file.size > MAX_FILE_BYTES:
        raise AppError(f"O arquivo {filename} é maior que {_MAX_MB} MB.")

    data = file.file.read()
    if not data:
        raise AppError(f"O arquivo {filename} está vazio.")
    if len(data) > MAX_FILE_BYTES:
        raise AppError(f"O arquivo {filename} é maior que {_MAX_MB} MB.")

    return Upload(
        data=data,
        mime_type=_sniff(data, declared, filename),
        filename=filename,
        size=len(data),
    )


def save(namespace: str, entity_code: str, upload: Upload) -> str:
    """Grava no storage e devolve a chave. `namespace` é a pasta: contracts/, inspections/..."""
    key = storage.key_for(namespace, entity_code, upload.filename)
    storage.save(key, upload.data)
    return key


def delete_documents_for(db: Session, entity_type: str, entity_id: UUID) -> list[str]:
    """Marca para exclusão os anexos de uma entidade e devolve as chaves de storage.

    `documents` usa ponteiro polimórfico (entity_type + entity_id) e por isso NÃO tem
    foreign key: NADA cascateia. Sem chamar isto ao apagar uma manutenção ou multa, a nota
    fiscal fica no disco e a linha fica no banco para sempre — lixo invisível que ninguém
    mais consegue nem listar, porque a entidade dona sumiu.

    Não faz commit: quem chama decide a transação. Depois do commit, passe o retorno para
    `purge_files()`.
    """
    docs = db.scalars(
        select(Document).where(
            Document.entity_type == entity_type, Document.entity_id == entity_id
        )
    ).all()
    for doc in docs:
        db.delete(doc)
    return [doc.storage_key for doc in docs]


def purge_files(keys: Iterable[str]) -> None:
    """Apaga os arquivos do disco. Chame DEPOIS do commit.

    O banco é o índice do que existe: arquivo órfão é lixo invisível, linha órfã é tela
    quebrada. Se o commit falhar, é melhor sobrar arquivo do que faltar.
    """
    for key in keys:
        storage.delete(key)


def download(storage_key: str, mime_type: str, filename: str | None) -> Response:
    """Devolve os bytes do arquivo.

    SEMPRE por endpoint autenticado: `storage/` nunca é servido como pasta estática, porque
    lá dentro tem CNH, CPF e contrato assinado (LGPD — ARQUITETURA.md, regra 5).
    """
    name = filename or "arquivo"
    ascii_name = _UNSAFE_IN_HEADER.sub("_", name) or "arquivo"
    return Response(
        content=storage.open(storage_key),
        media_type=mime_type,
        headers={
            # filename* (RFC 5987) preserva o acento; filename= é o fallback ASCII.
            "Content-Disposition": f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name)}',
        },
    )
