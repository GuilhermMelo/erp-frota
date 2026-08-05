"""Que dia é hoje — e por que isso é conta de dinheiro.

A inadimplência aqui é DERIVADA (`due_date < hoje`), nunca armazenada. Então "hoje" não é
detalhe de apresentação: é o que decide se uma cobrança está em atraso. `date.today()` segue
o fuso do PROCESSO — BRT no desktop, UTC no container do Render. Das 21h à meia-noite, todo
dia, os dois respondem datas diferentes para o mesmo banco.
"""

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.core.tempo import FUSO, hoje
from tests.conftest import BACKEND_DIR


def test_o_fuso_e_o_da_operacao_nao_o_do_servidor():
    """Às 22h de São Paulo já é o dia seguinte em UTC. É essa janela que quebra a conta.

    Sem mock: converte um instante REAL e conhecido. Se `FUSO` virasse `timezone.utc` — o
    tipo de "simplificação" que passa em revisão — este teste falha.
    """
    instante = datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc)  # 05/08 em UTC
    assert instante.astimezone(FUSO).date() == date(2026, 8, 4), "22h de 04/08 em São Paulo"
    assert instante.astimezone(timezone.utc).date() == date(2026, 8, 5), "e 05/08 em UTC"


def test_hoje_pergunta_a_hora_COM_fuso():
    """A prova de que `hoje()` aplica o fuso, em vez de só existir com nome bonito.

    Uma implementação `return date.today()` — mesmo dentro deste módulo — passaria em
    qualquer teste que só comparasse com a data de hoje. Aqui o relógio é substituído por um
    instante fixo, e a asserção sobre o ARGUMENTO é o que fecha a porta: `datetime.now()` sem
    fuso devolveria o horário do servidor.
    """
    congelado = datetime(2026, 8, 4, 22, 0, tzinfo=FUSO)
    with patch("app.core.tempo.datetime") as relogio:
        relogio.now.return_value = congelado
        assert hoje() == date(2026, 8, 4)
    relogio.now.assert_called_once_with(FUSO)


def test_hoje_nao_depende_do_relogio_local():
    """Contraprova do teste acima: quebrar `date.today()` não pode mudar `hoje()`.

    Se algum dia alguém "simplificar" o módulo de volta para `date.today()`, este teste é o
    que acusa — os dois de cima poderiam sobreviver a isso.
    """
    with patch("app.core.tempo.date") as calendario:
        calendario.today.return_value = date(1999, 1, 1)
        assert hoje() != date(1999, 1, 1)
    calendario.today.assert_not_called()


def test_nenhum_dominio_decide_hoje_pelo_relogio_do_servidor():
    """O guarda de regressão. Sem ele, a próxima rota nasce com `date.today()` e ninguém vê.

    Foi assim que o buraco existiu: quatro pontos, nenhum errado sozinho, todos errados
    juntos quando o sistema saiu do desktop e foi para um container em UTC.
    """
    ofensores = []
    for arquivo in (BACKEND_DIR / "app").rglob("*.py"):
        if arquivo.name == "tempo.py":  # é ele que define o certo, e cita o errado no texto
            continue
        texto = arquivo.read_text(encoding="utf-8")
        for numero, linha in enumerate(texto.splitlines(), 1):
            if "date.today()" in linha or "datetime.now()" in linha:
                ofensores.append(f"{arquivo.relative_to(BACKEND_DIR)}:{numero}")

    assert not ofensores, (
        "estes pontos decidem a data pelo fuso do processo — UTC no Render, BRT no desktop. "
        f"Use `from app.core.tempo import hoje`:\n  " + "\n  ".join(ofensores)
    )
