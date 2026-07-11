from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET = "dev-secret-troque-em-producao"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "dev"
    SECRET_KEY: str = DEFAULT_SECRET
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    DATABASE_URL: str = "postgresql+psycopg://frota:frota@localhost:5434/frota"
    STORAGE_DIR: str = "../storage"
    CORS_ORIGINS: str = "http://localhost:5173"

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
    def _fail_fast_on_weak_secret(self) -> "Settings":
        # Fora de dev, subir com o segredo padrão significa que qualquer um forja um JWT
        # e vira admin. Melhor não subir.
        if not self.is_dev and (self.SECRET_KEY == DEFAULT_SECRET or len(self.SECRET_KEY) < 32):
            raise RuntimeError(
                "SECRET_KEY inseguro para ENV=%s. Gere um com: "
                'python -c "import secrets; print(secrets.token_urlsafe(32))"' % self.ENV
            )
        return self


settings = Settings()
