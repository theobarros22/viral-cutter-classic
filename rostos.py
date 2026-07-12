"""
rostos.py
---------
Detecta rostos no vídeo, extrai uma imagem de preview de cada pessoa
e permite que o usuário escolha quem priorizar no enquadramento.

Como funciona:
1. Analisa frames do vídeo com MediaPipe
2. Agrupa rostos similares (mesma pessoa aparecendo em frames diferentes)
3. Extrai a melhor foto de cada pessoa detectada
4. Retorna lista de pessoas com preview e posição média na tela
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
    O vídeo não pôde ser decodificado — nenhum quadro foi lido.

    Quase sempre significa que o upload ainda não terminou (arquivos grandes
    levam minutos) ou que o arquivo está corrompido/incompleto. É diferente de
    "li o vídeo e não achei rosto nenhum" — esse caso continua retornando [].
    """


MSG_VIDEO_ILEGIVEL = (
    "⏳ Não consegui ler nenhum quadro do vídeo. Isso quase sempre significa "
    "que o upload ainda NÃO terminou (arquivos grandes, de vários GB, levam "
    "minutos) ou que o arquivo está corrompido. Aguarde o upload chegar a 100% "
    "e clique em DETECTAR PESSOAS novamente."
)

# Abaixo disso, a diferença de movimento entre os rostos é ruído de
# compressão/iluminação, não fala real — comum quando um microfone de mesa
# cobre a boca e a região analisada mal muda de um frame pro outro.
LIMIAR_MOVIMENTO_LABIAL = 4.0
NOME_MODELO_SFACE = "face_recognition_sface_2021dec_int8bq.onnx"
URL_MODELO_SFACE = (
    "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/"
    "models/face_recognition_sface/face_recognition_sface_2021dec_int8bq.onnx"
)
# Os recortes vêm do MediaPipe (sem os cinco marcos usados pelo alinhamento
# nativo do SFace). Em vídeo real, perfis da mesma pessoa ficam por volta de
# 0.50; 0.55 separava a mesma pessoa em duas identidades. O recorte facial
# justo reduz a influência do cenário e permite este limiar conservador.
LIMIAR_IDENTIDADE_SFACE = 0.47


def _print_seguro(mensagem) -> None:
    """Imprime logs sem derrubar o processamento em console Windows CP1252."""
    try:
        print(mensagem)
    except UnicodeEncodeError:
        print(str(mensagem).encode("ascii", errors="replace").decode("ascii"))


