"""
gancho.py
---------
Nota de viralidade em 4 dimensoes e titulo-gancho sobreposto ao clipe.

A analise com IA devolve, para cada corte:
  - "notas": {"gancho", "engajamento", "valor", "compartilhamento"} de 1 a 10
  - "titulo_gancho": frase curta para os primeiros segundos do clipe

Este modulo transforma isso em:
  - score_viral composto (ponderado) e ordem dos cortes do mais forte ao mais fraco
  - um arquivo .ass com o titulo no topo do video por alguns segundos

Funcoes puras, sem dependencias pesadas: testaveis sem GPU, sem FFmpeg e sem API.
"""

import re

DIMENSOES = ("gancho", "engajamento", "valor", "compartilhamento")

# O gancho pesa mais: sem ele ninguem fica para ver o resto do clipe.
PESOS = {
    "gancho": 0.35,
    "engajamento": 0.25,
    "valor": 0.20,
    "compartilhamento": 0.20,
}

MAX_PALAVRAS_TITULO = 7
MAX_CARACTERES_TITULO = 42
DURACAO_TITULO = 3.0


def normalizar_notas(notas) -> dict:
    """Devolve as 4 notas entre 1 e 10, ou None se faltar alguma ou vier invalida."""
    if not isinstance(notas, dict):
        return None
    saida = {}
    for dim in DIMENSOES:
        try:
            valor = float(notas.get(dim))
        except (TypeError, ValueError):
            return None
        if valor != valor:  # NaN
            return None
        saida[dim] = max(1.0, min(10.0, valor))
    return saida


def nota_composta(notas: dict) -> float:
    """Media ponderada das 4 notas, com uma casa decimal."""
    # +1e-9 evita que 8.15 vire 8.1 pelo arredondamento binario do float.
    return round(sum(PESOS[d] * notas[d] for d in DIMENSOES) + 1e-9, 1)


def limpar_titulo_gancho(texto) -> str:
    """Titulo curto, sem aspas nem ponto final, cortado em palavras inteiras."""
    if not isinstance(texto, str):
        return ""
    t = re.sub(r"\s+", " ", texto).strip()
    t = t.strip("\"'“”‘’` ")
    t = t.rstrip(".")
    if not t:
        return ""
    palavras = t.split(" ")[:MAX_PALAVRAS_TITULO]
    while len(" ".join(palavras)) > MAX_CARACTERES_TITULO and len(palavras) > 1:
        palavras = palavras[:-1]
    return " ".join(palavras)[:MAX_CARACTERES_TITULO].strip()


def aplicar_notas(segmentos: list) -> list:
    """
    Calcula o score composto onde a IA mandou as 4 notas.

    Segmentos sem notas (modo offline, resposta antiga) ficam como estao.
    O score original da IA e guardado em 'score_viral_ia' para comparacao.
    """
    saida = []
    for seg in segmentos or []:
        copia = dict(seg)
        notas = normalizar_notas(seg.get("notas"))
        if notas:
            composta = nota_composta(notas)
            copia["notas"] = notas
            copia["nota_composta"] = composta
            if "score_viral" in seg:
                copia["score_viral_ia"] = seg.get("score_viral")
            copia["score_viral"] = int(round(composta))
        else:
            copia.pop("notas", None)
        titulo = limpar_titulo_gancho(seg.get("titulo_gancho"))
        if titulo:
            copia["titulo_gancho"] = titulo
        else:
            copia.pop("titulo_gancho", None)
        saida.append(copia)
    return saida


def ordenar_por_viralidade(segmentos: list) -> list:
    """Do corte mais forte ao mais fraco; empate desfeito pela ordem no video."""
    def chave(seg):
        score = seg.get("score_viral", 0) or 0
        composta = seg.get("nota_composta", score) or 0
        try:
            inicio = float(seg.get("inicio", 0) or 0)
        except (TypeError, ValueError):
            inicio = 0.0
        return (-float(score), -float(composta), inicio)
    return sorted(segmentos or [], key=chave)


def _quebrar_em_linhas(texto: str, max_por_linha: int = 20) -> list:
    """Ate 2 linhas equilibradas; titulo curto fica numa linha so."""
    if len(texto) <= max_por_linha:
        return [texto]
    palavras = texto.split(" ")
    melhor = [texto]
    menor_diferenca = None
    for corte in range(1, len(palavras)):
        a = " ".join(palavras[:corte])
        b = " ".join(palavras[corte:])
        diferenca = abs(len(a) - len(b))
        if menor_diferenca is None or diferenca < menor_diferenca:
            menor_diferenca = diferenca
            melhor = [a, b]
    return melhor


def _escapar_ass(texto: str) -> str:
    # Chaves abrem tags de override no ASS; barra invertida inicia comandos.
    return texto.replace("\\", "/").replace("{", "(").replace("}", ")")


def gerar_ass_titulo_gancho(
    texto: str,
    caminho_ass: str,
    duracao: float = DURACAO_TITULO,
    largura: int = 1080,
    altura: int = 1920,
) -> bool:
    """
    Grava um .ass com o titulo no topo do video, de 0 a `duracao` segundos.

    Fica abaixo da faixa de interface do Reels/TikTok (topo ~10% da tela) e
    longe da legenda principal, que fica na parte de baixo.
    """
    titulo = limpar_titulo_gancho(texto)
    if not titulo:
        return False
    linhas = _quebrar_em_linhas(titulo.upper())
    corpo = "\\N".join(_escapar_ass(l) for l in linhas)
    margem_topo = int(altura * 0.13)
    fim = max(0.5, float(duracao))
    fim_txt = f"0:00:{fim:05.2f}"

    conteudo = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {largura}\n"
        f"PlayResY: {altura}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        # BorderStyle 3 = caixa opaca atras do texto (cor da caixa = OutlineColour).
        "Style: Gancho,Arial,76,&H00FFFFFF,&H00FFFFFF,&H1A000000,&H00000000,"
        f"-1,0,0,0,100,100,1,0,3,22,0,8,80,80,{margem_topo},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 5,0:00:00.00,{fim_txt},Gancho,,0,0,0,,{{\\fad(120,250)}}{corpo}\n"
    )
    try:
        with open(caminho_ass, "w", encoding="utf-8-sig") as f:
            f.write(conteudo)
        return True
    except OSError:
        return False
