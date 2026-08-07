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
NOME_MODELO_SFACE = "face_recognition_sface_2021dec.onnx"
URL_MODELO_SFACE = (
    "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/"
    "models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
)
# Os recortes vÃªm do MediaPipe (sem os cinco marcos usados pelo alinhamento
# nativo do SFace). Em vÃ­deo real, perfis da mesma pessoa ficam por volta de
# 0.50; 0.55 separava a mesma pessoa em duas identidades. O recorte facial
# justo reduz a influÃªncia do cenÃ¡rio e permite este limiar conservador.
LIMIAR_IDENTIDADE_SFACE = 0.47


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
    fps = fps if fps and fps > 0 else 30.0
    tamanho_faixa = max(1, int(max(1.0, limite_minutos) * 60 * fps))
    lote = max(6, min(8, int(max_amostras // 4) or 6))
    rodadas, usados = [], set()
    inicio = 0
    while inicio < total:
        fim = min(total, inicio + tamanho_faixa)
        alvos = []
        for valor in np.linspace(inicio, max(inicio, fim - 1), lote, dtype=int):
            frame = int(valor)
            if frame not in usados:
                usados.add(frame)
                alvos.append(frame)
        if alvos:
            rodadas.append(alvos)
        inicio = fim
    return rodadas


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
                    deteccoes.append({
                        "posicao_x": rosto["x"],
                        "posicao_y": rosto["y"],
                        "fonte": rosto.get("fonte", "mediapipe"),
                        "confianca": rosto.get("confianca", 0.0),
                        "recorte": recorte,
                        "recorte_identidade": recorte_identidade,
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
            if _busca_esta_estavel(historico, 3):
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
        if 0.45 <= proporcao <= 1.8:
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
    if not os.path.isfile(caminho) or os.path.getsize(caminho) < 30_000_000:
        try:
            import urllib.request
            _print_seguro("   Baixando modelo de reconhecimento facial (37 MB)...")
            temporario = caminho + ".download"
            urllib.request.urlretrieve(URL_MODELO_SFACE, temporario)
            os.replace(temporario, caminho)
        except Exception as erro:
            LOGGER.warning("SFace indisponÃ­vel; usando agrupamento por posiÃ§Ã£o: %s", erro)
            try:
                if os.path.exists(caminho + ".download"):
                    os.remove(caminho + ".download")
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


def _agrupar_por_identidade(
    deteccoes: list,
    reconhecedor,
    total_amostras: int,
    limiar: float = LIMIAR_IDENTIDADE_SFACE,
) -> list:
    """Agrupa rostos pelo embedding SFace, independentemente da cÃ¢mera/lado."""
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
    minimo_frames = max(2, int(np.ceil(max(1, total_amostras) * 0.12)))
    grupos = [g for g in grupos if len(g["frames"]) >= minimo_frames]
    grupos.sort(key=lambda g: float(np.mean([d["posicao_x"] for d in g["deteccoes"]])))

    pessoas = []
    for grupo in grupos:
        detecs = grupo["deteccoes"]
        melhor = _escolher_melhor_preview(detecs)
        preview = cv2.resize(melhor.get("recorte_identidade", melhor["recorte"]), (200, 200), interpolation=cv2.INTER_LANCZOS4)
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