def _caminho_recurso(nome: str) -> str:
    """Localiza recursos tanto no código-fonte quanto no executável."""
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
    Corrige o mp4 movendo o moov atom para o início.
    Resolve o erro 'moov atom not found' do OpenCV.
    Retorna o caminho do arquivo corrigido (ou o original se não precisar).
    """
    # A maioria dos arquivos abre normalmente. Remuxar sempre duplicava vídeos
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


def detectar_pessoas_no_video(caminho_video: str, max_amostras: int = 30,
                               limite_minutos: float = 5.0) -> list:
    """
    Detecta e agrupa as pessoas que aparecem no vídeo.

    Analisa apenas os primeiros `limite_minutos` minutos — em podcasts,
    todos os participantes normalmente já apareceram nos primeiros 5 min.
    Muito mais rápido em vídeos longos.

    Retorna lista de dicts:
    [
        {
            "id": 0,
            "nome": "Pessoa 1",
            "posicao_x": 0.25,        # posição média X (0=esq, 1=dir)
            "lado": "esquerda",        # "esquerda", "direita" ou "centro"
            "preview_base64": "...",   # imagem do rosto em base64
            "preview_path": "...",     # caminho do arquivo de preview
            "n_aparicoes": 45,         # quantas vezes apareceu
        }
    ]
    """
    # Corrige o mp4 antes de abrir com OpenCV
    caminho_original = caminho_video
    caminho_video = _corrigir_mp4(caminho_video)
    detector = _inicializar_detector()
    if detector is None:
        _print_seguro("⚠️ Detector não disponível.")
        if caminho_video != caminho_original and os.path.exists(caminho_video):
            os.remove(caminho_video)
        return []

    cap = cv2.VideoCapture(caminho_video)
    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        largura = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        altura  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps     = cap.get(cv2.CAP_PROP_FPS) or 30.0

        # Limita a análise aos primeiros N minutos
        frame_limite = int(limite_minutos * 60 * fps)
        frames_analisar = min(total_frames, frame_limite)

        # Vai diretamente aos frames de amostra. Antes o programa decodificava
        # todos os frames intermediários, embora analisasse apenas algumas dezenas.
        amostras_reais = min(max_amostras, frames_analisar)
        alvos = np.linspace(0, max(0, frames_analisar - 1), amostras_reais, dtype=int)
        _print_seguro(f"🔍 Detectando pessoas nos primeiros {limite_minutos:.0f} min ({amostras_reais} amostras)...")

        # Guarda: lista de (posicao_x, frame_com_rosto_recortado)
        # frames_lidos distingue "vídeo ilegível/incompleto" (0 quadros lidos)
        # de "li o vídeo mas não há rosto" (quadros lidos, 0 detecções).
        deteccoes = []
        frames_lidos = 0
        for frame_idx in alvos:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
            ret, frame = cap.read()
            if not ret:
                continue
            frames_lidos += 1

            rostos = detectar_rostos_robusto(frame, detector)
            for rosto in rostos:
                x_centro = rosto["x"] * largura
                y_centro = rosto["y"] * altura
                w_rosto  = rosto["w"] * largura
                h_rosto  = rosto.get("h", rosto["w"]) * altura

                margem = 0.5
                x1 = max(0, int(x_centro - w_rosto * (0.5 + margem)))
                y1 = max(0, int(y_centro - h_rosto * (0.5 + margem)))
                x2 = min(largura, int(x_centro + w_rosto * (0.5 + margem)))
                y2 = min(altura, int(y_centro + h_rosto * (0.5 + margem)))

                recorte = frame[y1:y2, x1:x2]
                if recorte.size > 0:
                    rosto_x1 = max(0, int(x_centro - w_rosto * 0.55))
                    rosto_y1 = max(0, int(y_centro - h_rosto * 0.55))
                    rosto_x2 = min(largura, int(x_centro + w_rosto * 0.55))
                    rosto_y2 = min(altura, int(y_centro + h_rosto * 0.55))
                    deteccoes.append({
                        "posicao_x": rosto["x"],
                        "posicao_y": rosto["y"],
                        "fonte": rosto.get("fonte", "mediapipe"),
                        "confianca": rosto.get("confianca", 0.0),
                        "recorte": recorte,
                        "recorte_identidade": frame[rosto_y1:rosto_y2, rosto_x1:rosto_x2],
                        "frame_idx": int(frame_idx),
                    })

        # Alguns MP4/MOV grandes não permitem busca aleatória confiável pelo OpenCV.
        # Se nenhuma amostra funcionou, faz uma varredura curta e sequencial.
        if not deteccoes:
            _print_seguro("   🔄 Busca aleatória sem resultado; tentando varredura sequencial...")
            cap.release()
            cap = cv2.VideoCapture(caminho_video)
            limite_sequencial = min(total_frames, int(fps * 120))
            passo_sequencial = max(1, int(fps * 2))
            frame_idx = 0
            while cap.isOpened() and frame_idx < limite_sequencial:
                ret = cap.grab()
                if not ret:
                    break
                if frame_idx % passo_sequencial == 0:
                    ret, frame = cap.retrieve()
                    if ret:
                        frames_lidos += 1
                        for rosto in detectar_rostos_robusto(frame, detector):
                            x_centro = rosto["x"] * largura
                            y_centro = rosto["y"] * altura
                            w_rosto = rosto["w"] * largura
                            h_rosto = rosto.get("h", rosto["w"]) * altura
                            x1 = max(0, int(x_centro - w_rosto))
                            y1 = max(0, int(y_centro - h_rosto))
                            x2 = min(largura, int(x_centro + w_rosto))
                            y2 = min(altura, int(y_centro + h_rosto))
                            recorte = frame[y1:y2, x1:x2]
                            if recorte.size > 0:
                                rosto_x1 = max(0, int(x_centro - w_rosto * 0.55))
                                rosto_y1 = max(0, int(y_centro - h_rosto * 0.55))
                                rosto_x2 = min(largura, int(x_centro + w_rosto * 0.55))
                                rosto_y2 = min(altura, int(y_centro + h_rosto * 0.55))
                                deteccoes.append({
                                    "posicao_x": rosto["x"],
                                    "posicao_y": rosto["y"],
                                    "fonte": rosto.get("fonte", "mediapipe"),
                                    "confianca": rosto.get("confianca", 0.0),
                                    "recorte": recorte,
                                    "recorte_identidade": frame[rosto_y1:rosto_y2, rosto_x1:rosto_x2],
                                    "frame_idx": frame_idx,
                                })
                frame_idx += 1
    finally:
        cap.release()
        _fechar_detector(detector)
        if caminho_video != caminho_original and os.path.exists(caminho_video):
            try:
                os.remove(caminho_video)
            except OSError:
                pass

    # Nenhum quadro decodificado → vídeo incompleto (upload em andamento) ou
    # corrompido. Sinaliza com clareza em vez de reportar "nenhuma pessoa".
    if frames_lidos == 0:
        _print_seguro(MSG_VIDEO_ILEGIVEL)
        raise VideoIlegivelError(MSG_VIDEO_ILEGIVEL)

    reconhecedor = _inicializar_reconhecedor_facial()
    deteccoes = _filtrar_candidatos_pessoas(
        deteccoes,
        amostras_reais,
        exigir_persistencia_por_lado=(reconhecedor is None),
    )
    if not deteccoes:
        _print_seguro("⚠️ Nenhum rosto detectado.")
        return []

    # Com SFace, a mesma pessoa continua sendo uma identidade mesmo quando
    # cortes de câmera a movem da esquerda para o centro ou para a direita.
    pessoas = (
        _agrupar_por_identidade(deteccoes, reconhecedor, amostras_reais)
        if reconhecedor is not None
        else _agrupar_por_posicao(deteccoes)
    )

    _print_seguro(f"✅ {len(pessoas)} pessoa(s) identificada(s) no vídeo.")
    return pessoas


def _filtrar_candidatos_pessoas(
    deteccoes: list,
    total_amostras: int,
    exigir_persistencia_por_lado: bool = True,
) -> list:
    """Remove objetos do cenário antes de criar a lista de participantes.

    Uma pessoa real precisa aparecer em mais de um frame e, em podcasts,
    normalmente tem o centro do rosto entre 28% e 78% da altura. TV, bustos
    em estante e objetos sobre a mesa costumam ficar fora dessa faixa.

    Se a composição for atípica, detecções confirmadas pelo MediaPipe ainda
    são aceitas; o Haar, mais sujeito a falsos positivos, nunca é usado fora
    da zona humana sem confirmação do MediaPipe.
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
    if not os.path.isfile(caminho) or os.path.getsize(caminho) < 1_000_000:
        try:
            import urllib.request
            _print_seguro("   Baixando modelo de reconhecimento facial (10 MB)...")
            temporario = caminho + ".download"
            urllib.request.urlretrieve(URL_MODELO_SFACE, temporario)
            os.replace(temporario, caminho)
        except Exception as erro:
            LOGGER.warning("SFace indisponível; usando agrupamento por posição: %s", erro)
            try:
                if os.path.exists(caminho + ".download"):
                    os.remove(caminho + ".download")
            except OSError:
                pass
            return None

    try:
        return cv2.FaceRecognizerSF.create(caminho, "")
    except Exception as erro:
        LOGGER.warning("Falha ao carregar SFace; usando agrupamento por posição: %s", erro)
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


