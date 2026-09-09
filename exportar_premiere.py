"""
exportar_premiere.py
--------------------
Exporta os cortes como um projeto do Premiere, em vez de queimar o
enquadramento no vídeo.

Por que existe: o enquadramento automático acerta a maior parte, mas quando
erra não há como corrigir sem reprocessar. Aqui os cortes vão para uma
sequência 9:16 com o material ORIGINAL 16:9 dentro — o enquadramento vira
Position/Scale no Premiere, que se ajusta arrastando.

Duas consequências práticas:

- Não corta nem recodifica nada. O XML aponta para o arquivo original com
  marcações de entrada e saída, então exportar é instantâneo e você reenquadra
  com os 4K inteiros disponíveis, sem perda de geração.
- Um clipe 4K numa sequência 1080x1920 em escala 100% já É um recorte 9:16 em
  resolução nativa, centrado. O ajuste é só arrastar na horizontal.

Formato: Final Cut Pro XML (XMEML v5), que é o caminho de interoperabilidade
que o Premiere importa há anos — o .prproj é fechado e frágil de gerar.
"""

import os
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom

SAIDA_LARGURA = 1080
SAIDA_ALTURA = 1920


def _url_de_arquivo(caminho: str) -> str:
    """Caminho do Windows no formato que o Premiere espera no pathurl."""
    absoluto = os.path.abspath(caminho).replace("\\", "/")
    from urllib.parse import quote

    return "file://localhost/" + quote(absoluto, safe="/:")


def _limpar_nome(texto: str, limite: int = 48) -> str:
    limpo = re.sub(r"[^\w\s-]", "", str(texto or "")).strip()
    limpo = re.sub(r"\s+", "_", limpo)
    return limpo[:limite] or "clipe"


def _taxa(elemento, timebase: int, ntsc: bool):
    rate = ET.SubElement(elemento, "rate")
    ET.SubElement(rate, "timebase").text = str(timebase)
    ET.SubElement(rate, "ntsc").text = "TRUE" if ntsc else "FALSE"


def _descricao_do_arquivo(pai, id_arquivo: str, caminho: str, largura: int,
                          altura: int, total_frames: int, timebase: int,
                          ntsc: bool, canais: int, completo: bool):
    """O <file> só é descrito por inteiro na primeira vez; depois vale o id.

    Repetir a descrição em 50 clipes faz o Premiere tratar como 50 mídias
    diferentes e a janela de projeto vira uma lista ilegível.
    """
    arquivo = ET.SubElement(pai, "file", {"id": id_arquivo})
    if not completo:
        return arquivo

    ET.SubElement(arquivo, "name").text = os.path.basename(caminho)
    ET.SubElement(arquivo, "pathurl").text = _url_de_arquivo(caminho)
    _taxa(arquivo, timebase, ntsc)
    ET.SubElement(arquivo, "duration").text = str(total_frames)
    midia = ET.SubElement(arquivo, "media")

    video = ET.SubElement(midia, "video")
    amostra = ET.SubElement(video, "samplecharacteristics")
    _taxa(amostra, timebase, ntsc)
    ET.SubElement(amostra, "width").text = str(largura)
    ET.SubElement(amostra, "height").text = str(altura)

    audio = ET.SubElement(midia, "audio")
    ET.SubElement(audio, "channelcount").text = str(canais)
    return arquivo


