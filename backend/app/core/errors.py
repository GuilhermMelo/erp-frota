"""Envelope de erro único para toda a API.

Toda resposta de erro tem a mesma forma:
    {"error": {"code": "...", "message": "...", "details": ...}}

O frontend lê sempre `error.message`, sem adivinhar formato.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Erro de negócio previsto. A mensagem é exibida ao usuário."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "erro"

    def __init__(self, message: str, *, details=None, status_code: int | None = None, code: str | None = None):
        self.message = message
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        super().__init__(message)


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "nao_encontrado"


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflito"


class Unauthorized(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "nao_autenticado"


class Forbidden(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "sem_permissao"


def _envelope(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = [
            {"campo": ".".join(str(p) for p in e["loc"][1:]), "erro": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("dados_invalidos", "Dados inválidos.", details),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Loga o traceback, mas nunca vaza stack trace na resposta.
        logger.exception("Erro não tratado em %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("erro_interno", "Erro interno no servidor."),
        )
