"""Helpers centralizados para executar FFmpeg com fallback seguro."""

import subprocess


_NVENC_DISPONIVEL = None


def nvenc_disponivel() -> bool:
    global _NVENC_DISPONIVEL
    if _NVENC_DISPONIVEL is not None:
        return _NVENC_DISPONIVEL

    try:
        resultado = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=size=16x16:rate=1",
                "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        _NVENC_DISPONIVEL = resultado.returncode == 0
    except (OSError, subprocess.SubprocessError):
        _NVENC_DISPONIVEL = False
    return _NVENC_DISPONIVEL


def argumentos_encoder(temporario: bool = False) -> list:
    """Usa RTX quando disponível; mantém libx264 como fallback universal."""
    if nvenc_disponivel():
        qualidade = "23" if temporario else "19"
        preset = "p1" if temporario else "p4"
        return ["-c:v", "h264_nvenc", "-preset", preset, "-cq", qualidade]

    preset = "ultrafast" if temporario else "fast"
    crf = "22" if temporario else "18"
    return ["-c:v", "libx264", "-preset", preset, "-crf", crf]