def gerar_xml(caminho_video: str, segmentos: list, caminho_saida: str,
              fps: float = 23.976, largura_fonte: int = 3840,
              altura_fonte: int = 2160, total_frames_fonte: int = 0,
              canais_audio: int = 2, nome_sequencia: str = "Viral Cutter 9x16") -> str:
    """Escreve o XMEML com uma sequência 9:16 e um clipe por segmento.

    Os clipes entram em sequência na timeline, na ordem dos segmentos, cada um
    com o nome do corte — para dar para achar pelo título na janela de projeto.
    """
    ntsc = abs(fps - round(fps)) > 0.001
    timebase = int(round(fps))
    total_frames_fonte = total_frames_fonte or int(round(fps * 3600))

    raiz = ET.Element("xmeml", {"version": "5"})
    sequencia = ET.SubElement(raiz, "sequence", {"id": "sequencia-viralcutter"})
    ET.SubElement(sequencia, "name").text = nome_sequencia
    _taxa(sequencia, timebase, ntsc)

    midia = ET.SubElement(sequencia, "media")
    video = ET.SubElement(midia, "video")
    formato = ET.SubElement(video, "format")
    amostra = ET.SubElement(formato, "samplecharacteristics")
    _taxa(amostra, timebase, ntsc)
    ET.SubElement(amostra, "width").text = str(SAIDA_LARGURA)
    ET.SubElement(amostra, "height").text = str(SAIDA_ALTURA)
    trilha_video = ET.SubElement(video, "track")

    audio = ET.SubElement(midia, "audio")
    trilha_audio = ET.SubElement(audio, "track")

    posicao = 0
    primeiro = True
    for indice, seg in enumerate(segmentos, start=1):
        inicio_s = float(seg.get("inicio", 0.0))
        fim_s = float(seg.get("fim", 0.0))
        if fim_s <= inicio_s:
            continue

        frame_ini = int(round(inicio_s * fps))
        frame_fim = int(round(fim_s * fps))
        duracao = frame_fim - frame_ini
        if duracao <= 0:
            continue

        nome = f"{indice:02d}_{_limpar_nome(seg.get('titulo'))}"

        item = ET.SubElement(trilha_video, "clipitem", {"id": f"video-{indice}"})
        ET.SubElement(item, "name").text = nome
        ET.SubElement(item, "enabled").text = "TRUE"
        ET.SubElement(item, "duration").text = str(duracao)
        _taxa(item, timebase, ntsc)
        ET.SubElement(item, "start").text = str(posicao)
        ET.SubElement(item, "end").text = str(posicao + duracao)
        ET.SubElement(item, "in").text = str(frame_ini)
        ET.SubElement(item, "out").text = str(frame_fim)
        _descricao_do_arquivo(item, "fonte-1", caminho_video, largura_fonte,
                              altura_fonte, total_frames_fonte, timebase, ntsc,
                              canais_audio, completo=primeiro)
        primeiro = False

        item_audio = ET.SubElement(trilha_audio, "clipitem", {"id": f"audio-{indice}"})
        ET.SubElement(item_audio, "name").text = nome
        ET.SubElement(item_audio, "enabled").text = "TRUE"
        ET.SubElement(item_audio, "duration").text = str(duracao)
        _taxa(item_audio, timebase, ntsc)
        ET.SubElement(item_audio, "start").text = str(posicao)
        ET.SubElement(item_audio, "end").text = str(posicao + duracao)
        ET.SubElement(item_audio, "in").text = str(frame_ini)
        ET.SubElement(item_audio, "out").text = str(frame_fim)
        ET.SubElement(item_audio, "file", {"id": "fonte-1"})
        origem = ET.SubElement(item_audio, "sourcetrack")
        ET.SubElement(origem, "mediatype").text = "audio"
        ET.SubElement(origem, "trackindex").text = "1"

        posicao += duracao

    ET.SubElement(sequencia, "duration").text = str(posicao)

    bruto = ET.tostring(raiz, encoding="utf-8")
    bonito = minidom.parseString(bruto).toprettyxml(indent="  ", encoding="UTF-8")
    # O Premiere quer o DOCTYPE; o ElementTree nao escreve isso sozinho.
    texto = bonito.decode("utf-8").replace(
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>',
        1,
    )
    with open(caminho_saida, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto)
    return caminho_saida


