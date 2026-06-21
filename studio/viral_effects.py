"""Filtros FFmpeg reutilizáveis para efeitos virais do Viralume."""

from pathlib import Path


def expressao_zoom(timestamps, intensidade=1.15, duracao=0.45):
    """Gera escala por eventos de punch-in, retornando 1 fora dos eventos."""
    intensidade = min(1.30, max(1.01, float(intensidade)))
    duracao = max(0.08, float(duracao))
    eventos = []
    for tempo in sorted({max(0.0, float(item)) for item in timestamps or []}):
        eventos.append(f"between(t,{tempo:.3f},{tempo + duracao:.3f})")
    if not eventos:
        return "1"
    condicao = "+".join(eventos)
    return f"if(gt({condicao},0),{intensidade:.3f},1)"


def filtro_zoom_dinamico(timestamps, largura=1080, altura=1920, intensidade=1.15):
    """Cria zoom seco centralizado compatível com uma composição vertical."""
    zoom = expressao_zoom(timestamps, intensidade)
    return (
        f"scale=w='iw*({zoom})':h='ih*({zoom})':eval=frame,"
        f"crop={int(largura)}:{int(altura)}:"
        f"(iw-{int(largura)})/2:(ih-{int(altura)})/2"
    )


def filtro_barra_progresso(duracao, cor="0xC63200", altura=10):
    """Barra inferior que cresce de acordo com o tempo do vídeo."""
    duracao = max(0.001, float(duracao))
    return (
        f"drawbox=x=0:y=ih-{int(altura)}:"
        f"w='iw*min(t/{duracao:.3f},1)':h={int(altura)}:"
        f"color={cor}:t=fill"
    )


def filtro_lut(caminho_lut):
    """Retorna filtro LUT3D somente para um arquivo .cube válido."""
    caminho = Path(caminho_lut)
    if caminho.suffix.lower() != ".cube":
        raise ValueError("A LUT precisa estar no formato .cube.")
    escapado = str(caminho).replace("\\", "/").replace(":", r"\:")
    return f"lut3d=file='{escapado}'"


def filtros_sfx(eventos):
    """Cria entradas de áudio atrasadas e prontas para amix."""
    filtros = []
    rotulos = ["[0:a]"]
    for indice, evento in enumerate(eventos or [], 1):
        tempo_ms = max(0, round(float(evento["tempo"]) * 1000))
        volume = min(2.0, max(0.0, float(evento.get("volume", 0.7))))
        filtros.append(
            f"[{indice}:a]volume={volume:.3f},"
            f"adelay={tempo_ms}|{tempo_ms}[sfx{indice}]"
        )
        rotulos.append(f"[sfx{indice}]")
    if not filtros:
        return [], None
    filtros.append(
        "".join(rotulos)
        + f"amix=inputs={len(rotulos)}:duration=first:normalize=0[aout]"
    )
    return filtros, "[aout]"
