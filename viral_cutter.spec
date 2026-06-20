# -*- mode: python ; coding: utf-8 -*-
# viral_cutter.spec — versao corrigida (coleta dados de todos os pacotes)
# Resolve o erro "FileNotFoundError safehttpx/version.txt" e similares.

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
binaries = []
if os.path.exists("face_detector.tflite"):
    datas.append(("face_detector.tflite", "."))
for nome in ("ffmpeg.exe", "ffprobe.exe"):
    caminho = os.path.join("tools", nome)
    if os.path.exists(caminho):
        binaries.append((caminho, "tools"))
pacotes = [
    "gradio", "gradio_client", "fastapi", "anthropic", "huggingface_hub",
    "certifi", "orjson", "typer", "pydantic", "tqdm", "safehttpx", "httpx",
    "httpcore", "anyio", "starlette", "uvicorn", "python_multipart", "h11",
    "rich", "click", "tomlkit", "packaging", "filelock", "sniffio", "groovy",
    "whisper", "mediapipe", "cv2", "matplotlib", "contourpy", "kiwisolver",
]
for p in pacotes:
    try:
        datas += collect_data_files(p)
    except Exception:
        pass

hidden = []
for m in ["gradio", "gradio_client", "whisper", "mediapipe", "anthropic", "uvicorn", "starlette"]:
    try:
        hidden += collect_submodules(m)
    except Exception:
        pass
hidden += [
    "cv2", "pydub", "torch", "fastapi", "aiofiles", "anyio",
    "httpx", "httpcore", "safehttpx", "certifi", "orjson",
    "websockets", "python_multipart", "h11", "sniffio",
    "huggingface_hub", "tokenizers", "packaging", "tqdm",
    "filelock", "fsspec", "requests", "rich", "typer", "click",
    "pydantic", "pydantic_core", "tomlkit", "groovy",
    "numpy", "PIL", "scipy", "matplotlib", "ffmpeg_utils", "runtime", "checkpoint",
]

block_cipher = None
a = Analysis(
    ["interface.py"],
    pathex=[os.path.abspath(".")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "IPython", "jupyter", "notebook"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    # CORRECAO CRITICA: o Gradio le os proprios arquivos .py em tempo de
    # execucao (component_meta.py). Sem isso o exe quebra com
    # "FileNotFoundError: gradio/blocks_events.py".
    module_collection_mode={
        "gradio": "py",
        "gradio_client": "py",
    },
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ViralCutter",
    debug=False, strip=False, upx=False, console=False,
    version="version_info.txt",
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="ViralCutter",
)