# ── Enquadramento levado para o Premiere ──────────────────────────────────────
# O crop calculado pelo programa vira Posicao/Escala no Movimento do clipe.
# A conversao e direta, mas a UNIDADE do <center> no XMEML e ambigua entre
# implementacoes: aqui vale "fracao da METADE do quadro". Se a imagem sair
# deslocada pela metade ou pelo dobro, e este divisor.
DIVISOR_CENTRO = 2.0


def _motion_do_crop(crop, largura_fonte: int, altura_fonte: int):
    """Converte (x, y, w, h) da fonte em escala % e centro normalizado.

    Escala: quanto ampliar para o recorte preencher a largura da sequencia.
    Centro: para onde empurrar a imagem, ja na escala aplicada, de modo que o
    recorte fique no meio do quadro.
    """
    x, y, w, h = crop
    if w <= 0 or h <= 0:
        return None
    fator = SAIDA_LARGURA / float(w)
    centro_recorte_x = x + w / 2.0
    centro_recorte_y = y + h / 2.0
    desloc_x = -(centro_recorte_x - largura_fonte / 2.0) * fator
    desloc_y = -(centro_recorte_y - altura_fonte / 2.0) * fator
    return {
        "escala": fator * 100.0,
        "horiz": desloc_x / (SAIDA_LARGURA / DIVISOR_CENTRO),
        "vert": desloc_y / (SAIDA_ALTURA / DIVISOR_CENTRO),
    }


def _filtro_movimento(pai, motion: dict):
    filtro = ET.SubElement(pai, "filter")
    efeito = ET.SubElement(filtro, "effect")
    ET.SubElement(efeito, "name").text = "Basic Motion"
    ET.SubElement(efeito, "effectid").text = "basic"
    ET.SubElement(efeito, "effectcategory").text = "motion"
    ET.SubElement(efeito, "effecttype").text = "motion"
    ET.SubElement(efeito, "mediatype").text = "video"

    escala = ET.SubElement(efeito, "parameter")
    ET.SubElement(escala, "parameterid").text = "scale"
    ET.SubElement(escala, "name").text = "Scale"
    ET.SubElement(escala, "valuemin").text = "0"
    ET.SubElement(escala, "valuemax").text = "1000"
    ET.SubElement(escala, "value").text = f"{motion['escala']:.3f}"

    centro = ET.SubElement(efeito, "parameter")
    ET.SubElement(centro, "parameterid").text = "center"
    ET.SubElement(centro, "name").text = "Center"
    valor = ET.SubElement(centro, "value")
    ET.SubElement(valor, "horiz").text = f"{motion['horiz']:.5f}"
    ET.SubElement(valor, "vert").text = f"{motion['vert']:.5f}"

    rot = ET.SubElement(efeito, "parameter")
    ET.SubElement(rot, "parameterid").text = "rotation"
    ET.SubElement(rot, "name").text = "Rotation"
    ET.SubElement(rot, "value").text = "0"


