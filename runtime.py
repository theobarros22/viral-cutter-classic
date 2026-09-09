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
    configurar_pasta_temporaria()


def suprimir_janelas_de_console() -> None:
    """Impede que cada chamada de ffmpeg abra uma janela preta na tela.

    O app roda por pythonw, sem console. No Windows, um processo de console
    filho de um pai sem console cria a PRÓPRIA janela — e o processamento chama
    ffmpeg/ffprobe dezenas de vezes por clipe, então a tela fica piscando
    janelas durante horas, por cima do que a pessoa estiver fazendo.

    São ~46 pontos de chamada espalhados por dez módulos. Interceptar na origem
    cobre todos eles e também os que forem escritos depois.
    """
    if os.name != "nt":
        return

    import subprocess

    if getattr(subprocess.Popen, "_viralcutter_sem_janela", False):
        return

    original = subprocess.Popen.__init__
    sem_janela = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    def __init__(self, *args, **kwargs):
        # creationflags é o 14º posicional. Ninguém passa assim na prática, mas
        # se passar, respeita o que veio em vez de estourar com argumento duplo.
        if len(args) < 14:
            kwargs["creationflags"] = (kwargs.get("creationflags") or 0) | sem_janela
        return original(self, *args, **kwargs)

    subprocess.Popen.__init__ = __init__
    subprocess.Popen._viralcutter_sem_janela = True


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


def _pasta_gravavel(caminho: str) -> bool:
    """Confirma que da para escrever de verdade, nao so que o caminho existe.

    Uma unidade removida deixa a letra registrada no Windows: os.path.isdir
    responde True e a falha so aparece na primeira escrita, ja dentro do
    Gradio. Por isso o teste e uma escrita real.
    """
    try:
        os.makedirs(caminho, exist_ok=True)
        teste = os.path.join(caminho, ".escrita_ok")
        with open(teste, "w", encoding="utf-8") as arquivo:
            arquivo.write("ok")
        os.remove(teste)
        return True
    except Exception:
        return False


def configurar_pasta_temporaria() -> str:
    """Define GRADIO_TEMP_DIR num lugar que sempre existe.

    O padrao passa a ser LOCALAPPDATA (disco do sistema, sempre montado). Um
    valor vindo de fora so e respeitado se passar no teste de escrita — assim
    um caminho apontando para uma unidade ausente nao derruba a inicializacao,
    apenas e descartado.
    """
    candidatos = []
    definido = os.environ.get("GRADIO_TEMP_DIR")
    if definido:
        candidatos.append(definido)
    candidatos.append(os.path.join(pasta_dados(), "gradio_temp"))
    candidatos.append(os.path.join(tempfile.gettempdir(), NOME_APP, "gradio_temp"))

    for caminho in candidatos:
        if _pasta_gravavel(caminho):
            if definido and caminho != definido:
                logging.getLogger(NOME_APP).warning(
                    "GRADIO_TEMP_DIR=%s nao esta gravavel; usando %s.", definido, caminho
                )
            os.environ["GRADIO_TEMP_DIR"] = caminho
            return caminho

    raise RuntimeError("Nenhuma pasta temporaria gravavel foi encontrada.")


def discos_prontos() -> list:
    """Raizes montadas e legiveis, para liberar no allowed_paths do Gradio.

    Substitui a lista fixa com "D:\\": aquela letra pertence a um leitor de
    cartao sem midia, e as letras dos discos externos mudam entre sessoes.
    """
    if os.name != "nt":
        return ["/"]
    raizes = []
    for letra in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        raiz = letra + ":\\"
        try:
            if os.path.isdir(raiz) and os.listdir(raiz) is not None:
                raizes.append(raiz)
        except Exception:
            continue
    return raizes
