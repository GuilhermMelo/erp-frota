from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core import paths

DEFAULT_SECRET = "dev-secret-troque-em-producao"
DEFAULT_STORAGE = "../storage"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "dev"
    SECRET_KEY: str = DEFAULT_SECRET
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    DATABASE_URL: str = "postgresql+psycopg://frota:frota@localhost:5434/frota"
    STORAGE_DIR: str = DEFAULT_STORAGE
    CORS_ORIGINS: str = "http://localhost:5273"

    # NÃO use um domínio .local/.test/.invalid aqui: o login valida o e-mail com EmailStr,
    # que recusa domínios reservados — o admin do seed nunca conseguiria entrar.
    ADMIN_EMAIL: str = "admin@erpfrota.com.br"
    ADMIN_PASSWORD: str = "admin123"
    ADMIN_NAME: str = "Administrador"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def storage_path(self) -> Path:
        return Path(self.STORAGE_DIR).resolve()

    @property
    def is_dev(self) -> bool:
        return self.ENV == "dev"

    @model_validator(mode="after")
    def _resolve(self) -> "Settings":
        # A pasta de arquivos é a MESMA no código-fonte e no .exe instalado (ver paths.py).
        # Os dois falam com o mesmo banco, e o banco guarda só o CAMINHO do arquivo — raízes
        # diferentes fariam um PDF anexado num modo não abrir no outro.
        # Os testes sobrescrevem STORAGE_DIR para um tmp; por isso o `if`.
        if self.STORAGE_DIR == DEFAULT_STORAGE:
            self.STORAGE_DIR = str(paths.data_dir() / "storage")

        # O segredo padrão está no código-fonte. Cada instalação sorteia o seu na primeira
        # execução; sem isso, qualquer um forjaria um token de admin.
        if paths.IS_FROZEN and self.SECRET_KEY == DEFAULT_SECRET:
            self.SECRET_KEY = paths.installation_secret()

        # Fora de dev, subir com o segredo padrão significa que qualquer um forja um JWT
        # e vira admin. Melhor não subir.
        if not self.is_dev and (self.SECRET_KEY == DEFAULT_SECRET or len(self.SECRET_KEY) < 32):
            raise RuntimeError(
                f"SECRET_KEY inseguro para ENV={self.ENV}. Gere um com: "
                'python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        return self


settings = Settings()
