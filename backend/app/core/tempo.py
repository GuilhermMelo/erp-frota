"""Que dia é hoje — para a locadora, não para o servidor.

`date.today()` devolve o dia do FUSO DO PROCESSO. No desktop isso é BRT (UTC−3) e está
certo por acidente; no container do Render é UTC e está errado das 21h à meia-noite todo
dia. São três horas por dia em que os dois sistemas discordam sobre a data.

Isso é dinheiro, não estética. A inadimplência aqui é **derivada** (`due_date < hoje`),
nunca armazenada: uma cobrança que vence hoje aparece em atraso a partir das 21h para quem
olha pelo Render, e em dia para quem olha pelo desktop. O mesmo banco, dois números. E na
virada do mês o lançamento cai na competência errada.

O fuso é o da operação e fica FIXO no código, não numa variável de ambiente: um deploy que
esquece a variável não pode ter o direito de mudar em que dia uma dívida vence.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

# A locadora opera em São Paulo. `ZoneInfo` já cuida do horário de verão caso ele volte —
# um `timedelta(hours=-3)` fixo não cuidaria.
FUSO = ZoneInfo("America/Sao_Paulo")


def hoje() -> date:
    """O dia corrente na operação. Use SEMPRE isto no lugar de `date.today()`."""
    return datetime.now(FUSO).date()


def agora() -> datetime:
    """O instante corrente, com fuso. Para carimbo de data/hora, não para dia."""
    return datetime.now(FUSO)
