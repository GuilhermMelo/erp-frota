"""Ponto de entrada do backend empacotado (PyInstaller).

O Electron sobe este executável em segundo plano e espera o /health responder antes de
mostrar a janela. Quem instalar o app não precisa ter Python.
"""

import multiprocessing
import os
import sys
import traceback
from pathlib import Path

LIMITE_LOG = 5 * 1024 * 1024  # 5 MB


def _abrir_log() -> Path:
    """Liga sys.stdout/sys.stderr a um arquivo e devolve o caminho dele.

    O .exe é gerado com `console=False` (nenhuma janela de terminal piscando atrás do
    app). Sem console, o Windows não dá handles de saída ao processo e o Python deixa
    `sys.stdout` e `sys.stderr` em None. O uvicorn chama `sys.stdout.isatty()` ao montar
    o formatador de log e o app morre antes de subir, com
    "'NoneType' object has no attribute 'isatty'".

    Apontar as duas saídas para um arquivo resolve as duas pontas: o logger volta a
    funcionar E sobra um log para depurar na máquina de quem instalou — que não tem
    terminal nem Python para descobrir por que o app não abriu.
    """
    from app.core.paths import data_dir

    caminho = data_dir() / "logs" / "backend.log"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if caminho.exists() and caminho.stat().st_size > LIMITE_LOG:
        caminho.unlink()

    arquivo = open(caminho, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 (vive enquanto o processo viver)
    if sys.stdout is None:
        sys.stdout = arquivo
    if sys.stderr is None:
        sys.stderr = arquivo
    return caminho


def main() -> None:
    multiprocessing.freeze_support()  # sem isto o .exe se re-executa em loop no Windows

    log = _abrir_log()

    try:
        from app.main import app  # importado aqui para o erro cair no log, não numa caixa de diálogo

        import uvicorn

        uvicorn.run(
            app,  # o objeto, não a string "app.main:app": import por string quebra no .exe
            host="127.0.0.1",  # só a própria máquina. NUNCA 0.0.0.0 num app de desktop.
            port=int(os.environ.get("ERP_PORT", "8010")),
            log_level="info",
            use_colors=False,  # o log vai para arquivo; códigos de cor só sujariam o texto
        )
    except BaseException:
        # Sem console, uma exceção aqui vira um diálogo do Windows sem contexto nenhum.
        # Registrar antes de morrer é a única pista que sobra para quem for depurar.
        traceback.print_exc(file=sys.stderr)
        print(f"\n[erp-frota] backend encerrado com erro. Log: {log}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