def _escolher_melhor_preview(deteccoes: list):
    """Escolhe um rosto nítido sem favorecer caixas gigantes ou vazias."""
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
        # demais e conter cenário preto em vez do participante.
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


def _agrupar_por_identidade(
    deteccoes: list,
    reconhecedor,
    total_amostras: int,
    limiar: float = LIMIAR_IDENTIDADE_SFACE,
) -> list:
    """Agrupa rostos pelo embedding SFace, independentemente da câmera/lado."""
    grupos = []
    for det in sorted(deteccoes, key=lambda d: int(d.get("frame_idx", 0))):
        recorte_identidade = det.get("recorte_identidade", det["recorte"])
        embedding = _extrair_embedding_facial(recorte_identidade, reconhecedor)
        if embedding is None:
            continue

        melhor_grupo = None
        melhor_score = -1.0
        frame_idx = int(det.get("frame_idx", -1))
        for grupo in grupos:
            # Duas faces no mesmo frame são necessariamente pessoas distintas.
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
            # Limita memória sem perder variedade de poses.
            if len(melhor_grupo["embeddings"]) < 8:
                melhor_grupo["embeddings"].append(embedding)
        else:
            grupos.append({
                "deteccoes": [det],
                "embeddings": [embedding],
                "frames": {frame_idx},
            })

    minimo_frames = max(2, min(4, int(np.ceil(max(1, total_amostras) * 0.10))))
    grupos = [g for g in grupos if len(g["frames"]) >= minimo_frames]
    grupos.sort(key=lambda g: float(np.mean([d["posicao_x"] for d in g["deteccoes"]])))

    pessoas = []
    for grupo in grupos:
        detecs = grupo["deteccoes"]
        melhor = _escolher_melhor_preview(detecs)
        preview = cv2.resize(melhor["recorte"], (200, 200), interpolation=cv2.INTER_LANCZOS4)
        _, buffer = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 85])
        pos_x_media = float(np.mean([d["posicao_x"] for d in detecs]))
        lado = "esquerda" if pos_x_media < 0.4 else ("direita" if pos_x_media > 0.6 else "centro")
        pessoas.append({
            "id": len(pessoas),
            "nome": f"Pessoa {len(pessoas) + 1} ({lado})",
            "posicao_x": pos_x_media,
            "lado": lado,
            "preview_base64": base64.b64encode(buffer).decode("utf-8"),
            "n_aparicoes": len(detecs),
            "recorte_cv2": preview,
        })
    return pessoas


