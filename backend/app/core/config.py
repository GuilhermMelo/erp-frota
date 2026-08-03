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
    CORS_ORIGINS: str = "http://localhost:5273"

    # --- Arquivos (CNH, contratos, fotos de vistoria) ---------------------------
    # "local" grava em disco; "supabase" grava no Storage do Supabase.
    # Em hospedagem sem volume (Render, Railway) o disco do container SOME a cada
    # deploy: "local" ali significa perder foto de vistoria e contrato assinado.
    STORAGE_BACKEND: str = "local"
    STORAGE_DIR: str = DEFAULT_STORAGE

    SUPABASE_URL: str = ""
    # A chave `service_role`. NUNCA vai para o frontend: ela ignora RLS por
    # definição. Vive só como variável de ambiente do servidor.
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_BUCKET: str = "arquivos"

    # NÃO use um domínio .local/.test/.invalid aqui: o login valida o e-mail com EmailStr,
    # que recusa domínios reservados — o admin do seed nunca conseguiria entrar.
    ADMIN_EMAIL: str = "admin@erpfrota.com.br"
    # Vazio de propósito. Senha padrão em código-fonte é senha PÚBLICA: vale para toda
    # instalação que existir, e este repositório é aberto. Sem valor aqui, o seed sorteia
    # a senha do primeiro admin e a entrega num arquivo (ver seed.py).
    ADMIN_PASSWORD: str = ""
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

        # Em nuvem o SECRET_KEY TEM que vir de variável de ambiente e ser FIXO. Se cada
        # deploy sorteasse um novo, todo token emitido antes viraria inválido e o sistema
        # deslogaria todo mundo a cada publicação — parecendo bug intermitente de login.

        # Sem a senha configurada, o seed sorteia e grava num arquivo. Isso funciona no
        # desktop, onde o dono abre a pasta e lê. Num container o arquivo morre com o
        # deploy: ninguém nunca veria a senha e o sistema nasceria inacessível.
        if not self.is_dev and not self.ADMIN_PASSWORD:
            raise RuntimeError(
                f"ADMIN_PASSWORD é obrigatório para ENV={self.ENV}. Fora do desktop não há "
                "onde entregar uma senha sorteada. Defina a variável, entre no sistema e "
                "troque a senha pela tela de Usuários."
            )

        if self.STORAGE_BACKEND not in ("local", "supabase"):
            raise RuntimeError(f"STORAGE_BACKEND inválido: {self.STORAGE_BACKEND!r}.")

        if self.STORAGE_BACKEND == "supabase" and not (self.SUPABASE_URL and self.SUPABASE_SERVICE_KEY):
            raise RuntimeError(
                "STORAGE_BACKEND=supabase exige SUPABASE_URL e SUPABASE_SERVICE_KEY. "
                "Falhar aqui é melhor que aceitar upload e perder o arquivo."
            )
        return self


settings = Settings()
