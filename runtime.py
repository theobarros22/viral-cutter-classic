"""Configuração de caminhos para execução em código-fonte ou executável."""

import os
import sys
import logging
import tempfile
import json
import socket
from datetime import datetime


NOME_APP = "ViralCutter"
_MUTEX = None


def configurar_console_utf8() -> None:
    """Evita falha de Unicode em consoles Windows configurados como CP1252."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def pasta_base() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def configurar_ambiente() -> None:
    """Adiciona ferramentas empacotadas ao PATH da execução atual."""
    candidatos = [
        os.path.join(pasta_base(), "tools"),
        os.path.join(getattr(sys, "_MEIPASS", pasta_base()), "tools"),
    ]
    existentes = [p for p in candidatos if os.path.isdir(p)]
    if existentes:
        os.environ["PATH"] = os.pathsep.join(existentes + [os.environ.get("PATH", "")])


def pasta_dados() -> str:
    caminho = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), NOME_APP)
    os.makedirs(caminho, exist_ok=True)
    return caminho


def configurar_logs() -> str:
    """Registra erros em arquivo sem depender da janela de console."""
    pasta = os.path.join(pasta_dados(), "logs")
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, f"viral_cutter_{datetime.now():%Y%m%d}.log")
    logging.basicConfig(
        filename=caminho,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )

    def registrar_excecao(tipo, valor, traceback):
        logging.getLogger(NOME_APP).critical(
            "Erro não tratado", exc_info=(tipo, valor, traceback)
        )
        sys.__excepthook__(tipo, valor, traceback)

    sys.excepthook = registrar_excecao
    return caminho


def garantir_instancia_unica() -> bool:
    """Evita duas instâncias disputando GPU, arquivos e estado da interface."""
    global _MUTEX
    if os.name != "nt":
        return True

    import ctypes

    _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\ViralCutterV2")
    return ctypes.windll.kernel32.GetLastError() != 183


def escolher_porta(inicial: int = 7860, tentativas: int = 30) -> int:
    """Escolhe uma porta local livre sem falhar quando 7860 estiver ocupada."""
    for porta in range(inicial, inicial + tentativas):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", porta))
                return porta
            except OSError:
                continue
    raise RuntimeError("Nenhuma porta local livre foi encontrada.")


def registrar_status(porta: int, estado: str) -> str:
    caminho = os.path.join(pasta_dados(), "status.json")
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump({"porta": porta, "estado": estado}, arquivo)
    return caminho
