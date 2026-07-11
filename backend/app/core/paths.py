"""Onde estão os arquivos — rodando do código-fonte ou dentro do .exe empacotado.

O PyInstaller descompacta os dados num diretório temporário e aponta `sys._MEIPASS` para
ele. Sem isto, o app empacotado procuraria as migrações e o `index.html` na pasta do
projeto — que não existe na máquina de quem instalou.
"""

import os
import secrets
import sys
from pathlib import Path

# True quando rodando de dentro do executável gerado pelo PyInstaller.
IS_FROZEN = getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """Os arquivos que VÊM com o app (migrações, interface). Somente leitura."""
    if IS_FROZEN:
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # backend/app/core/paths.py -> backend/
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """Onde o app ESCREVE: fotos, contratos, chave secreta.

    Instalado, o app mora em `C:\\Program Files`, que NÃO é gravável pelo usuário. Gravar
    ao lado do .exe daria "Acesso negado" no primeiro upload de foto. Tudo que o app
    escreve vai para a pasta do usuário.
    """
    if IS_FROZEN:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        # Sem acento e sem espaço problemático: este caminho aparece em log, em mensagem de
        # erro e na barra de endereço do Explorer quando o dono for procurar as fotos.
        d = Path(base) / "GM Locacoes"
    else:
        d = resource_dir().parent  # a raiz do projeto, em desenvolvimento
    d.mkdir(parents=True, exist_ok=True)
    return d


def installation_secret() -> str:
    """Chave de assinatura do JWT, sorteada UMA vez por instalação e guardada.

    Sem isto, todas as instalações compartilhariam o segredo padrão que está no
    código-fonte — e qualquer um poderia forjar um token de admin.
    """
    arquivo = data_dir() / "secret.key"
    if not arquivo.exists():
        arquivo.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return arquivo.read_text(encoding="utf-8").strip()


def migrations_dir() -> Path:
    return resource_dir() / "migrations"


def alembic_ini() -> Path:
    return resource_dir() / "alembic.ini"


def static_dir() -> Path:
    """A interface compilada (npm run build). Só existe no app empacotado."""
    return resource_dir() / "static"
