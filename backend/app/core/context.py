"""Quem está fazendo a requisição, disponível para o listener de auditoria.

O listener roda dentro do flush do SQLAlchemy, longe do request. Um ContextVar é a
forma limpa de levar o usuário até lá sem passar `user` por dez camadas.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Actor:
    user_id: UUID | None
    email: str
    ip: str | None = None


_actor: ContextVar[Actor | None] = ContextVar("actor", default=None)


def set_actor(actor: Actor | None) -> None:
    _actor.set(actor)


def get_actor() -> Actor | None:
    return _actor.get()
