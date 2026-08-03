"""Guarda de arquivos (fotos, contratos, notas fiscais).

Duas implementações, mesma interface de quatro métodos — `key_for`, `save`, `open` e
`delete`. Nenhum domínio sabe qual está em uso:

    local       disco. É o modo do app de desktop e do desenvolvimento.
    supabase    Storage do Supabase. É o modo de nuvem, porque em host sem volume
                (Render, Railway) o disco do container some a cada deploy — e "some"
                aqui significa perder foto de vistoria e contrato assinado.

Os arquivos NUNCA são servidos como pasta estática, em nenhum dos dois modos: CNH, CPF e
contratos são dado pessoal. O download passa pelo endpoint autenticado GET /files/{key}.
Por isso o bucket do Supabase é PRIVADO e o acesso usa a chave `service_role` — que
justamente por ser irrestrita nunca sai do servidor.
"""

import re
import unicodedata
import uuid
from pathlib import Path

import httpx

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


def _key_for(namespace: str, entity_code: str, filename: str) -> str:
    """Ex.: inspections/VST000001/a1b2c3-frente.jpg

    O prefixo aleatório evita colisão quando duas fotos sobem com o mesmo nome do
    celular ("IMG_0001.jpg" é o caso normal, não a exceção).
    """
    unique = uuid.uuid4().hex[:8]
    return f"{namespace}/{entity_code}/{unique}-{_slugify(filename)}"


def _guard_size(data: bytes) -> None:
    if len(data) > MAX_FILE_BYTES:
        raise AppError(f"Arquivo maior que {MAX_FILE_BYTES // 1024 // 1024} MB.")


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def key_for(self, namespace: str, entity_code: str, filename: str) -> str:
        return _key_for(namespace, entity_code, filename)

    def _path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        # Impede que um key com "../" escape da pasta de storage.
        if not target.is_relative_to(self.root):
            raise AppError("Caminho de arquivo inválido.")
        return target

    def save(self, key: str, data: bytes) -> int:
        _guard_size(data)
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


class SupabaseStorage:
    """Storage do Supabase, pela API REST.

    Sem o SDK de propósito: são três chamadas HTTP, e o `supabase-py` traria uma árvore
    de dependências inteira para isso. `httpx` já está no projeto.

    O bucket é PRIVADO. Não existe URL pública para uma foto de CNH — o download continua
    passando pelo `GET /files/{key}` autenticado, exatamente como no modo local.
    """

    def __init__(self, url: str, service_key: str, bucket: str):
        self.bucket = bucket
        self._http = httpx.Client(
            base_url=f"{url.rstrip('/')}/storage/v1",
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
            },
            timeout=30,
        )

    def key_for(self, namespace: str, entity_code: str, filename: str) -> str:
        return _key_for(namespace, entity_code, filename)

    def save(self, key: str, data: bytes) -> int:
        _guard_size(data)
        r = self._http.post(
            f"/object/{self.bucket}/{key}",
            content=data,
            headers={
                "Content-Type": "application/octet-stream",
                # O mesmo key nunca se repete (uuid no nome), mas um retry de rede pode
                # reenviar o mesmo PUT. upsert torna isso inofensivo.
                "x-upsert": "true",
            },
        )
        if r.status_code >= 300:
            # A resposta do Supabase pode conter a chave em mensagem de erro; só o
            # status vai para o usuário. Nunca vaze credencial em texto de erro.
            raise AppError(f"Falha ao salvar o arquivo (HTTP {r.status_code}).")
        return len(data)

    def open(self, key: str) -> bytes:
        r = self._http.get(f"/object/{self.bucket}/{key}")
        if r.status_code == 404:
            raise NotFound("Arquivo não encontrado.")
        if r.status_code >= 300:
            raise AppError(f"Falha ao ler o arquivo (HTTP {r.status_code}).")
        return r.content

    def delete(self, key: str) -> None:
        # 404 é sucesso aqui: o objetivo é "não existir mais". Igual ao missing_ok
        # do modo local — apagar duas vezes não pode ser erro.
        r = self._http.delete(f"/object/{self.bucket}/{key}")
        if r.status_code >= 300 and r.status_code != 404:
            raise AppError(f"Falha ao apagar o arquivo (HTTP {r.status_code}).")


def _build():
    if settings.STORAGE_BACKEND == "supabase":
        return SupabaseStorage(
            settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY, settings.SUPABASE_BUCKET
        )
    return LocalStorage(settings.storage_path)


storage = _build()
