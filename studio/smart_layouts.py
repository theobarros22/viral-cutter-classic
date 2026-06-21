"""Geometria dos Smart Layouts verticais do Viralume."""


FORMAT_WIDTH = 1080
FORMAT_HEIGHT = 1920

LAYOUTS = {
    "solo": [(0.0, 0.0, 1.0, 1.0)],
    "duo-horizontal": [(0.0, 0.0, 1.0, 0.5), (0.0, 0.5, 1.0, 0.5)],
    "duo-vertical": [(0.0, 0.0, 0.5, 1.0), (0.5, 0.0, 0.5, 1.0)],
    "hero-top": [(0.0, 0.0, 1.0, 0.34), (0.0, 0.34, 1.0, 0.66)],
    "hero-bottom": [(0.0, 0.0, 1.0, 0.66), (0.0, 0.66, 1.0, 0.34)],
    "trio-stack": [
        (0.0, 0.0, 1.0, 0.333),
        (0.0, 0.333, 1.0, 0.334),
        (0.0, 0.667, 1.0, 0.333),
    ],
    "trio-hero": [(0.0, 0.0, 1.0, 0.66), (0.0, 0.66, 0.5, 0.34), (0.5, 0.66, 0.5, 0.34)],
    "trio-side": [(0.0, 0.0, 0.66, 1.0), (0.66, 0.0, 0.34, 0.5), (0.66, 0.5, 0.34, 0.5)],
    "pip": [(0.0, 0.0, 1.0, 1.0), (0.62, 0.06, 0.30, 0.22)],
    "quad": [(0.0, 0.0, 0.5, 0.5), (0.5, 0.0, 0.5, 0.5), (0.0, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5)],
    "vertical-hero": [(0.0, 0.0, 0.66, 1.0), (0.66, 0.18, 0.34, 0.64)],
}


def validar_layout(nome):
    return nome if nome in LAYOUTS else "solo"


def plano_layout(nome, fontes=None):
    """Converte um preset em regiões de pixels para composição FFmpeg."""
    nome = validar_layout(nome)
    fontes = list(fontes or [])
    regioes = []
    for indice, (x, y, largura, altura) in enumerate(LAYOUTS[nome]):
        regioes.append({
            "source": fontes[indice] if indice < len(fontes) else indice,
            "x": round(x * FORMAT_WIDTH),
            "y": round(y * FORMAT_HEIGHT),
            "width": round(largura * FORMAT_WIDTH),
            "height": round(altura * FORMAT_HEIGHT),
        })
    return {
        "name": nome,
        "format": "9:16",
        "width": FORMAT_WIDTH,
        "height": FORMAT_HEIGHT,
        "regions": regioes,
    }


def filtro_regiao(indice_entrada, regiao, rotulo):
    """Escala e recorta uma entrada para preencher uma região vertical."""
    largura = int(regiao["width"])
    altura = int(regiao["height"])
    return (
        f"[{int(indice_entrada)}:v]"
        f"scale={largura}:{altura}:force_original_aspect_ratio=increase,"
        f"crop={largura}:{altura}[{rotulo}]"
    )