def _agrupar_por_posicao(deteccoes: list, limiar_agrupamento: float = 0.25) -> list:
    """
    Agrupa detecções de rostos por posição X para identificar pessoas distintas.

    Estratégia simples e eficaz para podcasts:
    - Rostos no lado esquerdo (x < 0.4) → Pessoa A
    - Rostos no lado direito (x > 0.6) → Pessoa B
    - Rostos no centro (0.4-0.6) → pode ser plano geral ou terceira pessoa
    """
    grupos = {}

    for det in deteccoes:
        x = det["posicao_x"]

        # Define o grupo baseado na posição X
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
        # Pega o melhor recorte (maior área)
        melhor = max(detecs, key=lambda d: d["recorte"].shape[0] * d["recorte"].shape[1])
        recorte = melhor["recorte"]

        # Redimensiona para preview padronizado (200x200)
        preview = cv2.resize(recorte, (200, 200), interpolation=cv2.INTER_LANCZOS4)

        # Converte para base64 para exibir no Gradio
        _, buffer = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 85])
        preview_b64 = base64.b64encode(buffer).decode('utf-8')

        # Posição média X desse grupo
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
    Salva os previews das pessoas em arquivos temporários.
    Retorna a lista de pessoas com o campo 'preview_path' preenchido.
    """
    os.makedirs(pasta_temp, exist_ok=True)

    for p in pessoas:
        caminho = os.path.join(pasta_temp, f"pessoa_{p['id']}.jpg")
        if "recorte_cv2" in p:
            cv2.imwrite(caminho, p["recorte_cv2"])
            p["preview_path"] = caminho

    return pessoas


def detectar_quem_fala_por_frame(
    caminho_video: str,
    pessoas: list,
    intervalo_frames: int = 5,
    intervalos_frames: list = None,
    analisar_audio: bool = True,
) -> list:
    """
    Detecta quem está falando em cada frame do vídeo.

    Combina:
    - Posição dos rostos detectados
    - Análise de movimento labial (variação na região da boca)
    - Energia do áudio por janela de tempo

    Retorna lista com posição_x do falante para cada frame.
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

        _print_seguro(f"🎤 Detectando quem fala em {total_frames} frames...")

        energia_audio = (
            _analisar_energia_audio(caminho_video, fps, total_frames)
            if analisar_audio else [1.0] * total_frames
        )

        resultado = [None] * total_frames
        frame_anterior = None
        ultimo_falante_x = None

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

    # Interpola frames não analisados
    resultado = _interpolar_falante(resultado, total_frames)

    _print_seguro(f"✅ Detecção de fala concluída!")
    return resultado