def gerar_xml_por_corte(caminho_video: str, cortes: list, caminho_saida: str,
                        fps: float, largura_fonte: int, altura_fonte: int,
                        total_frames_fonte: int, canais_audio: int = 2,
                        nome_pasta: str = "Cortes 9x16") -> str:
    """Uma SEQUENCIA por corte, dentro de uma pasta na janela de projeto.

    Cada corte e uma entrega separada — reenquadrar e exportar um a um e o
    fluxo real de trabalho. Numa timeline unica de 42 minutos isso nao existe.

    Cada ``corte`` e um dict com ``inicio``, ``fim``, ``titulo`` e, quando o
    enquadramento foi calculado, ``shots``: uma lista de
    ``{"inicio", "fim", "crop"}`` em segundos e pixels da fonte. O clipe e
    partido nos limites de shot e cada pedaco recebe o seu Movimento, para o
    rosto de quem fala ficar enquadrado sem voce precisar procurar.
    """
    ntsc = abs(fps - round(fps)) > 0.001
    timebase = int(round(fps))

    raiz = ET.Element("xmeml", {"version": "5"})
    pasta = ET.SubElement(raiz, "bin")
    ET.SubElement(pasta, "name").text = nome_pasta
    filhos = ET.SubElement(pasta, "children")

    primeiro_arquivo = True
    for indice, corte in enumerate(cortes, start=1):
        ini_s = float(corte.get("inicio", 0.0))
        fim_s = float(corte.get("fim", 0.0))
        if fim_s <= ini_s:
            continue
        nome = f"{indice:02d}_{_limpar_nome(corte.get('titulo'))}"
        frame_ini = int(round(ini_s * fps))
        total = int(round(fim_s * fps)) - frame_ini
        if total <= 0:
            continue

        sequencia = ET.SubElement(filhos, "sequence", {"id": f"seq-{indice}"})
        ET.SubElement(sequencia, "name").text = nome
        ET.SubElement(sequencia, "duration").text = str(total)
        _taxa(sequencia, timebase, ntsc)

        midia = ET.SubElement(sequencia, "media")
        video = ET.SubElement(midia, "video")
        formato = ET.SubElement(video, "format")
        amostra = ET.SubElement(formato, "samplecharacteristics")
        _taxa(amostra, timebase, ntsc)
        ET.SubElement(amostra, "width").text = str(SAIDA_LARGURA)
        ET.SubElement(amostra, "height").text = str(SAIDA_ALTURA)
        trilha_v = ET.SubElement(video, "track")
        audio = ET.SubElement(midia, "audio")
        trilha_a = ET.SubElement(audio, "track")

        # Sem shots calculados, o corte inteiro e um pedaco so: escala 100%,
        # que ja e um recorte 9:16 nativo e centrado do 4K.
        shots = corte.get("shots") or [{"inicio": 0.0, "fim": fim_s - ini_s, "crop": None}]

        for n, shot in enumerate(shots):
            desloc_ini = int(round(float(shot.get("inicio", 0.0)) * fps))
            desloc_fim = int(round(float(shot.get("fim", 0.0)) * fps))
            desloc_fim = min(desloc_fim, total)
            if desloc_fim <= desloc_ini:
                continue

            item = ET.SubElement(trilha_v, "clipitem", {"id": f"v-{indice}-{n}"})
            ET.SubElement(item, "name").text = nome
            ET.SubElement(item, "enabled").text = "TRUE"
            ET.SubElement(item, "duration").text = str(desloc_fim - desloc_ini)
            _taxa(item, timebase, ntsc)
            ET.SubElement(item, "start").text = str(desloc_ini)
            ET.SubElement(item, "end").text = str(desloc_fim)
            ET.SubElement(item, "in").text = str(frame_ini + desloc_ini)
            ET.SubElement(item, "out").text = str(frame_ini + desloc_fim)
            _descricao_do_arquivo(item, "fonte-1", caminho_video, largura_fonte,
                                  altura_fonte, total_frames_fonte, timebase,
                                  ntsc, canais_audio, completo=primeiro_arquivo)
            primeiro_arquivo = False
            if shot.get("crop"):
                motion = _motion_do_crop(shot["crop"], largura_fonte, altura_fonte)
                if motion:
                    _filtro_movimento(item, motion)

        item_a = ET.SubElement(trilha_a, "clipitem", {"id": f"a-{indice}"})
        ET.SubElement(item_a, "name").text = nome
        ET.SubElement(item_a, "enabled").text = "TRUE"
        ET.SubElement(item_a, "duration").text = str(total)
        _taxa(item_a, timebase, ntsc)
        ET.SubElement(item_a, "start").text = "0"
        ET.SubElement(item_a, "end").text = str(total)
        ET.SubElement(item_a, "in").text = str(frame_ini)
        ET.SubElement(item_a, "out").text = str(frame_ini + total)
        ET.SubElement(item_a, "file", {"id": "fonte-1"})
        origem = ET.SubElement(item_a, "sourcetrack")
        ET.SubElement(origem, "mediatype").text = "audio"
        ET.SubElement(origem, "trackindex").text = "1"

    bruto = ET.tostring(raiz, encoding="utf-8")
    bonito = minidom.parseString(bruto).toprettyxml(indent="  ", encoding="UTF-8")
    texto = bonito.decode("utf-8").replace(
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>',
        1,
    )
    with open(caminho_saida, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto)
    return caminho_saida


