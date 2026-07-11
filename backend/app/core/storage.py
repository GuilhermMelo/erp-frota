"""Guarda de arquivos (fotos, contratos, notas fiscais).

Hoje grava em disco local. A interface existe para que trocar por S3/R2 amanhã seja
implementar estes quatro métodos — sem tocar em nenhum domínio.

Os arquivos NUNCA são servidos como pasta estática: CNH, CPF e contratos são dado
pessoal. O download passa pelo endpoint autenticado GET /files/{key}.
"""

import re
import unicodedata
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError, NotFound

MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB — o navegador já comprime antes de subir
ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def _slugify(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return (name or "arquivo")[:60]


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def key_for(self, namespace: str, entity_code: str, filename: str) -> str:
        """Ex.: inspections/VST000001/a1b2c3-frente.jpg"""
        unique = uuid.uuid4().hex[:8]
        return f"{namespace}/{entity_code}/{unique}-{_slugify(filename)}"

    def _path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        # Impede que um key com "../" escape da pasta de storage.
        if not target.is_relative_to(self.root):
            raise AppError("Caminho de arquivo inválido.")
        return target

    def save(self, key: str, data: bytes) -> int:
        if len(data) > MAX_FILE_BYTES:
            raise AppError(f"Arquivo maior que {MAX_FILE_BYTES // 1024 // 1024} MB.")
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return len(data)

    def open(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise NotFound("Arquivo não encontrado.")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)


storage = LocalStorage(settings.storage_path)