def _detectar_movimento_labial(
    frame_atual, frame_anterior, rostos: list,
    largura: int, altura: int
) -> float:
    """
    Detecta qual rosto tem mais movimento na região da boca.
    Usa diferença entre frames consecutivos na parte inferior do rosto.
    Retorna a posição X do rosto com mais movimento (quem está falando).

    Se nenhum rosto atinge LIMIAR_MOVIMENTO_LABIAL, o resultado é ambíguo
    (ex.: microfone cobrindo a boca) — retorna None em vez de cair sempre
    no primeiro rosto da lista, o que enviesaria sistematicamente a detecção
    de fala para o mesmo lado.
    """
    if frame_anterior is None or not rostos:
        return rostos[0]["x"] if rostos else None

    max_movimento = 0
    falante_x = None

    for rosto in rostos:
        # Região da boca: 60-90% da altura do rosto
        x_c = rosto["x"] * largura
        y_c = rosto["y"] * altura
        w   = rosto["w"] * largura
        h   = rosto.get("h", rosto["w"]) * altura

        # Recorte da região da boca
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

        # Calcula diferença entre frames (movimento)
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
    """Analisa energia do áudio e retorna valor por frame."""
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
            # Lê uma pequena janela por vez. Antes carregava todo o áudio na
            # memória, chegando facilmente a centenas de MB em podcasts longos.
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


def _interpolar_falante(posicoes: list, total_frames: int) -> list:
    """Preenche frames sem detecção mantendo o último falante conhecido."""
    resultado = list(posicoes)
    ultimo = 0.5

    for i in range(total_frames):
        if resultado[i] is not None:
            ultimo = resultado[i]
        else:
            resultado[i] = ultimo

    return resultado


# ── MediaPipe helpers ─────────────────────────────────────────────────────────

