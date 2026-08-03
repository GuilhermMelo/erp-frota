# Imagem única com a API e a interface — o mesmo arranjo de "uma porta só" que o app
# empacotado usa. A API serve o React compilado; não há servidor web separado e não há
# CORS entre front e back, porque não há duas origens.
#
# Roda igual em Render, Railway, Fly.io ou qualquer lugar que aceite um Dockerfile.

# ---------------------------------------------------------------- 1. interface
FROM node:22-alpine AS interface
WORKDIR /ui

# package*.json antes do código: o Docker reusa a camada de dependências enquanto
# elas não mudarem, e `npm ci` é o passo caro.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ------------------------------------------------------------------- 2. a API
FROM python:3.13-slim AS app

# PYTHONDONTWRITEBYTECODE: o filesystem do container é descartável, .pyc é peso morto.
# PYTHONUNBUFFERED: sem isto o log fica preso no buffer e o painel do host mostra
# uma aplicação "silenciosa" que na verdade está falando.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=production \
    STORAGE_BACKEND=supabase

WORKDIR /app

# psycopg vem em binário (requirements), então não é preciso libpq-dev nem compilador.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
# A interface compilada vai para onde `paths.static_dir()` procura.
COPY --from=interface /ui/dist ./static

# Usuário sem privilégio: se a aplicação for comprometida, o atacante não é root.
RUN useradd --create-home --uid 10001 erp && chown -R erp:erp /app
USER erp

EXPOSE 8000

# As migrações rodam no lifespan do próprio app (main.py), não aqui: assim um deploy
# que sobe duas instâncias não dispara dois `alembic upgrade` concorrentes no boot.
#
# $PORT é definido pelo Render e pelo Railway. O fallback serve para rodar local.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