def _specs_do_video(caminho: str) -> dict:
    """Lê fps, resolução e nº de frames com o ffprobe do próprio projeto."""
    import json
    import subprocess
    from ffmpeg_utils import localizar_ffprobe

    def _rodar(args):
        return subprocess.run(args, capture_output=True, text=True,
                              encoding="utf-8", errors="replace").stdout

    saida = _rodar([
        localizar_ffprobe(), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
        "-of", "json", caminho,
    ])
    fluxo = (json.loads(saida or "{}").get("streams") or [{}])[0]
    num, _, den = (fluxo.get("r_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1)

    saida_audio = _rodar([
        localizar_ffprobe(), "-v", "error",
        "-select_streams", "a:0", "-show_entries", "stream=channels",
        "-of", "json", caminho,
    ])
    canais = (json.loads(saida_audio or "{}").get("streams") or [{}])[0].get("channels") or 2

    return {
        "fps": fps,
        "largura": int(fluxo.get("width") or 1920),
        "altura": int(fluxo.get("height") or 1080),
        "frames": int(fluxo.get("nb_frames") or 0) or int(round(fps * 3600)),
        "canais": int(canais),
    }


def exportar(caminho_video: str, caminho_saida: str = None) -> str:
    """Exporta o XML usando a análise já salva para este vídeo.

    Reaproveita os segmentos do estado persistido — a mesma análise que gerou
    os clipes. Não refaz transcrição nem detecção.
    """
    from checkpoint import carregar_estado_analise
    from runtime import pasta_dados

    pasta_estado = os.path.join(pasta_dados(), "estado")
    dados = carregar_estado_analise(pasta_estado, caminho_video) or {}
    segmentos = dados.get("segmentos") or []
    if not segmentos:
        raise SystemExit(
            "Nenhuma análise salva para este vídeo. Rode 'TRANSCREVER E ANALISAR' "
            "no aplicativo antes de exportar."
        )

    specs = _specs_do_video(caminho_video)
    if not caminho_saida:
        base = os.path.splitext(os.path.basename(caminho_video))[0]
        pasta = os.path.join(os.path.expanduser("~"), "Desktop")
        caminho_saida = os.path.join(pasta, f"{_limpar_nome(base, 60)}_9x16.xml")

    gerar_xml(
        caminho_video, segmentos, caminho_saida,
        fps=specs["fps"], largura_fonte=specs["largura"],
        altura_fonte=specs["altura"], total_frames_fonte=specs["frames"],
        canais_audio=specs["canais"],
        nome_sequencia=f"{os.path.splitext(os.path.basename(caminho_video))[0][:40]} 9x16",
    )
    print(f"{len(segmentos)} cortes exportados")
    print(f"Sequencia {SAIDA_LARGURA}x{SAIDA_ALTURA} a {specs['fps']:.3f} fps")
    print(f"Arquivo: {caminho_saida}")
    print("No Premiere: Arquivo > Importar > selecione este XML.")
    return caminho_saida


if __name__ == "__main__":
    import sys

    from runtime import configurar_ambiente, configurar_console_utf8, suprimir_janelas_de_console

    configurar_console_utf8()
    configurar_ambiente()
    suprimir_janelas_de_console()

    if len(sys.argv) < 2:
        print("Uso: exportar_premiere.py <video> [saida.xml]")
        raise SystemExit(2)
    exportar(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
