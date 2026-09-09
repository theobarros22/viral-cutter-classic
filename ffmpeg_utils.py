"""Helpers centralizados para executar FFmpeg e FFprobe com fallback seguro."""

import os
import sys
import json
import shutil
import subprocess
from typing import Dict, Any, Optional


_NVENC_DISPONIVEL: Optional[bool] = None
_CAMINHO_FFMPEG: Optional[str] = None
_CAMINHO_FFPROBE: Optional[str] = None


def localizar_ffmpeg() -> str:
    """Localiza o executável FFmpeg no sistema, pasta empacotada ou pasta tools local."""
    global _CAMINHO_FFMPEG
    if _CAMINHO_FFMPEG and os.path.exists(_CAMINHO_FFMPEG):
        return _CAMINHO_FFMPEG

    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    candidatos = [
        os.path.join(base, "tools", "ffmpeg.exe"),
        os.path.join(base, "ffmpeg.exe"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "ffmpeg.exe"),
        shutil.which("ffmpeg"),
    ]

    for cand in candidatos:
        if cand and os.path.exists(cand):
            _CAMINHO_FFMPEG = cand
            return _CAMINHO_FFMPEG

    _CAMINHO_FFMPEG = "ffmpeg"
    return _CAMINHO_FFMPEG


def localizar_ffprobe() -> str:
    """Localiza o executável FFprobe no sistema, pasta empacotada ou pasta tools local."""
    global _CAMINHO_FFPROBE
    if _CAMINHO_FFPROBE and os.path.exists(_CAMINHO_FFPROBE):
        return _CAMINHO_FFPROBE

    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    candidatos = [
        os.path.join(base, "tools", "ffprobe.exe"),
        os.path.join(base, "ffprobe.exe"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "ffprobe.exe"),
        shutil.which("ffprobe"),
    ]

    for cand in candidatos:
        if cand and os.path.exists(cand):
            _CAMINHO_FFPROBE = cand
            return _CAMINHO_FFPROBE

    _CAMINHO_FFPROBE = "ffprobe"
    return _CAMINHO_FFPROBE


def obter_duracao(caminho: str) -> float:
    """Retorna a duração do arquivo em segundos usando ffprobe com fallback."""
    if not caminho or not os.path.exists(caminho):
        return 0.0

    ffprobe = localizar_ffprobe()
    cmd = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_format", caminho
    ]
    try:
        resultado = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
        )
        if resultado.returncode == 0 and resultado.stdout.strip():
            dados = json.loads(resultado.stdout)
            duracao = float(dados.get("format", {}).get("duration", 0))
            if duracao > 0:
                return duracao
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        pass

    # Fallback via stream de vídeo se show_format falhar
    cmd_stream = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "v:0", caminho
    ]
    try:
        resultado = subprocess.run(
            cmd_stream, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
        )
        if resultado.returncode == 0 and resultado.stdout.strip():
            dados = json.loads(resultado.stdout)
            streams = dados.get("streams", [])
            if streams:
                return float(streams[0].get("duration", 0))
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        pass

    return 0.0


def obter_info_video(caminho_video: str) -> Dict[str, Any]:
    """Retorna informações estruturadas de largura, altura, fps e duração do vídeo."""
    if not caminho_video or not os.path.exists(caminho_video):
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho_video}")

    ffprobe = localizar_ffprobe()
    cmd = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "v:0",
        "-show_format", caminho_video
    ]
    resultado = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20
    )
    if resultado.returncode != 0 or not resultado.stdout.strip():
        raise RuntimeError(f"FFprobe não conseguiu ler as informações do vídeo: {caminho_video}")

    dados = json.loads(resultado.stdout)
    streams = dados.get("streams", [])
    if not streams:
        raise RuntimeError(f"Nenhuma stream de vídeo encontrada em: {caminho_video}")

    stream = streams[0]
    fps_str = stream.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        den_i = int(den) if den.isdigit() else 1
        num_i = int(num) if num.isdigit() else 30
        fps = round(num_i / den_i, 2) if den_i else 30.0
    else:
        try:
            fps = float(fps_str)
        except ValueError:
            fps = 30.0

    duracao_str = stream.get("duration") or dados.get("format", {}).get("duration", 0)
    try:
        duracao = float(duracao_str)
    except ValueError:
        duracao = 0.0

    return {
        "largura": int(stream.get("width", 1920)),
        "altura": int(stream.get("height", 1080)),
        "fps": fps,
        "duracao": duracao,
        "codec": stream.get("codec_name", "h264"),
    }


def nvenc_disponivel() -> bool:
    """Verifica se a GPU NVIDIA com encoder NVENC está disponível e funcional."""
    global _NVENC_DISPONIVEL
    if _NVENC_DISPONIVEL is not None:
        return _NVENC_DISPONIVEL

    ffmpeg = localizar_ffmpeg()
    try:
        resultado = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=size=16x16:rate=1",
                "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        _NVENC_DISPONIVEL = (resultado.returncode == 0)
    except (OSError, subprocess.SubprocessError):
        _NVENC_DISPONIVEL = False
    return _NVENC_DISPONIVEL


def argumentos_encoder(temporario: bool = False, perfil: str = "equilibrado") -> list:
    """Usa RTX quando disponível com parâmetros otimizados; mantém libx264 como fallback universal."""
    if nvenc_disponivel():
        if temporario:
            return ["-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll", "-cq", "23"]
        if perfil == "rapido":
            return ["-c:v", "h264_nvenc", "-preset", "p2", "-cq", "22"]
        if perfil == "qualidade":
            return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "17", "-spatial-aq", "1", "-temporal-aq", "1"]
        # Padrão: equilibrado
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "19", "-spatial-aq", "1", "-temporal-aq", "1"]

    if temporario or perfil == "rapido":
        return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "22"]
    if perfil == "qualidade":
        return ["-c:v", "libx264", "-preset", "medium", "-crf", "16"]
    # Padrão: equilibrado
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]
