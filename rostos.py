"""
rostos.py
---------
Detecta rostos no vÃ­deo, extrai uma imagem de preview de cada pessoa
e permite que o usuÃ¡rio escolha quem priorizar no enquadramento.

Como funciona:
1. Analisa frames do vÃ­deo com MediaPipe
2. Agrupa rostos similares (mesma pessoa aparecendo em frames diferentes)
3. Extrai a melhor foto de cada pessoa detectada
4. Retorna lista de pessoas com preview e posiÃ§Ã£o mÃ©dia na tela
"""

import cv2
import numpy as np
import os
import base64
import json
import tempfile
import sys
import logging
from runtime import pasta_dados


LOGGER = logging.getLogger("ViralCutter.rostos")


class VideoIlegivelError(RuntimeError):
    """
    O vÃ­deo nÃ£o pÃ´de ser decodificado â€” nenhum quadro foi lido.

    Quase sempre significa que o upload ainda nÃ£o terminou (arquivos grandes
    levam minutos) ou que o arquivo estÃ¡ corrompido/incompleto. Ã‰ diferente de
    "li o vÃ­deo e nÃ£o achei rosto nenhum" â€” esse caso continua retornando [].
    """


MSG_VIDEO_ILEGIVEL = (
    "â³ NÃ£o consegui ler nenhum quadro do vÃ­deo. Isso quase sempre significa "
    "que o upload ainda NÃƒO terminou (arquivos grandes, de vÃ¡rios GB, levam "
    "minutos) ou que o arquivo estÃ¡ corrompido. Aguarde o upload chegar a 100% "
    "e clique em DETECTAR PESSOAS novamente."
)

