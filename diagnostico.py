"""Checagem rápida do ambiente antes de abrir ou empacotar o Viral Cutter."""

import importlib.util
import importlib
import os
import shutil
import sys
from runtime import configurar_ambiente, pasta_dados


MODULOS = ("cv2", "mediapipe", "numpy", "torch", "whisper", "gradio", "anthropic", "pydub")


def executar_diagnostico() -> bool:
    configurar_ambiente()
    problemas = []
    avisos = []

    if sys.version_info[:2] != (3, 11):
        problemas.append(f"Python {sys.version.split()[0]} em uso; necessário Python 3.11.")

    for nome in MODULOS:
        if importlib.util.find_spec(nome) is None:
            problemas.append(f"Pacote ausente: {nome}")
            continue
        try:
            importlib.import_module(nome)
        except Exception as erro:
            problemas.append(f"Pacote não consegue iniciar: {nome} ({erro})")

    for programa in ("ffmpeg", "ffprobe"):
        if shutil.which(programa) is None:
            problemas.append(f"{programa}.exe não encontrado no PATH.")

    if importlib.util.find_spec("torch") is not None:
        try:
            import torch
            estado = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
            avisos.append(f"Processamento Whisper disponível em: {estado}")
        except Exception:
            pass

    if not os.path.exists("face_detector.tflite"):
        avisos.append("Modelo facial ausente; será baixado na primeira execução.")

    try:
        teste = os.path.join(pasta_dados(), "_teste_escrita.tmp")
        with open(teste, "w", encoding="utf-8") as arquivo:
            arquivo.write("ok")
        os.remove(teste)
    except OSError as erro:
        problemas.append(f"Sem permissão para gravar dados locais: {erro}")

    print("=== Diagnóstico Viral Cutter ===")
    for aviso in avisos:
        print(f"AVISO: {aviso}")
    for problema in problemas:
        print(f"ERRO: {problema}")

    if problemas:
        print(f"\nResultado: {len(problemas)} problema(s) precisam ser corrigidos.")
        return False

    print("\nResultado: ambiente pronto.")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if executar_diagnostico() else 1)
