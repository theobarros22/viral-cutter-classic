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