# Abaixo disso, a diferenÃ§a de movimento entre os rostos Ã© ruÃ­do de
# compressÃ£o/iluminaÃ§Ã£o, nÃ£o fala real â€” comum quando um microfone de mesa
# cobre a boca e a regiÃ£o analisada mal muda de um frame pro outro.
LIMIAR_MOVIMENTO_LABIAL = 4.0
# Rosto e mais alto que largo; usado para estimar a caixa de quem o detector
# nao achou no frame, a partir da largura medida na etapa 1.
ALTURA_ROSTO_SOBRE_LARGURA_FALA = 1.3
# YuNet: detector facial do OpenCV. Substitui o BlazeFace de curto alcance do
# MediaPipe, que neste material nao achava ninguem em metade dos quadros (perfil)
# e ainda detectava o logo da parede como rosto. Medido no podcast do usuario:
# MediaPipe 15/30 quadros, YuNet 30/30, e o logo nunca detectado.
#
# Devolve tambem 5 pontos faciais (olhos, nariz, cantos da boca) — e a geometria
# desses pontos que separa rosto de grafico, coisa que uma caixa sozinha nao faz.
NOME_MODELO_YUNET = "face_detection_yunet_2023mar.onnx"
URL_MODELO_YUNET = (
    "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
# Detecta numa copia reduzida: 1280 de largura ainda resolve rosto pequeno em
# plano aberto e evita o custo de rodar a rede sobre 4K.
# Impressao digital dos modelos que baixamos e conferimos. Sao arquivos vindos
# da internet que passam a rodar na maquina do usuario: se o download vier
# corrompido — ou trocado —, e melhor recusar do que usar. Conferido apos o
# download; se nao bater, o arquivo e apagado e o erro aparece.
SHA256_MODELOS = {
    "face_detection_yunet_2023mar.onnx":
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    "face_recognition_sface_2021dec.onnx":
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
}
LARGURA_DETECCAO_YUNET = 1280
CONFIANCA_MINIMA_YUNET = 0.6

NOME_MODELO_SFACE = "face_recognition_sface_2021dec.onnx"
URL_MODELO_SFACE = (
    "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/"
    "models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
)
# Os recortes vÃªm do MediaPipe (sem os cinco marcos usados pelo alinhamento
# nativo do SFace). Em vÃ­deo real, perfis da mesma pessoa ficam por volta de
# 0.50; 0.55 separava a mesma pessoa em duas identidades. O recorte facial
# justo reduz a influÃªncia do cenÃ¡rio e permite este limiar conservador.
LIMIAR_IDENTIDADE_SFACE = 0.42
# Só funde duas faces presentes no mesmo frame quando a similaridade é bem
# acima do limiar normal: isso cobre a mesma pessoa em duas câmeras, sem
# confundir participantes que compartilham a tomada.
LIMIAR_IDENTIDADE_SIMULTANEA = 0.48

# Regra 3 de PARA-DESENVOLVEDORES.md, valida ate a troca para identidade facial:
# "dois lados so viram duas pessoas se estiverem mais afastados que a soma dos
# meios-ombros E tiverem rostos de tamanho compativel".
#
# O agrupamento por embedding jogou essa geometria fora. Num podcast real dois
# participantes a 57% de tela de distancia viraram uma pessoa so, posicionada no
# ponto medio entre os dois. A regra volta como VETO: dois grupos que aparecem
# NO MESMO FRAME, afastados e com rostos de tamanho parecido sao pessoas
# distintas, e nenhuma similaridade os funde.
#
# A co-ocorrencia e exigida de proposito. Sem ela, a mesma pessoa filmada por
# duas cameras em posicoes diferentes voltaria a virar duas identidades -- que
# foi justamente o motivo de adotar reconhecimento facial.
SEPARACAO_MINIMA_LADOS = 0.22
RAZAO_TAMANHO_COMPATIVEL = 1.7


def _mediana_de(grupo, campo: str):
    """Mediana de um campo das deteccoes, ou None se o dado nao existir."""
    valores = [
        float(d[campo]) for d in grupo.get("deteccoes", ()) if d.get(campo) is not None
    ]
    return float(np.median(valores)) if valores else None


def _sao_participantes_distintos(a, b) -> bool:
    """Dois grupos no mesmo frame, afastados e de tamanho compativel.

    O veto exige evidencia geometrica. Sem posicao ou sem tamanho nas
    deteccoes ele nao opina, e a decisao volta a ser so do rosto -- e assim
    que os testes de unidade e o caminho de fallback continuam valendo.
    """
    if not (a["frames"] & b["frames"]):
        return False

    xa, xb = _mediana_de(a, "posicao_x"), _mediana_de(b, "posicao_x")
    if xa is None or xb is None:
        return False
    if abs(xa - xb) < SEPARACAO_MINIMA_LADOS:
        return False

    ta, tb = _mediana_de(a, "tamanho"), _mediana_de(b, "tamanho")
    if not ta or not tb:
        return False
    return (max(ta, tb) / min(ta, tb)) <= RAZAO_TAMANHO_COMPATIVEL

# O SFace só distingue pessoas se receber rosto, e a caixa crua nem sempre é
# rosto: em plano aberto ela pega corpo e parede, e o embedding vira textura de
# madeira — foi assim que duas pessoas diferentes caíram na mesma identidade e
# a mesma pessoa apareceu duas vezes. Por isso a caixa é reapertada no rosto
# encontrado dentro dela, e o que sobra é medido antes de virar identidade.
# Os cortes vieram de medição no material real: parede/flor desfocada ficam em
# nitidez ~10-70, rosto de verdade em 250+; a caixa de plano aberto tem rosto
# ocupando 0.17-0.26 dela, a de rosto real 0.35+.
MIN_NITIDEZ_ROSTO = 150.0
MIN_NITIDEZ_ROSTO_YUNET = 40.0
MIN_FRACAO_ROSTO = 0.35


def _print_seguro(mensagem) -> None:
    """Imprime logs sem derrubar o processamento em console Windows CP1252."""
    try:
        print(mensagem)
    except UnicodeEncodeError:
        print(str(mensagem).encode("ascii", errors="replace").decode("ascii"))


def _caminho_recurso(nome: str) -> str:
    """Localiza recursos tanto no cÃ³digo-fonte quanto no executÃ¡vel."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome)


def _caminho_modelo_facial() -> str:
    """Usa o modelo empacotado ou uma copia persistente gravavel."""
    empacotado = _caminho_recurso("face_detector.tflite")
    if os.path.isfile(empacotado):
        return empacotado
    pasta_modelos = os.path.join(pasta_dados(), "modelos")
    os.makedirs(pasta_modelos, exist_ok=True)
    return os.path.join(pasta_modelos, "face_detector.tflite")


def _corrigir_mp4(caminho_video: str) -> str:
    """
    Corrige o mp4 movendo o moov atom para o inÃ­cio.
    Resolve o erro 'moov atom not found' do OpenCV.
    Retorna o caminho do arquivo corrigido (ou o original se nÃ£o precisar).
    """
    # A maioria dos arquivos abre normalmente. Remuxar sempre duplicava vÃ­deos
    # enormes e atrasava a primeira etapa sem necessidade.
    cap = cv2.VideoCapture(caminho_video)
    abriu = cap.isOpened()
    if abriu:
        abriu, _ = cap.read()
    cap.release()
    if abriu:
        return caminho_video

    import subprocess
    fd, caminho_corrigido = tempfile.mkstemp(suffix="_fixed.mp4")
    os.close(fd)
    cmd = [
        "ffmpeg", "-y", "-i", caminho_video,
        "-c", "copy", "-movflags", "+faststart",
        caminho_corrigido
    ]
    resultado = subprocess.run(cmd, capture_output=True)
    if resultado.returncode == 0 and os.path.exists(caminho_corrigido):
        return caminho_corrigido
    if os.path.exists(caminho_corrigido):
        os.remove(caminho_corrigido)
    return caminho_video  # usa original se falhar


def _planejar_rodadas_amostragem(total_frames: int, fps: float,
                                   max_amostras: int = 30,
                                   limite_minutos: float = 5.0) -> list:
    """Distribui pequenos lotes por toda a duração, sem repetir frames."""
    total = max(1, int(total_frames))
    quantidade = min(total, max(1, int(max_amostras)))
    # Em podcasts, os dois participantes costumam aparecer juntos logo no
    # começo. Reservar uma parte da amostragem evita perder um deles quando o
    # restante do episódio alterna apenas para quem está falando.
    inicio_quantidade = min(quantidade, max(2, quantidade // 4))
    inicio_fim = min(
        total - 1,
        max(1, int(max(1.0, limite_minutos) * 60 * (fps or 30.0)) - 1),
    )
    alvos = list(dict.fromkeys(
        [
            *(int(valor) for valor in np.linspace(
                0, inicio_fim, inicio_quantidade, dtype=int
            )),
            *(int(valor) for valor in np.linspace(
                0, total - 1, quantidade, dtype=int
            )),
        ]
    ))
    if len(alvos) < quantidade:
        for valor in np.linspace(0, total - 1, quantidade * 2, dtype=int):
            if int(valor) not in alvos:
                alvos.append(int(valor))
            if len(alvos) == quantidade:
                break
    alvos = sorted(alvos[:quantidade])
    lote = max(1, min(8, int(max_amostras // 4) or 1))
    return [alvos[inicio:inicio + lote] for inicio in range(0, len(alvos), lote)]


def _busca_esta_estavel(historico_assinaturas: list,
                         rodadas_sem_novidade: int = 3) -> bool:
    """Só encerra com identidades reais e várias rodadas sem novidade."""
    quantidade = max(1, int(rodadas_sem_novidade))
    if len(historico_assinaturas) < quantidade:
        return False
    ultimas = [tuple(item) for item in historico_assinaturas[-quantidade:]]
    return bool(ultimas[0]) and all(item == ultimas[0] for item in ultimas[1:])


def _assinaturas_pessoas(pessoas: list) -> tuple:
    """Representa cada identidade separadamente, mesmo no mesmo lado."""
    return tuple(int(p.get("id", i)) for i, p in enumerate(pessoas or []))

def detectar_pessoas_no_video(caminho_video: str, max_amostras: int = 30,
                               limite_minutos: float = 5.0) -> list:
    """Detecta participantes em rodadas progressivas por toda a duração."""
    caminho_original = caminho_video
    caminho_video = _corrigir_mp4(caminho_video)
    detector = _inicializar_detector()
    if detector is None:
        _print_seguro("Detector não disponível.")
        return []

    reconhecedor = _inicializar_reconhecedor_facial()
    cap = cv2.VideoCapture(caminho_video)
    deteccoes = []
    pessoas = []
    frames_lidos = 0
    amostras_analisadas = 0
    historico = []
    motivo_parada = "fim do vídeo"
    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        largura = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        altura = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        rodadas = _planejar_rodadas_amostragem(
            total_frames, fps, max_amostras, limite_minutos
        )
        _print_seguro(
            f"Detectando pessoas de forma adaptativa ({len(rodadas)} faixas possíveis)..."
        )

        for numero, alvos in enumerate(rodadas, 1):
            lidos_rodada = 0
            for frame_idx in alvos:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
                ret, frame = cap.read()
                if not ret:
                    continue
                frames_lidos += 1
                lidos_rodada += 1
                for rosto in detectar_rostos_robusto(frame, detector):
                    x_centro = rosto["x"] * largura
                    y_centro = rosto["y"] * altura
                    w_rosto = rosto["w"] * largura
                    h_rosto = rosto.get("h", rosto["w"]) * altura
                    margem = 0.5
                    x1 = max(0, int(x_centro - w_rosto * (0.5 + margem)))
                    y1 = max(0, int(y_centro - h_rosto * (0.5 + margem)))
                    x2 = min(largura, int(x_centro + w_rosto * (0.5 + margem)))
                    y2 = min(altura, int(y_centro + h_rosto * (0.5 + margem)))
                    rx1 = max(0, int(x_centro - w_rosto * 0.55))
                    ry1 = max(0, int(y_centro - h_rosto * 0.55))
                    rx2 = min(largura, int(x_centro + w_rosto * 0.55))
                    ry2 = min(altura, int(y_centro + h_rosto * 0.55))
                    recorte = frame[y1:y2, x1:x2]
                    recorte_identidade = frame[ry1:ry2, rx1:rx2]
                    if recorte.size == 0 or recorte_identidade.size == 0:
                        continue
                    # Aperta no rosto antes de guardar: é este recorte que vira
                    # embedding, e caixa com parede dentro embaralha identidades.
                    apertado = _apertar_no_rosto(recorte_identidade, detector)
                    if apertado is None:
                        continue
                    recorte_identidade, fracao = apertado
                    recorte_embedding = _alinhar_rosto_yunet(
                        frame, rosto, reconhecedor
                    )
                    if recorte_embedding is None:
                        recorte_embedding = recorte_identidade
                    deteccoes.append({
                        "posicao_x": rosto["x"],
                        "posicao_y": rosto["y"],
                        # Tamanho do rosto DE VERDADE: a caixa crua vem inflada,
                        # e `fracao` diz quanto dela o rosto ocupa. Guardado aqui
                        # porque a deteccao de fala precisa saber onde fica a boca
                        # de quem o detector nao achou naquele frame.
                        "tamanho": float(rosto["w"]) * 1.1 * float(fracao),
                        "fonte": rosto.get("fonte", "mediapipe"),
                        "confianca": rosto.get("confianca", 0.0),
                        "pontos": rosto.get("pontos", []),
                        "recorte": recorte,
                        "recorte_identidade": recorte_identidade,
                        "recorte_embedding": recorte_embedding,
                        "fracao_rosto": fracao,
                        "nitidez": _nitidez(recorte_identidade),
                        "frame_idx": int(frame_idx),
                    })

            amostras_analisadas += lidos_rodada
            filtradas = _filtrar_candidatos_pessoas(
                deteccoes,
                amostras_analisadas,
                exigir_persistencia_por_lado=(reconhecedor is None),
            )
            filtradas = _remover_identidades_sem_rosto_valido(filtradas)
            if filtradas:
                pessoas = (
                    _agrupar_por_identidade(filtradas, reconhecedor, amostras_analisadas)
                    if reconhecedor is not None
                    else _agrupar_por_posicao(filtradas)
                )
            else:
                pessoas = []
            historico.append(_assinaturas_pessoas(pessoas))
            segundo_ini = int(alvos[0] / fps) if alvos else 0
            segundo_fim = int(alvos[-1] / fps) if alvos else 0
            _print_seguro(
                f"Rodada {numero}: {segundo_ini // 60}-{segundo_fim // 60} min, "
                f"{lidos_rodada} amostras, {len(pessoas)} identidade(s) confirmada(s)."
            )
            if (
                amostras_analisadas >= max(1, int(max_amostras))
                and _busca_esta_estavel(historico, 3)
            ):
                motivo_parada = "identidades estáveis por três rodadas"
                break
    finally:
        cap.release()
        _fechar_detector(detector)
        if caminho_video != caminho_original and os.path.exists(caminho_video):
            try:
                os.remove(caminho_video)
            except OSError:
                pass

    if frames_lidos == 0:
        _print_seguro(MSG_VIDEO_ILEGIVEL)
        raise VideoIlegivelError(MSG_VIDEO_ILEGIVEL)
    _print_seguro(f"Busca encerrada: {motivo_parada}.")
    if not pessoas:
        _print_seguro("Nenhum rosto persistente detectado.")
        return []
    _print_seguro(f"{len(pessoas)} pessoa(s) identificada(s) no vídeo.")
    return pessoas

def _apertar_no_rosto(recorte, detector):
    """Reaperta a caixa no rosto que existe dentro dela.

    Devolve ``(recorte_apertado, fracao)``, onde ``fracao`` é quanto da largura
    da caixa o rosto ocupa — baixo significa caixa de corpo inteiro ou cenário.
    Devolve ``None`` quando não há rosto nenhum ali dentro.
    """
    if not isinstance(recorte, np.ndarray) or recorte.size == 0:
        return None
    if min(recorte.shape[:2]) < 24:
        return None

    # Trabalha numa cópia reduzida. O detector é de curto alcance e se comporta
    # de outro jeito num recorte 4K — em vídeo assim ele passou a recusar os
    # perfis da apresentadora. 400px é a escala em que os cortes desta função
    # foram medidos, e ainda sobra resolução de sobra para o SFace (112px).
    maior = max(recorte.shape[:2])
    if maior > 400:
        escala = 400.0 / maior
        recorte = cv2.resize(
            recorte,
            (max(1, int(recorte.shape[1] * escala)), max(1, int(recorte.shape[0] * escala))),
            interpolation=cv2.INTER_AREA,
        )

    try:
        achados = detectar_rostos_robusto(recorte, detector)
    except Exception as erro:
        LOGGER.debug("Falha ao reapertar recorte: %s", erro)
        return None
    if not achados:
        return None

    rosto = max(achados, key=lambda r: float(r["w"]) * float(r.get("h", r["w"])))
    altura, largura = recorte.shape[:2]
    x_centro, y_centro = rosto["x"] * largura, rosto["y"] * altura
    w_rosto = rosto["w"] * largura
    h_rosto = rosto.get("h", rosto["w"]) * altura
    x1 = max(0, int(x_centro - w_rosto * 0.62))
    y1 = max(0, int(y_centro - h_rosto * 0.62))
    x2 = min(largura, int(x_centro + w_rosto * 0.62))
    y2 = min(altura, int(y_centro + h_rosto * 0.62))
    apertado = recorte[y1:y2, x1:x2]
    if apertado.size == 0 or min(apertado.shape[:2]) < 24:
        return None
    return apertado, float(rosto["w"])


def refinar_caixa_rosto(frame, rosto: dict, detector) -> dict:
    """Corrige a caixa do detector para a caixa do rosto de verdade.

    A detecção multiescala às vezes devolve uma caixa bem maior que o rosto,
    pegando tronco e parede junto. Quem depende do TAMANHO do rosto se perde
    com isso: o enquadramento conclui que a cabeça não cabe no quadro 9:16 e
    degrada para um layout mais aberto — no meio de um plano estável, e só nas
    amostras em que a caixa saiu inflada. O resultado é o zoom pulando.

    Devolve uma cópia do rosto com x/y/w/h corrigidos, em coordenadas
    normalizadas do frame original, ou ``None`` se não houver rosto ali dentro.
    """
    if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
        return None

    # O YuNet ja entrega a caixa justa no rosto, com pontos faciais. Reapertar
    # so gastaria tempo e poderia piorar. Este refino existe para a caixa do
    # MediaPipe, que vinha inflada com tronco e parede dentro.
    if rosto.get("fonte") == "yunet":
        refinado = dict(rosto)
        refinado.setdefault("nitidez", _nitidez_da_caixa(frame, rosto))
        return refinado

    altura, largura = frame.shape[:2]
    try:
        centro_x = float(rosto["x"]) * largura
        centro_y = float(rosto["y"]) * altura
        rosto_w = float(rosto["w"]) * largura
        rosto_h = float(rosto.get("h", rosto["w"])) * altura
    except (KeyError, TypeError, ValueError):
        return None

    x0 = max(0, int(centro_x - rosto_w * 0.55))
    y0 = max(0, int(centro_y - rosto_h * 0.55))
    x1 = min(largura, int(centro_x + rosto_w * 0.55))
    y1 = min(altura, int(centro_y + rosto_h * 0.55))
    recorte = frame[y0:y1, x0:x1]
    if recorte.size == 0 or min(recorte.shape[:2]) < 24:
        return None

    rec_h, rec_w = recorte.shape[:2]
    maior = max(rec_h, rec_w)
    reduzido = recorte
    if maior > 400:
        escala = 400.0 / maior
        reduzido = cv2.resize(
            recorte,
            (max(1, int(rec_w * escala)), max(1, int(rec_h * escala))),
            interpolation=cv2.INTER_AREA,
        )

    try:
        # Passe único, não a busca multiescala: aqui o rosto já ocupa boa parte
        # do recorte, então varrer metades ampliadas em 3x só custa tempo — e
        # esta função roda uma vez por rosto por amostra.
        achados = _detectar_rostos_frame(reduzido, detector)
        if not achados:
            achados = detectar_rostos_robusto(reduzido, detector)
    except Exception as erro:
        LOGGER.debug("Falha ao refinar caixa de rosto: %s", erro)
        return None
    if not achados:
        return None

    interno = max(achados, key=lambda r: float(r["w"]) * float(r.get("h", r["w"])))

    # Nitidez do rosto apertado, medida na escala em que os cortes foram
    # calibrados. Serve para quem chama distinguir rosto de decoracao: no
    # material real, flor e luminaria desfocadas ficam em 10-70 e rosto em 250+.
    altura_r, largura_r = reduzido.shape[:2]
    ix1 = max(0, int(interno["x"] * largura_r - interno["w"] * largura_r * 0.5))
    iy1 = max(0, int(interno["y"] * altura_r - interno.get("h", interno["w"]) * altura_r * 0.5))
    ix2 = min(largura_r, int(interno["x"] * largura_r + interno["w"] * largura_r * 0.5))
    iy2 = min(altura_r, int(interno["y"] * altura_r + interno.get("h", interno["w"]) * altura_r * 0.5))
    recorte_rosto = reduzido[iy1:iy2, ix1:ix2]
    nitidez = _nitidez(recorte_rosto) if recorte_rosto.size else 0.0

    refinado = dict(rosto)
    refinado["nitidez"] = nitidez
    refinado["x"] = (x0 + float(interno["x"]) * rec_w) / largura
    refinado["y"] = (y0 + float(interno["y"]) * rec_h) / altura
    refinado["w"] = (float(interno["w"]) * rec_w) / largura
    refinado["h"] = (float(interno.get("h", interno["w"])) * rec_h) / altura
    return refinado


def _nitidez_da_caixa(frame, rosto) -> float:
    """Nitidez medida dentro da caixa do rosto, na escala usada nos limiares."""
    altura, largura = frame.shape[:2]
    cx, cy = float(rosto["x"]) * largura, float(rosto["y"]) * altura
    w = float(rosto["w"]) * largura
    h = float(rosto.get("h", rosto["w"])) * altura
    x1 = max(0, int(cx - w / 2)); y1 = max(0, int(cy - h / 2))
    x2 = min(largura, int(cx + w / 2)); y2 = min(altura, int(cy + h / 2))
    recorte = frame[y1:y2, x1:x2]
    if recorte.size == 0 or min(recorte.shape[:2]) < 12:
        return 0.0
    maior = max(recorte.shape[:2])
    if maior > 400:
        e = 400.0 / maior
        recorte = cv2.resize(recorte, (max(1, int(recorte.shape[1]*e)),
                                       max(1, int(recorte.shape[0]*e))),
                             interpolation=cv2.INTER_AREA)
    return _nitidez(recorte)


def _nitidez(recorte) -> float:
    cinza = cv2.cvtColor(recorte, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(cinza, cv2.CV_64F).var())


def _remover_identidades_sem_rosto_valido(deteccoes: list) -> list:
    """Mantém somente recortes faciais reais, não quadros vazios ou minúsculos."""
    validas = []
    for det in deteccoes or []:
        recorte = det.get("recorte_identidade")
        if not isinstance(recorte, np.ndarray) or recorte.size == 0:
            continue
        if recorte.ndim < 2 or recorte.shape[0] < 20 or recorte.shape[1] < 20:
            continue
        proporcao = recorte.shape[1] / max(1.0, float(recorte.shape[0]))
        if not (0.45 <= proporcao <= 1.8):
            continue
        # Sem rosto de verdade não há identidade: cenário desfocado e caixas de
        # corpo inteiro só atrapalham o agrupamento.
        if float(det.get("fracao_rosto", 1.0)) < MIN_FRACAO_ROSTO:
            continue
        limite_nitidez = (
            MIN_NITIDEZ_ROSTO_YUNET
            if det.get("fonte") == "yunet"
            and float(det.get("confianca", 0.0)) >= CONFIANCA_MINIMA_YUNET
            else MIN_NITIDEZ_ROSTO
        )
        if float(det.get("nitidez", 1e9)) < limite_nitidez:
            continue
        validas.append(det)
    return validas

def _filtrar_candidatos_pessoas(
    deteccoes: list,
    total_amostras: int,
    exigir_persistencia_por_lado: bool = True,
) -> list:
    """Remove objetos do cenÃ¡rio antes de criar a lista de participantes.

    Uma pessoa real precisa aparecer em mais de um frame e, em podcasts,
    normalmente tem o centro do rosto entre 28% e 78% da altura. TV, bustos
    em estante e objetos sobre a mesa costumam ficar fora dessa faixa.

    Se a composiÃ§Ã£o for atÃ­pica, detecÃ§Ãµes confirmadas pelo MediaPipe ainda
    sÃ£o aceitas; o Haar, mais sujeito a falsos positivos, nunca Ã© usado fora
    da zona humana sem confirmaÃ§Ã£o do MediaPipe.
    """
    if not deteccoes:
        return []

    na_zona = [d for d in deteccoes if 0.28 <= float(d.get("posicao_y", 0.5)) <= 0.78]
    if na_zona:
        candidatos = na_zona
    else:
        candidatos = [d for d in deteccoes if d.get("fonte", "mediapipe") != "haar"]

    if not candidatos:
        return []

    if not exigir_persistencia_por_lado:
        return candidatos

    minimo_frames = max(2, min(4, int(np.ceil(max(1, total_amostras) * 0.10))))
    por_lado = {"esquerda": [], "centro": [], "direita": []}
    for det in candidatos:
        x = float(det["posicao_x"])
        lado = "esquerda" if x < 0.4 else ("direita" if x > 0.6 else "centro")
        por_lado[lado].append(det)

    confirmados = []
    for detecs in por_lado.values():
        frames_distintos = {int(d.get("frame_idx", -1)) for d in detecs}
        fontes = {d.get("fonte", "mediapipe") for d in detecs}
        minimo = minimo_frames + (1 if fontes == {"haar"} else 0)
        if len(frames_distintos) >= minimo:
            confirmados.extend(detecs)

    return confirmados


def _caminho_modelo_reconhecimento() -> str:
    pasta = os.path.join(pasta_dados(), "models")
    os.makedirs(pasta, exist_ok=True)
    return os.path.join(pasta, NOME_MODELO_SFACE)


def _inicializar_reconhecedor_facial():
    """Carrega o SFace oficial do OpenCV; falha silenciosamente para fallback."""
    if not hasattr(cv2, "FaceRecognizerSF"):
        return None

    caminho = _caminho_modelo_reconhecimento()
    if os.path.isfile(caminho) and not _conferir_modelo(caminho):
        _print_seguro("   Modelo de reconhecimento corrompido; baixando de novo.")
        try:
            os.remove(caminho)
        except OSError:
            pass
    if not os.path.isfile(caminho) or os.path.getsize(caminho) < 30_000_000:
        try:
            _print_seguro("   Baixando modelo de reconhecimento facial (37 MB)...")
            _baixar_modelo(URL_MODELO_SFACE, caminho)
        except Exception as erro:
            LOGGER.warning("SFace indisponÃ­vel; usando agrupamento por posiÃ§Ã£o: %s", erro)
            try:
                if os.path.exists(caminho + ".parcial"):
                    os.remove(caminho + ".parcial")
            except OSError:
                pass
            return None

    try:
        return cv2.FaceRecognizerSF.create(caminho, "")
    except Exception as erro:
        LOGGER.warning("Falha ao carregar SFace; usando agrupamento por posiÃ§Ã£o: %s", erro)
        return None


def _extrair_embedding_facial(recorte, reconhecedor):
    try:
        rosto = cv2.resize(recorte, (112, 112), interpolation=cv2.INTER_AREA)
        embedding = reconhecedor.feature(rosto)
        if embedding is None or not np.isfinite(embedding).all():
            return None
        return embedding
    except Exception as erro:
        LOGGER.debug("Falha ao extrair embedding facial: %s", erro)
        return None


def _alinhar_rosto_yunet(frame, rosto: dict, reconhecedor):
    """Alinha o rosto YuNet antes do SFace comparar identidades."""
    if (
        reconhecedor is None
        or rosto.get("fonte") != "yunet"
        or len(rosto.get("pontos", ())) != 5
        or frame is None
        or frame.size == 0
    ):
        return None
    try:
        altura, largura = frame.shape[:2]
        w = float(rosto["w"]) * largura
        h = float(rosto["h"]) * altura
        x = float(rosto["x"]) * largura - w / 2.0
        y = float(rosto["y"]) * altura - h / 2.0
        face = np.array(
            [[x, y, w, h, *(
                coordenada
                for ponto in rosto["pontos"]
                for coordenada in (float(ponto[0]) * largura, float(ponto[1]) * altura)
            )]],
            dtype=np.float32,
        )
        alinhado = reconhecedor.alignCrop(frame, face)
        return alinhado if isinstance(alinhado, np.ndarray) and alinhado.size else None
    except Exception as erro:
        LOGGER.debug("Falha ao alinhar rosto YuNet: %s", erro)
        return None


def _escolher_melhor_preview(deteccoes: list):
    """Escolhe um rosto nÃ­tido sem favorecer caixas gigantes ou vazias."""
    areas = np.array([
        d.get("recorte_identidade", d["recorte"]).shape[0]
        * d.get("recorte_identidade", d["recorte"]).shape[1]
        for d in deteccoes
    ], dtype=np.float32)
    area_mediana = float(np.median(areas)) if len(areas) else 0.0
    candidatos = []
    for det, area in zip(deteccoes, areas):
        rosto = det.get("recorte_identidade", det["recorte"])
        if rosto.size == 0:
            continue
        # Caixas multiescala aberrantes costumam ser muito maiores que as
        # demais e conter cenÃ¡rio preto em vez do participante.
        if area_mediana and not (area_mediana * 0.45 <= area <= area_mediana * 2.20):
            continue
        cinza = cv2.cvtColor(rosto, cv2.COLOR_BGR2GRAY)
        contraste = float(cinza.std())
        nitidez = float(cv2.Laplacian(cinza, cv2.CV_64F).var())
        if contraste >= 8.0:
            confianca = max(0.20, float(det.get("confianca", 0.0)))
            qualidade = nitidez * max(0.25, contraste / 32.0) * (confianca ** 2)
            candidatos.append((qualidade, det))
    if candidatos:
        return max(candidatos, key=lambda item: item[0])[1]
    return max(deteccoes, key=lambda d: d["recorte"].shape[0] * d["recorte"].shape[1])


def _fundir_grupos_da_mesma_pessoa(grupos: list, reconhecedor, limiar: float) -> list:
    """Junta grupos que são a mesma pessoa vista de outro jeito.

    O agrupamento é guloso e vai comparando cada rosto com os grupos que já
    existem, então quem aparece muito de perfil acaba espalhado em vários
    grupos pequenos que depois morrem no corte de mínimo de frames — foi o que
    sumiu com a apresentadora no material de teste. Aqui os grupos se comparam
    entre si. Dois grupos que aparecem no mesmo frame são pessoas distintas,
    por definição, e nunca se fundem.
    """
    fundiu = True
    while fundiu:
        fundiu = False
        for i in range(len(grupos)):
            for j in range(i + 1, len(grupos)):
                a, b = grupos[i], grupos[j]
                if _sao_participantes_distintos(a, b):
                    continue
                # Mediana, nao maximo. Com oito poses de cada lado, o maximo de
                # 64 pares sobe so por haver mais amostra: um grupo grande
                # acabava fundindo com qualquer coisa, e bastava rodar mais
                # rodadas para a fusao errada acontecer.
                score = float(np.median([
                    float(reconhecedor.match(ea, eb, cv2.FaceRecognizerSF_FR_COSINE))
                    for ea in a["embeddings"]
                    for eb in b["embeddings"]
                ]))
                limite = (
                    max(limiar, LIMIAR_IDENTIDADE_SIMULTANEA)
                    if a["frames"] & b["frames"]
                    else limiar
                )
                if score >= limite:
                    a["deteccoes"].extend(b["deteccoes"])
                    a["frames"] |= b["frames"]
                    a["embeddings"] = (a["embeddings"] + b["embeddings"])[:8]
                    grupos.pop(j)
                    fundiu = True
                    break
            if fundiu:
                break
    return grupos


def _agrupar_por_identidade(
    deteccoes: list,
    reconhecedor,
    total_amostras: int,
    limiar: float = LIMIAR_IDENTIDADE_SFACE,
) -> list:
    """Agrupa rostos pelo embedding SFace, independentemente da cÃ¢mera/lado."""
    grupos = []
    for det in sorted(deteccoes, key=lambda d: int(d.get("frame_idx", 0))):
        recorte_identidade = det.get(
            "recorte_embedding", det.get("recorte_identidade", det["recorte"])
        )
        embedding = _extrair_embedding_facial(recorte_identidade, reconhecedor)
        if embedding is None:
            continue

        melhor_grupo = None
        melhor_score = -1.0
        frame_idx = int(det.get("frame_idx", -1))
        for grupo in grupos:
            # Duas faces no mesmo frame sÃ£o necessariamente pessoas distintas.
            if frame_idx in grupo["frames"]:
                continue
            score = max(
                float(reconhecedor.match(embedding, existente, cv2.FaceRecognizerSF_FR_COSINE))
                for existente in grupo["embeddings"]
            )
            if score > melhor_score:
                melhor_score = score
                melhor_grupo = grupo

        if melhor_grupo is not None and melhor_score >= limiar:
            melhor_grupo["deteccoes"].append(det)
            melhor_grupo["frames"].add(frame_idx)
            # Limita memÃ³ria sem perder variedade de poses.
            if len(melhor_grupo["embeddings"]) < 8:
                melhor_grupo["embeddings"].append(embedding)
        else:
            grupos.append({
                "deteccoes": [det],
                "embeddings": [embedding],
                "frames": {frame_idx},
            })

    if not grupos and deteccoes:
        LOGGER.warning(
            "SFace nÃ£o extraiu embeddings; usando agrupamento por posiÃ§Ã£o."
        )
        return _agrupar_por_posicao(deteccoes)

    grupos = _fundir_grupos_da_mesma_pessoa(grupos, reconhecedor, limiar)
    # Em uma varredura global de 30 pontos, um participante que aparece em
    # duas tomadas distintas é real; exigir quatro o descartava. Em análises
    # maiores, a fração mantém a proteção contra rostos passageiros.
    minimo_frames = max(2, int(np.ceil(max(1, total_amostras) * 0.06)))
    grupos = [g for g in grupos if len(g["frames"]) >= minimo_frames]
    grupos.sort(key=lambda g: float(np.mean([d["posicao_x"] for d in g["deteccoes"]])))

    pessoas = []
    for grupo in grupos:
        detecs = grupo["deteccoes"]
        melhor = _escolher_melhor_preview(detecs)
        preview = cv2.resize(melhor.get("recorte_identidade", melhor["recorte"]), (200, 200), interpolation=cv2.INTER_LANCZOS4)
        _, buffer = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 85])
        pos_x_media = float(np.mean([d["posicao_x"] for d in detecs]))
        # Mediana, nao media: uma deteccao esquisita nao pode deslocar o ponto
        # onde a deteccao de fala vai procurar a boca desta pessoa.
        pos_y_media = float(np.median([d.get("posicao_y", 0.40) for d in detecs]))
        tamanhos = [float(d.get("tamanho", 0.0)) for d in detecs if d.get("tamanho")]
        tamanho_medio = float(np.median(tamanhos)) if tamanhos else 0.0
        lado = "esquerda" if pos_x_media < 0.4 else ("direita" if pos_x_media > 0.6 else "centro")
        pessoas.append({
            "id": len(pessoas),
            "nome": f"Pessoa {len(pessoas) + 1} ({lado})",
            "posicao_x": pos_x_media,
            "posicao_y": pos_y_media,
            "tamanho": tamanho_medio,
            "lado": lado,
            "preview_base64": base64.b64encode(buffer).decode("utf-8"),
            "n_aparicoes": len(detecs),
            "recorte_cv2": preview,
        })
    return pessoas


def _agrupar_por_posicao(deteccoes: list, limiar_agrupamento: float = 0.25) -> list:
    """
    Agrupa detecÃ§Ãµes de rostos por posiÃ§Ã£o X para identificar pessoas distintas.

    EstratÃ©gia simples e eficaz para podcasts:
    - Rostos no lado esquerdo (x < 0.4) â†’ Pessoa A
    - Rostos no lado direito (x > 0.6) â†’ Pessoa B
    - Rostos no centro (0.4-0.6) â†’ pode ser plano geral ou terceira pessoa
    """
    grupos = {}

    for det in deteccoes:
        x = det["posicao_x"]

        # Define o grupo baseado na posiÃ§Ã£o X
        if x < 0.4:
            chave = "esquerda"
        elif x > 0.6:
            chave = "direita"
        else:
            chave = "centro"

        if chave not in grupos:
            grupos[chave] = []
        grupos[chave].append(det)

    pessoas = []
    ordem = {"esquerda": 0, "direita": 1, "centro": 2}

    for lado, detecs in sorted(grupos.items(), key=lambda x: ordem.get(x[0], 99)):
        # Pega o melhor recorte (maior Ã¡rea)
        melhor = max(detecs, key=lambda d: d["recorte"].shape[0] * d["recorte"].shape[1])
        recorte = melhor["recorte"]

        # Redimensiona para preview padronizado (200x200)
        preview = cv2.resize(recorte, (200, 200), interpolation=cv2.INTER_LANCZOS4)

        # Converte para base64 para exibir no Gradio
        _, buffer = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 85])
        preview_b64 = base64.b64encode(buffer).decode('utf-8')

        # PosiÃ§Ã£o mÃ©dia X desse grupo
        pos_x_media = np.mean([d["posicao_x"] for d in detecs])

        pessoas.append({
            "id":             len(pessoas),
            "nome":           f"Pessoa {len(pessoas) + 1} ({lado})",
            "posicao_x":      float(pos_x_media),
            "lado":           lado,
            "preview_base64": preview_b64,
            "n_aparicoes":    len(detecs),
            "recorte_cv2":    preview,  # usado internamente
        })

    return pessoas


def salvar_previews(pessoas: list, pasta_temp: str) -> list:
    """
    Salva os previews das pessoas em arquivos temporÃ¡rios.
    Retorna a lista de pessoas com o campo 'preview_path' preenchido.
    """
    os.makedirs(pasta_temp, exist_ok=True)

    for p in pessoas:
        caminho = os.path.join(pasta_temp, f"pessoa_{p['id']}.jpg")
        if "recorte_cv2" in p:
            cv2.imwrite(caminho, p["recorte_cv2"])
            p["preview_path"] = caminho

    return pessoas


def _escolher_fallback_humano(pessoas: list, ultimo=None) -> float:
    """Escolhe uma posiÃ§Ã£o humana real; nunca inventa o centro do quadro."""
    if ultimo is not None:
        return float(ultimo)
    posicoes = [
        float(p["posicao_x"])
        for p in (pessoas or [])
        if p.get("posicao_x") is not None
    ]
    if not posicoes:
        raise RuntimeError(
            "Nenhuma pessoa validada para enquadrar; revise a detecÃ§Ã£o antes de cortar."
        )
    return posicoes[0]

def detectar_quem_fala_por_frame(
    caminho_video: str,
    pessoas: list,
    intervalo_frames: int = 5,
    intervalos_frames: list = None,
    analisar_audio: bool = True,
) -> list:
    """
    Detecta quem estÃ¡ falando em cada frame do vÃ­deo.

    Combina:
    - PosiÃ§Ã£o dos rostos detectados
    - AnÃ¡lise de movimento labial (variaÃ§Ã£o na regiÃ£o da boca)
    - Energia do Ã¡udio por janela de tempo

    Retorna lista com posiÃ§Ã£o_x do falante para cada frame.
    Frames sem fala detectada retornam None.
    """
    detector = _inicializar_detector()
    cap = cv2.VideoCapture(caminho_video)
    try:
        if not cap.isOpened():
            raise RuntimeError("Nao foi possivel abrir o video para detectar o falante.")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = fps if fps and fps > 0 else 30.0
        largura = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        altura = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        _print_seguro(f"ðŸŽ¤ Detectando quem fala em {total_frames} frames...")

        energia_audio = (
            _analisar_energia_audio(caminho_video, fps, total_frames)
            if analisar_audio else [1.0] * total_frames
        )

        # Se o detector facial falhar no primeiro trecho, nÃ£o comeÃ§a no
        # centro arbitrÃ¡rio: usa a posiÃ§Ã£o conhecida do participante quando
        # hÃ¡ apenas uma pessoa identificada. Isso evita enquadrar mesa, TV
        # ou bandeira enquanto o rosto estÃ¡ fora do primeiro frame amostrado.
        posicoes_pessoas = [
            float(p.get("posicao_x"))
            for p in (pessoas or [])
            if p.get("posicao_x") is not None
        ]
        fallback_x = _escolher_fallback_humano(pessoas, ultimo=None)

        resultado = [None] * total_frames
        frame_anterior = None
        ultimo_falante_x = fallback_x

        intervalos = intervalos_frames or [(0, total_frames)]
        for inicio, fim in intervalos:
            inicio = max(0, int(inicio))
            fim = min(total_frames, int(fim))
            cap.set(cv2.CAP_PROP_POS_FRAMES, inicio)

            for frame_idx in range(inicio, fim):
                ret = cap.grab()
                if not ret:
                    break

                if (frame_idx - inicio) % intervalo_frames != 0:
                    continue

                ret, frame = cap.retrieve()
                if not ret:
                    continue
                rostos = detectar_rostos_robusto(frame, detector)
                # Mesmo criterio das outras etapas: decoracao desfocada tambem
                # e "detectada" e aqui chega a VENCER a disputa de movimento
                # labial (ruido de compressao mexe tanto quanto uma boca), e o
                # quadro ia parar 17s sobre um aparador. Sem rosto confiavel e
                # melhor herdar o falante anterior do que mirar em movel.
                rostos = [
                    refinado
                    for refinado in (
                        refinar_caixa_rosto(frame, bruto, detector) for bruto in rostos
                    )
                    if refinado is not None
                    and float(refinado.get("nitidez", 0.0)) >= MIN_NITIDEZ_ROSTO
                ]
                # Inclui quem o detector nao achou mas sabemos onde esta: sem
                # isso, o unico rosto visivel virava "o falante" por omissao.
                rostos = _candidatos_falante(rostos, pessoas)

                if len(rostos) == 0:
                    resultado[frame_idx] = ultimo_falante_x
                elif len(rostos) == 1:
                    ultimo_falante_x = rostos[0]["x"]
                    resultado[frame_idx] = ultimo_falante_x
                else:
                    melhor_falante = _detectar_movimento_labial(
                        frame, frame_anterior, rostos, largura, altura
                    )
                    energia = (
                        energia_audio[frame_idx]
                        if frame_idx < len(energia_audio)
                        else 0.5
                    )
                    if melhor_falante is not None and energia > 0.3:
                        ultimo_falante_x = melhor_falante
                        resultado[frame_idx] = melhor_falante
                    else:
                        resultado[frame_idx] = ultimo_falante_x

                frame_anterior = frame
    finally:
        cap.release()
        _fechar_detector(detector)

    # Interpola frames nÃ£o analisados
    resultado = _interpolar_falante(resultado, total_frames, valor_inicial=fallback_x)

    _print_seguro(f"âœ… DetecÃ§Ã£o de fala concluÃ­da!")
    return resultado


def _candidatos_falante(rostos_detectados: list, pessoas: list) -> list:
    """Junta os rostos detectados com a posição conhecida de quem ficou de fora.

    Quem fala de perfil escapa do detector o tempo todo: neste material, em 24%
    dos frames só um rosto era encontrado, e em 96% dessas vezes era a mesma
    pessoa — a que olha para a câmera. O código então tomava o único rosto
    visível como falante e o quadro fechava em quem estava calado.

    Numa câmera fixa isso é evitável: a etapa 1 já mediu onde cada participante
    fica. Basta medir o movimento de boca naquele ponto, mesmo sem detecção.

    Só entra palpite quando ALGUM rosto foi detectado no frame: sem nenhum, a
    cena provavelmente nem é a do estúdio (b-roll, outro ângulo) e inventar
    posição ali só criaria enquadramento em cima de parede.
    """
    candidatos = [dict(r) for r in (rostos_detectados or [])]
    if not candidatos:
        return candidatos

    for pessoa in pessoas or []:
        posicao_x = pessoa.get("posicao_x")
        tamanho = float(pessoa.get("tamanho") or 0.0)
        if posicao_x is None or tamanho <= 0.0:
            continue
        posicao_x = float(posicao_x)
        ja_detectada = any(
            abs(float(c.get("x", 0.5)) - posicao_x) < max(0.06, float(c.get("w", 0.06)))
            for c in candidatos
        )
        if ja_detectada:
            continue
        candidatos.append({
            "x": posicao_x,
            "y": float(pessoa.get("posicao_y") or 0.40),
            "w": tamanho,
            "h": tamanho * ALTURA_ROSTO_SOBRE_LARGURA_FALA,
            "fonte": "posicao_conhecida",
            "confianca": 0.0,
        })
    return candidatos


def _detectar_movimento_labial(
    frame_atual, frame_anterior, rostos: list,
    largura: int, altura: int
) -> float:
    """
    Detecta qual rosto tem mais movimento na regiÃ£o da boca.
    Usa diferenÃ§a entre frames consecutivos na parte inferior do rosto.
    Retorna a posiÃ§Ã£o X do rosto com mais movimento (quem estÃ¡ falando).

    Se nenhum rosto atinge LIMIAR_MOVIMENTO_LABIAL, o resultado Ã© ambÃ­guo
    (ex.: microfone cobrindo a boca) â€” retorna None em vez de cair sempre
    no primeiro rosto da lista, o que enviesaria sistematicamente a detecÃ§Ã£o
    de fala para o mesmo lado.
    """
    if frame_anterior is None or not rostos:
        return rostos[0]["x"] if rostos else None

    max_movimento = 0
    falante_x = None

    for rosto in rostos:
        # RegiÃ£o da boca: 60-90% da altura do rosto
        x_c = rosto["x"] * largura
        y_c = rosto["y"] * altura
        w   = rosto["w"] * largura
        h   = rosto.get("h", rosto["w"]) * altura

        # Recorte da regiÃ£o da boca
        x1 = max(0, int(x_c - w * 0.3))
        y1 = max(0, int(y_c + h * 0.1))   # abaixo do centro do rosto
        x2 = min(largura, int(x_c + w * 0.3))
        y2 = min(altura, int(y_c + h * 0.5))

        if x2 <= x1 or y2 <= y1:
            continue

        boca_atual    = frame_atual[y1:y2, x1:x2]
        boca_anterior = frame_anterior[y1:y2, x1:x2]

        if boca_atual.shape != boca_anterior.shape or boca_atual.size == 0:
            continue

        # Calcula diferenÃ§a entre frames (movimento)
        diff = cv2.absdiff(
            cv2.cvtColor(boca_atual, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(boca_anterior, cv2.COLOR_BGR2GRAY)
        )
        movimento = float(np.mean(diff))

        if movimento > max_movimento:
            max_movimento = movimento
            falante_x = rosto["x"]

    if max_movimento < LIMIAR_MOVIMENTO_LABIAL:
        return None

    return falante_x


def _analisar_energia_audio(caminho_video: str, fps: float, total_frames: int) -> list:
    """Analisa energia do Ã¡udio e retorna valor por frame."""
    import subprocess
    import wave

    fd, audio_temp = tempfile.mkstemp(suffix="_energia_audio.wav")
    os.close(fd)
    cmd = [
        "ffmpeg", "-y", "-i", caminho_video,
        "-ac", "1", "-ar", "16000", "-vn", audio_temp
    ]
    resultado = subprocess.run(cmd, capture_output=True)

    if resultado.returncode != 0 or not os.path.exists(audio_temp):
        if os.path.exists(audio_temp):
            os.remove(audio_temp)
        return [0.5] * total_frames

    try:
        energias = []
        with wave.open(audio_temp, 'rb') as wf:
            sr = wf.getframerate()
            samples_por_frame = max(1, int(sr / fps))
            # LÃª uma pequena janela por vez. Antes carregava todo o Ã¡udio na
            # memÃ³ria, chegando facilmente a centenas de MB em podcasts longos.
            for _ in range(total_frames):
                raw = wf.readframes(samples_por_frame)
                if not raw:
                    energias.append(0.0)
                    continue
                janela = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                energias.append(float(np.sqrt(np.mean(janela ** 2))))

        # Normaliza 0-1
        maior = max(energias, default=0.0)
        max_e = maior if maior > 0 else 1
        energias = [e / max_e for e in energias]

        os.remove(audio_temp)
        return energias

    except Exception:
        if os.path.exists(audio_temp):
            os.remove(audio_temp)
        return [0.5] * total_frames


def _interpolar_falante(posicoes: list, total_frames: int, valor_inicial: float = 0.5) -> list:
    """Preenche frames sem detecÃ§Ã£o mantendo o Ãºltimo falante conhecido."""
    resultado = list(posicoes)
    ultimo = float(valor_inicial)

    for i in range(total_frames):
        if resultado[i] is not None:
            ultimo = resultado[i]
        else:
            resultado[i] = ultimo

    return resultado


# â”€â”€ MediaPipe helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _conferir_modelo(caminho: str) -> bool:
    """Confere o arquivo contra a impressao digital conhecida.

    Sem hash registrado devolve True: o objetivo e recusar arquivo corrompido
    ou trocado, nao impedir que alguem aponte um modelo proprio.
    """
    import hashlib

    esperado = SHA256_MODELOS.get(os.path.basename(caminho))
    if not esperado:
        return True
    digestor = hashlib.sha256()
    try:
        with open(caminho, "rb") as arquivo:
            for bloco in iter(lambda: arquivo.read(1 << 20), b""):
                digestor.update(bloco)
    except OSError:
        return False
    return digestor.hexdigest() == esperado


def _baixar_modelo(url: str, destino: str) -> str:
    """Baixa, confere e so entao publica o arquivo no lugar definitivo.

    Baixa para um temporario: assim um download interrompido nao deixa um
    modelo pela metade que pareca valido na proxima execucao.
    """
    import urllib.request

    parcial = destino + ".parcial"
    urllib.request.urlretrieve(url, parcial)
    if not _conferir_modelo(parcial):
        try:
            os.remove(parcial)
        except OSError:
            pass
        raise RuntimeError(
            f"O modelo baixado nao confere com a impressao digital conhecida: "
            f"{os.path.basename(destino)}. Download recusado."
        )
    os.replace(parcial, destino)
    return destino


def _caminho_modelo_yunet() -> str:
    """Baixa o modelo do YuNet na primeira vez e reaproveita depois."""
    pasta = os.path.join(pasta_dados(), "models")
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, NOME_MODELO_YUNET)
    if os.path.isfile(destino) and not _conferir_modelo(destino):
        _print_seguro("Modelo YuNet corrompido; baixando de novo.")
        os.remove(destino)
    if not os.path.isfile(destino):
        _print_seguro("Baixando detector facial YuNet (230 KB)...")
        _baixar_modelo(URL_MODELO_YUNET, destino)
    return destino


def _inicializar_yunet():
    """Detector principal. Devolve None se o OpenCV nao tiver o YuNet."""
    if not hasattr(cv2, "FaceDetectorYN"):
        return None
    try:
        caminho = _caminho_modelo_yunet()
        obj = cv2.FaceDetectorYN.create(
            caminho, "", (LARGURA_DETECCAO_YUNET, LARGURA_DETECCAO_YUNET),
            CONFIANCA_MINIMA_YUNET, 0.3, 5000,
        )
        _print_seguro("Detector YuNet carregado.")
        return {"tipo": "yunet", "obj": obj, "tamanho": None}
    except Exception as erro:
        LOGGER.warning("YuNet indisponivel (%s); usando MediaPipe.", erro)
        return None


def _detectar_rostos_yunet(frame, detector) -> list:
    """Passe unico numa copia reduzida — o YuNet ja resolve rosto pequeno.

    A busca multiescala que o MediaPipe exigia (frame inteiro, 2x, metades em
    3x) fica desnecessaria aqui, e era ela que produzia caixas infladas com
    parede dentro.
    """
    altura, largura = frame.shape[:2]
    if largura < 32 or altura < 32:
        return []

    escala = min(1.0, LARGURA_DETECCAO_YUNET / float(largura))
    larg_d = max(32, int(round(largura * escala)))
    alt_d = max(32, int(round(altura * escala)))
    reduzido = (
        cv2.resize(frame, (larg_d, alt_d), interpolation=cv2.INTER_AREA)
        if escala < 1.0 else frame
    )

    obj = detector["obj"]
    if detector.get("tamanho") != (larg_d, alt_d):
        obj.setInputSize((larg_d, alt_d))
        detector["tamanho"] = (larg_d, alt_d)

    try:
        _, faces = obj.detect(reduzido)
    except Exception as erro:
        LOGGER.debug("Falha no YuNet: %s", erro)
        return []
    if faces is None:
        return []

    rostos = []
    for face in faces:
        x, y, w, h = (float(v) for v in face[:4])
        if w <= 0 or h <= 0:
            continue
        rostos.append({
            "x": (x + w / 2.0) / larg_d,
            "y": (y + h / 2.0) / alt_d,
            "w": w / larg_d,
            "h": h / alt_d,
            "fonte": "yunet",
            "confianca": float(face[14]),
            # Pontos faciais em coordenadas normalizadas do frame original.
            "pontos": [
                ((float(face[4 + i * 2]) / larg_d), (float(face[5 + i * 2]) / alt_d))
                for i in range(5)
            ],
        })
    return rostos


def _inicializar_detector():
    yunet = _inicializar_yunet()
    if yunet is not None:
        return yunet

    mediapipe_detector = None
    erros = []
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        modelo_path = _caminho_modelo_facial()
        if not os.path.exists(modelo_path):
            import urllib.request
            _print_seguro("Baixando modelo de deteccao facial...")
            url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
            urllib.request.urlretrieve(url, modelo_path)

        base_options = mp_python.BaseOptions(model_asset_path=modelo_path)
        options = mp_vision.FaceDetectorOptions(
            base_options=base_options,
            # 0.35 em vez de 0.5 â€” rostos pequenos em plano aberto tÃªm
            # confianÃ§a mais baixa; 0.5 deixava muita gente sem detectar
            min_detection_confidence=0.35
        )
        obj = mp_vision.FaceDetector.create_from_options(options)
        mediapipe_detector = {"tipo": "novo", "obj": obj}
        _print_seguro("Detector MediaPipe Tasks carregado.")
    except Exception as erro:
        erros.append(f"MediaPipe Tasks: {erro}")
        try:
            import mediapipe as mp
            # model_selection=1 = full-range (rostos longe da cÃ¢mera)
            obj = mp.solutions.face_detection.FaceDetection(
                model_selection=1, min_detection_confidence=0.35
            )
            mediapipe_detector = {"tipo": "antigo", "obj": obj}
            _print_seguro("Detector MediaPipe full-range carregado.")
        except Exception as erro_antigo:
            erros.append(f"MediaPipe Solutions: {erro_antigo}")

    # Fallback independente do MediaPipe. Os classificadores fazem parte do
    # OpenCV e funcionam tambÃ©m dentro do executÃ¡vel.
    haar = None
    try:
        caminho_haar = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        obj_haar = cv2.CascadeClassifier(caminho_haar)
        if not obj_haar.empty():
            haar = obj_haar
    except Exception as erro:
        erros.append(f"OpenCV Haar: {erro}")

    if mediapipe_detector is None and haar is None:
        mensagem = " | ".join(erros) or "nenhum detector disponÃ­vel"
        LOGGER.error("Falha ao inicializar detectores: %s", mensagem)
        _print_seguro(f"   âš ï¸ Falha ao carregar detector facial: {mensagem}")
        return None

    if erros:
        LOGGER.warning("Detectores com fallback: %s", " | ".join(erros))

    return {
        "tipo": "combinado",
        "mediapipe": mediapipe_detector,
        "haar": haar,
    }


def _fechar_detector(detector):
    try:
        if isinstance(detector, dict) and detector.get("tipo") == "yunet":
            return  # o YuNet nao mantem recurso a liberar
        if isinstance(detector, dict) and detector.get("tipo") == "combinado":
            mp_detector = detector.get("mediapipe")
            if mp_detector and mp_detector.get("obj"):
                mp_detector["obj"].close()
        elif isinstance(detector, dict):
            detector["obj"].close()
        else:
            detector.close()
    except Exception as erro:
        LOGGER.debug("Falha ao fechar detector: %s", erro)


def detectar_rostos_robusto(frame, detector) -> list:
    """
    DetecÃ§Ã£o robusta para PLANO ABERTO (rostos pequenos).

    O modelo do MediaPipe Ã© de curto alcance â€” em plano aberto de podcast
    os rostos ficam pequenos demais e ele falha. Esta funÃ§Ã£o tenta 3 vezes
    usando SÃ“ o MediaPipe (nunca o Haar aqui â€” ver motivo abaixo):

    1. Frame original (rÃ¡pido, funciona em close)
    2. Frame ampliado 2x (rostos pequenos ficam detectÃ¡veis)
    3. Metades esquerda/direita ampliadas 3x em largura E altura
       (pessoas coladas nas bordas, longe do centro)

    O Haar cascade (OpenCV) sÃ³ Ã© usado se o MediaPipe nÃ£o estiver disponÃ­vel.
    Quando o MediaPipe funciona mas nÃ£o acha ninguÃ©m apÃ³s todas as escalas,
    o resultado correto Ã© vazio. O Haar confunde padrÃµes do cenÃ¡rio (parede,
    TV, estatueta) com rostos e jÃ¡ gerou enquadramentos mirando em decoraÃ§Ã£o.

    Retorna lista no mesmo formato de _detectar_rostos_frame
    (coordenadas normalizadas 0-1 relativas ao frame ORIGINAL).
    """
    if isinstance(detector, dict) and detector.get("tipo") == "yunet":
        return _limpar_deteccoes(_detectar_rostos_yunet(frame, detector))

    mp_detector = detector.get("mediapipe") if isinstance(detector, dict) else detector

    h, w = frame.shape[:2]
    resultado_mp = []

    # Tentativa 1 â€” frame original, MediaPipe puro. NÃ£o retorna cedo: uma
    # pessoa prÃ³xima pode aparecer aqui enquanto outra, menor, sÃ³ surge no zoom.
    if mp_detector:
        resultado_mp.extend(_detectar_rostos_frame(frame, mp_detector))

    # Tentativa 2 â€” amplia o frame 2x (coordenadas normalizadas nÃ£o mudam)
    if mp_detector:
        try:
            ampliado = cv2.resize(frame, (w * 2, h * 2), interpolation=cv2.INTER_LINEAR)
            resultado_mp.extend(_detectar_rostos_frame(ampliado, mp_detector))
        except Exception:
            pass

        # Tentativa 3 â€” metades esquerda e direita, ampliadas 3x em largura
        # E altura (zoom sÃ³ na largura nÃ£o aumenta rostos pequenos o
        # suficiente; testado empiricamente em plano aberto multicÃ¢mera).
        try:
            resultado = []
            metades = [
                (0.0, frame[:, : w // 2]),       # metade esquerda
                (0.5, frame[:, w // 2 :]),       # metade direita
            ]
            for offset_x, metade in metades:
                mh, mw = metade.shape[:2]
                metade_grande = cv2.resize(metade, (mw * 3, mh * 3), interpolation=cv2.INTER_LINEAR)
                detectados = _detectar_rostos_frame(metade_grande, mp_detector)
                for r in detectados:
                    # Converte coordenadas da metade de volta para o frame inteiro
                    convertido = {
                        "x": offset_x + r["x"] * 0.5,
                        "y": r["y"],
                        "w": r["w"] * 0.5,
                        "h": r["h"],
                        "fonte": r.get("fonte", "mediapipe"),
                        "confianca": r.get("confianca", 0.0),
                    }
                    resultado.append(convertido)
            resultado_mp.extend(resultado)
        except Exception:
            pass

    resultado_mp = _limpar_deteccoes(resultado_mp)
    if resultado_mp:
        return resultado_mp

    # MediaPipe respondeu normalmente, mas nÃ£o encontrou rosto em nenhuma
    # escala. NÃ£o substitui esse resultado por um palpite ruidoso do Haar.
    if mp_detector is not None:
        return []

    # Ãšltimo recurso apenas quando o MediaPipe nem sequer pÃ´de ser carregado.
    haar = detector.get("haar") if isinstance(detector, dict) else None
    return _detectar_rostos_haar(frame, haar) if haar is not None else []


def _detectar_rostos_frame(frame, detector) -> list:
    rostos = []
    h, w = frame.shape[:2]
    try:
        if detector is None:
            return rostos

        if isinstance(detector, dict) and detector.get("tipo") == "combinado":
            mp_detector = detector.get("mediapipe")
            if mp_detector is not None:
                rostos = _detectar_rostos_frame(frame, mp_detector)
            if rostos:
                return _limpar_deteccoes(rostos)
            return _detectar_rostos_haar(frame, detector.get("haar"))

        if isinstance(detector, dict) and detector.get("tipo") == "novo":
            import mediapipe as mp
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            result = detector["obj"].detect(mp_image)
            if result.detections:
                for det in result.detections:
                    bbox = det.bounding_box
                    rostos.append({
                        "x": (bbox.origin_x + bbox.width / 2) / w,
                        "y": (bbox.origin_y + bbox.height / 2) / h,
                        "w": bbox.width / w,
                        "h": bbox.height / h,
                        "fonte": "mediapipe",
                        "confianca": float(det.categories[0].score) if det.categories else 0.0,
                    })
        elif isinstance(detector, dict) and detector.get("tipo") == "antigo":
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            resultado = detector["obj"].process(frame_rgb)
            if resultado.detections:
                for det in resultado.detections:
                    bbox = det.location_data.relative_bounding_box
                    rostos.append({
                        "x": bbox.xmin + bbox.width / 2,
                        "y": bbox.ymin + bbox.height / 2,
                        "w": bbox.width,
                        "h": bbox.height,
                        "fonte": "mediapipe",
                        "confianca": float(det.score[0]) if det.score else 0.0,
                    })
        else:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            resultado = detector.process(frame_rgb)
            if resultado.detections:
                for det in resultado.detections:
                    bbox = det.location_data.relative_bounding_box
                    rostos.append({
                        "x": bbox.xmin + bbox.width / 2,
                        "y": bbox.ymin + bbox.height / 2,
                        "w": bbox.width,
                        "h": bbox.height,
                        "fonte": "mediapipe",
                        "confianca": float(det.score[0]) if det.score else 0.0,
                    })
    except Exception as erro:
        LOGGER.warning("Erro durante detecÃ§Ã£o facial: %s", erro)
    return _limpar_deteccoes(rostos)


def _detectar_rostos_haar(frame, classificador) -> list:
    """Fallback OpenCV para quando MediaPipe falhar ou nÃ£o achar rostos."""
    if classificador is None:
        return []
    try:
        h, w = frame.shape[:2]
        cinza = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cinza = cv2.equalizeHist(cinza)
        min_lado = max(20, int(min(h, w) * 0.025))
        caixas = classificador.detectMultiScale(
            cinza,
            scaleFactor=1.08,
            minNeighbors=4,
            minSize=(min_lado, min_lado),
        )
        return _limpar_deteccoes([
            {
                "x": (x + largura / 2) / w,
                "y": (y + altura / 2) / h,
                "w": largura / w,
                "h": altura / h,
                "fonte": "haar",
                "confianca": 0.0,
            }
            for x, y, largura, altura in caixas
        ])
    except Exception as erro:
        LOGGER.warning("Erro no fallback OpenCV Haar: %s", erro)
        return []


def _limpar_deteccoes(rostos: list) -> list:
    """Remove caixas invÃ¡lidas e duplicadas produzidas pelos fallbacks."""
    resultado = []
    ordenados = sorted(
        rostos,
        key=lambda r: (float(r.get("confianca", 0.0)), float(r.get("w", 0.0)) * float(r.get("h", r.get("w", 0.0)))),
        reverse=True,
    )
    for rosto in ordenados:
        limpo = {
            "x": max(0.0, min(1.0, float(rosto["x"]))),
            "y": max(0.0, min(1.0, float(rosto["y"]))),
            "w": max(0.0, min(1.0, float(rosto["w"]))),
            "h": max(0.0, min(1.0, float(rosto.get("h", rosto["w"])))),
            "fonte": rosto.get("fonte", "desconhecida"),
            "confianca": float(rosto.get("confianca", 0.0)),
        }
        if rosto.get("pontos"):
            limpo["pontos"] = list(rosto["pontos"])
        if limpo["w"] <= 0 or limpo["h"] <= 0:
            continue
        if any(_deteccoes_sobrepostas(limpo, existente) for existente in resultado):
            continue
        resultado.append(limpo)
    return resultado


def _deteccoes_sobrepostas(a: dict, b: dict) -> bool:
    """Considera duplicadas caixas com grande sobreposiÃ§Ã£o ou centro prÃ³ximo."""
    ax1, ay1 = a["x"] - a["w"] / 2, a["y"] - a["h"] / 2
    ax2, ay2 = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
    bx1, by1 = b["x"] - b["w"] / 2, b["y"] - b["h"] / 2
    bx2, by2 = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    uniao = a["w"] * a["h"] + b["w"] * b["h"] - inter
    iou = inter / uniao if uniao > 0 else 0.0
    # Em detecÃ§Ã£o multi-escala, a mesma face pode voltar como uma caixa
    # grande no frame inteiro e outra menor na metade ampliada. Usa a maior
    # caixa como referÃªncia; pessoas realmente distintas tÃªm centros muito
    # mais afastados em relaÃ§Ã£o ao prÃ³prio tamanho facial.
    centro_proximo = (
        abs(a["x"] - b["x"]) < max(0.04, max(a["w"], b["w"]) * 0.50)
        and abs(a["y"] - b["y"]) < max(0.04, max(a["h"], b["h"]) * 0.40)
    )
    return iou >= 0.20 or centro_proximo
# fim do arquivo â€” deteccao robusta v2