def _inicializar_detector():
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
            # 0.35 em vez de 0.5 — rostos pequenos em plano aberto têm
            # confiança mais baixa; 0.5 deixava muita gente sem detectar
            min_detection_confidence=0.35
        )
        obj = mp_vision.FaceDetector.create_from_options(options)
        mediapipe_detector = {"tipo": "novo", "obj": obj}
        _print_seguro("Detector MediaPipe Tasks carregado.")
    except Exception as erro:
        erros.append(f"MediaPipe Tasks: {erro}")
        try:
            import mediapipe as mp
            # model_selection=1 = full-range (rostos longe da câmera)
            obj = mp.solutions.face_detection.FaceDetection(
                model_selection=1, min_detection_confidence=0.35
            )
            mediapipe_detector = {"tipo": "antigo", "obj": obj}
            _print_seguro("Detector MediaPipe full-range carregado.")
        except Exception as erro_antigo:
            erros.append(f"MediaPipe Solutions: {erro_antigo}")

    # Fallback independente do MediaPipe. Os classificadores fazem parte do
    # OpenCV e funcionam também dentro do executável.
    haar = None
    try:
        caminho_haar = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        obj_haar = cv2.CascadeClassifier(caminho_haar)
        if not obj_haar.empty():
            haar = obj_haar
    except Exception as erro:
        erros.append(f"OpenCV Haar: {erro}")

    if mediapipe_detector is None and haar is None:
        mensagem = " | ".join(erros) or "nenhum detector disponível"
        LOGGER.error("Falha ao inicializar detectores: %s", mensagem)
        _print_seguro(f"   ⚠️ Falha ao carregar detector facial: {mensagem}")
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
    Detecção robusta para PLANO ABERTO (rostos pequenos).

    O modelo do MediaPipe é de curto alcance — em plano aberto de podcast
    os rostos ficam pequenos demais e ele falha. Esta função tenta 3 vezes
    usando SÓ o MediaPipe (nunca o Haar aqui — ver motivo abaixo):

    1. Frame original (rápido, funciona em close)
    2. Frame ampliado 2x (rostos pequenos ficam detectáveis)
    3. Metades esquerda/direita ampliadas 3x em largura E altura
       (pessoas coladas nas bordas, longe do centro)

    O Haar cascade (OpenCV) só é usado se o MediaPipe não estiver disponível.
    Quando o MediaPipe funciona mas não acha ninguém após todas as escalas,
    o resultado correto é vazio. O Haar confunde padrões do cenário (parede,
    TV, estatueta) com rostos e já gerou enquadramentos mirando em decoração.

    Retorna lista no mesmo formato de _detectar_rostos_frame
    (coordenadas normalizadas 0-1 relativas ao frame ORIGINAL).
    """
    mp_detector = detector.get("mediapipe") if isinstance(detector, dict) else detector

    h, w = frame.shape[:2]
    resultado_mp = []

    # Tentativa 1 — frame original, MediaPipe puro. Não retorna cedo: uma
    # pessoa próxima pode aparecer aqui enquanto outra, menor, só surge no zoom.
    if mp_detector:
        resultado_mp.extend(_detectar_rostos_frame(frame, mp_detector))

    # Tentativa 2 — amplia o frame 2x (coordenadas normalizadas não mudam)
    if mp_detector:
        try:
            ampliado = cv2.resize(frame, (w * 2, h * 2), interpolation=cv2.INTER_LINEAR)
            resultado_mp.extend(_detectar_rostos_frame(ampliado, mp_detector))
        except Exception:
            pass

        # Tentativa 3 — metades esquerda e direita, ampliadas 3x em largura
        # E altura (zoom só na largura não aumenta rostos pequenos o
        # suficiente; testado empiricamente em plano aberto multicâmera).
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

    # MediaPipe respondeu normalmente, mas não encontrou rosto em nenhuma
    # escala. Não substitui esse resultado por um palpite ruidoso do Haar.
    if mp_detector is not None:
        return []

    # Último recurso apenas quando o MediaPipe nem sequer pôde ser carregado.
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
        LOGGER.warning("Erro durante detecção facial: %s", erro)
    return _limpar_deteccoes(rostos)


def _detectar_rostos_haar(frame, classificador) -> list:
    """Fallback OpenCV para quando MediaPipe falhar ou não achar rostos."""
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
    """Remove caixas inválidas e duplicadas produzidas pelos fallbacks."""
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
        if limpo["w"] <= 0 or limpo["h"] <= 0:
            continue
        if any(_deteccoes_sobrepostas(limpo, existente) for existente in resultado):
            continue
        resultado.append(limpo)
    return resultado


def _deteccoes_sobrepostas(a: dict, b: dict) -> bool:
    """Considera duplicadas caixas com grande sobreposição ou centro próximo."""
    ax1, ay1 = a["x"] - a["w"] / 2, a["y"] - a["h"] / 2
    ax2, ay2 = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
    bx1, by1 = b["x"] - b["w"] / 2, b["y"] - b["h"] / 2
    bx2, by2 = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    uniao = a["w"] * a["h"] + b["w"] * b["h"] - inter
    iou = inter / uniao if uniao > 0 else 0.0
    # Em detecção multi-escala, a mesma face pode voltar como uma caixa
    # grande no frame inteiro e outra menor na metade ampliada. Usa a maior
    # caixa como referência; pessoas realmente distintas têm centros muito
    # mais afastados em relação ao próprio tamanho facial.
    centro_proximo = (
        abs(a["x"] - b["x"]) < max(0.04, max(a["w"], b["w"]) * 0.50)
        and abs(a["y"] - b["y"]) < max(0.04, max(a["h"], b["h"]) * 0.40)
    )
    return iou >= 0.20 or centro_proximo
# fim do arquivo — deteccao robusta v2
