# Empacota o backend num executável. Quem instalar o app não precisa ter Python.
#
# Rodar de dentro de backend/:  pyinstaller erp-frota-api.spec --noconfirm
#
# A interface (frontend/dist) precisa estar COMPILADA antes: `npm run build`.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

RAIZ = Path(SPECPATH).parent
FRONTEND_DIST = RAIZ / "frontend" / "dist"

if not FRONTEND_DIST.is_dir():
    raise SystemExit(
        f"A interface não foi compilada: {FRONTEND_DIST} não existe.\n"
        "Rode `npm run build` em frontend/ antes de empacotar."
    )

datas = [
    # As migrações rodam sozinhas no boot do app — ninguém vai abrir um terminal para
    # rodar `alembic upgrade head` num programa de desktop.
    (str(Path(SPECPATH) / "migrations"), "migrations"),
    (str(Path(SPECPATH) / "alembic.ini"), "."),
    # A interface compilada, servida pela própria API (mesma porta, sem CORS).
    (str(FRONTEND_DIST), "static"),
]
binaries = []
hiddenimports = [
    # O uvicorn carrega loop e protocolo por string em tempo de execução: o PyInstaller
    # não enxerga esses imports sozinho e o .exe subiria sem servidor HTTP.
    *collect_submodules("uvicorn"),
    # O app INTEIRO, não só "app.main": o Alembic lê migrations/env.py do disco em tempo
    # de execução (load_python_file), e o `from app.db.base import Base` de lá é invisível
    # para o PyInstaller. Sem isto o .exe empacota zero models e a migração morre no boot
    # com ModuleNotFoundError: No module named 'app.db.base'.
    *collect_submodules("app"),
]

# Alembic carrega o env.py e os templates por caminho; psycopg e bcrypt têm binários.
for pacote in ("alembic", "psycopg", "bcrypt", "pydantic", "email_validator"):
    d, b, h = collect_all(pacote)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["run_server.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="erp-frota-api",
    console=False,  # sem janela de terminal piscando atrás do app
    debug=False,
    strip=False,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="erp-frota-api",
)
