"""
coletar_ambiente.py
-------------------
Gera um relatorio da maquina e dos tempos ja registrados, para comparar
desempenho entre computadores diferentes.

Uso:
    python coletar_ambiente.py                 # imprime na tela
    python coletar_ambiente.py relatorio.txt   # salva em arquivo

Nao coleta nada pessoal: so hardware, versoes e os tempos por etapa que o
proprio programa ja grava nos logs de processamento.
"""

import glob
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime


def _rodar(comando: list, limite: int = 15) -> str:
    try:
        saida = subprocess.run(
            comando, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=limite,
        )
        return saida.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def secao_sistema() -> list:
    linhas = ["== SISTEMA =="]
    linhas.append(f"SO: {platform.platform()}")
    linhas.append(f"Processador: {platform.processor() or 'desconhecido'}")
    linhas.append(f"Nucleos logicos: {os.cpu_count()}")
    try:
        import ctypes

        class Memoria(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        memoria = Memoria()
        memoria.dwLength = ctypes.sizeof(Memoria)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memoria))
        linhas.append(f"Memoria RAM: {memoria.ullTotalPhys / 1024**3:.1f} GB")
    except Exception:
        linhas.append("Memoria RAM: nao detectada")
    return linhas


def secao_gpu() -> list:
    linhas = ["", "== PLACA DE VIDEO =="]
    if shutil.which("nvidia-smi"):
        info = _rodar([
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ])
        linhas.append(f"NVIDIA: {info or 'nvidia-smi nao respondeu'}")
    else:
        linhas.append("NVIDIA: nenhuma GPU NVIDIA detectada (o programa usa a CPU)")

    try:
        import torch

        linhas.append(f"PyTorch: {torch.__version__}")
        if torch.cuda.is_available():
            linhas.append(f"CUDA ativo em: {torch.cuda.get_device_name(0)}")
        else:
            linhas.append(
                "CUDA ativo em: NAO — o Whisper vai rodar na CPU (bem mais lento)"
            )
    except Exception as erro:
        linhas.append(f"PyTorch: ausente ou com erro ({erro})")
    return linhas


def secao_ffmpeg() -> list:
    linhas = ["", "== FFMPEG =="]
    caminho = shutil.which("ffmpeg")
    if not caminho:
        pacote = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "ffmpeg.exe")
        caminho = pacote if os.path.isfile(pacote) else None
    if not caminho:
        linhas.append("ffmpeg: NAO ENCONTRADO")
        return linhas

    linhas.append(f"ffmpeg: {caminho}")
    versao = _rodar([caminho, "-version"]).splitlines()
    if versao:
        linhas.append(versao[0])
    encoders = _rodar([caminho, "-hide_banner", "-encoders"])
    for nome in ("h264_nvenc", "hevc_nvenc", "libx264"):
        linhas.append(f"{nome}: {'disponivel' if nome in encoders else 'ausente'}")
    return linhas


def secao_pacotes() -> list:
    linhas = ["", "== PACOTES =="]
    linhas.append(f"Python: {sys.version.split()[0]}")
    import importlib.metadata as md

    for nome in (
        "gradio", "opencv-python", "mediapipe", "openai-whisper",
        "faster-whisper", "numpy", "pywebview", "scenedetect", "anthropic",
    ):
        try:
            linhas.append(f"{nome}: {md.version(nome)}")
        except Exception:
            linhas.append(f"{nome}: ausente")
    linhas.append(
        "ANTHROPIC_API_KEY: "
        + ("configurada" if os.environ.get("ANTHROPIC_API_KEY") else "ausente (modo offline)")
    )
    return linhas


_PADRAO_TEMPOS = re.compile(
    r"Tempos: corte (?P<corte>[^|]+)\|\s*falante (?P<falante>[^|]+)\|"
    r"\s*enquadramento (?P<enquadramento>.+)$"
)


def _segundos(texto: str) -> float:
    """Converte '3min 45s' / '17s' / '1h 02min' em segundos."""
    texto = texto.strip()
    total = 0.0
    for valor, unidade in re.findall(r"(\d+(?:[.,]\d+)?)\s*(h|min|s)", texto):
        numero = float(valor.replace(",", "."))
        total += numero * {"h": 3600, "min": 60, "s": 1}[unidade]
    return total


def secao_desempenho(pasta_clipes: str = None) -> list:
    """Le os logs de processamento e resume os tempos por etapa."""
    linhas = ["", "== DESEMPENHO MEDIDO =="]
    if pasta_clipes is None:
        pasta_clipes = os.path.join(os.path.expanduser("~"), "Desktop", "viral-clipes")
    if not os.path.isdir(pasta_clipes):
        linhas.append(f"Nenhum trabalho encontrado em {pasta_clipes}")
        return linhas

    logs = glob.glob(os.path.join(pasta_clipes, "*", "viral_cutter_*.log"))
    if not logs:
        linhas.append("Nenhum log de processamento ainda. Processe um video primeiro.")
        return linhas

    for caminho in sorted(logs)[-3:]:
        corte, falante, enquadra = [], [], []
        try:
            conteudo = io.open(caminho, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for linha in conteudo.splitlines():
            achou = _PADRAO_TEMPOS.search(linha)
            if achou:
                corte.append(_segundos(achou.group("corte")))
                falante.append(_segundos(achou.group("falante")))
                enquadra.append(_segundos(achou.group("enquadramento")))
        if not corte:
            continue
        pasta = os.path.basename(os.path.dirname(caminho))
        total = sum(corte) + sum(falante) + sum(enquadra)
        linhas.append("")
        linhas.append(f"Trabalho: {pasta[:60]}")
        linhas.append(f"  Clipes medidos: {len(corte)}")
        linhas.append(f"  Media por clipe: corte {sum(corte)/len(corte):.1f}s | "
                      f"falante {sum(falante)/len(falante):.1f}s | "
                      f"enquadramento {sum(enquadra)/len(enquadra):.1f}s")
        linhas.append(f"  Tempo total das etapas: {total/60:.1f} min")
        revisar = conteudo.count("REVISAR enquadramento")
        linhas.append(f"  Clipes marcados para revisar: {revisar}")
    return linhas


def montar_relatorio() -> str:
    linhas = [
        "RELATORIO DE AMBIENTE — VIRAL CUTTER CLASSIC",
        f"Gerado em: {datetime.now():%d/%m/%Y %H:%M}",
        "",
    ]
    linhas += secao_sistema()
    linhas += secao_gpu()
    linhas += secao_ffmpeg()
    linhas += secao_pacotes()
    linhas += secao_desempenho()
    linhas.append("")
    linhas.append("Envie este arquivo junto com o relato do problema ou do teste.")
    return "\n".join(linhas)


if __name__ == "__main__":
    texto = montar_relatorio()
    if len(sys.argv) > 1:
        with io.open(sys.argv[1], "w", encoding="utf-8") as arquivo:
            arquivo.write(texto)
        print(f"Relatorio salvo em: {os.path.abspath(sys.argv[1])}")
    else:
        print(texto)
