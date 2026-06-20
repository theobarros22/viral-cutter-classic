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


LOGGER = logging.getLogger("ViralCutter.rostos")


def _caminho_recurso(nome: str) -> str:
    """Localiza recursos tanto no código-fonte quanto no executável."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome)


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
        print("⚠️ Detector não disponível.")
        if caminho_video != caminho_original and os.path.exists(caminho_video):
            os.remove(caminho_video)
        return []

    cap = cv2.VideoCapture(caminho_video)
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
    print(f"🔍 Detectando pessoas nos primeiros {limite_minutos:.0f} min ({amostras_reais} amostras)...")

    # Guarda: lista de (posicao_x, frame_com_rosto_recortado)
    deteccoes = []
    for frame_idx in alvos:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
        ret, frame = cap.read()
        if not ret:
            continue

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
                deteccoes.append({
                    "posicao_x": rosto["x"],
                    "posicao_y": rosto["y"],
                    "recorte": recorte,
                    "frame_idx": int(frame_idx),
                })

    # Alguns MP4/MOV grandes não permitem busca aleatória confiável pelo OpenCV.
    # Se nenhuma amostra funcionou, faz uma varredura curta e sequencial.
    if not deteccoes:
        print("   🔄 Busca aleatória sem resultado; tentando varredura sequencial...")
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
                            deteccoes.append({
                                "posicao_x": rosto["x"],
                                "posicao_y": rosto["y"],
                                "recorte": recorte,
                                "frame_idx": frame_idx,
                            })
            frame_idx += 1

    cap.release()
    _fechar_detector(detector)
    if caminho_video != caminho_original and os.path.exists(caminho_video):
        os.remove(caminho_video)

    if not deteccoes:
        print("⚠️ Nenhum rosto detectado.")
        return []

    # Agrupa rostos por posição X (esquerda vs direita)
    pessoas = _agrupar_por_posicao(deteccoes)

    print(f"✅ {len(pessoas)} pessoa(s) identificada(s) no vídeo.")
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
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = fps if fps and fps > 0 else 30.0
    largura = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    altura  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"🎤 Detectando quem fala em {total_frames} frames...")

    # Carrega análise de energia do áudio
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
                # Sem rosto → mantém último falante
                resultado[frame_idx] = ultimo_falante_x

            elif len(rostos) == 1:
                # Só 1 pessoa → é ela falando
                ultimo_falante_x = rostos[0]["x"]
                resultado[frame_idx] = ultimo_falante_x

            else:
                # 2+ pessoas → detecta quem está com a boca mais aberta
                # (movimento labial = variação na parte inferior do rosto)
                melhor_falante = _detectar_movimento_labial(
                    frame, frame_anterior, rostos, largura, altura
                )

                # Combina com energia do áudio
                energia = energia_audio[frame_idx] if frame_idx < len(energia_audio) else 0.5

                if melhor_falante is not None and energia > 0.3:
                    ultimo_falante_x = melhor_falante
                    resultado[frame_idx] = melhor_falante
                else:
                    resultado[frame_idx] = ultimo_falante_x

            # Guarda apenas o último frame realmente analisado.
            frame_anterior = frame

    cap.release()
    _fechar_detector(detector)

    # Interpola frames não analisados
    resultado = _interpolar_falante(resultado, total_frames)

    print(f"✅ Detecção de fala concluída!")
    return resultado


def _detectar_movimento_labial(
    frame_atual, frame_anterior, rostos: list,
    largura: int, altura: int
) -> float:
    """
    Detecta qual rosto tem mais movimento na região da boca.
    Usa diferença entre frames consecutivos na parte inferior do rosto.
    Retorna a posição X do rosto com mais movimento (quem está falando).
    """
    if frame_anterior is None or not rostos:
        return rostos[0]["x"] if rostos else None

    max_movimento = 0
    falante_x = rostos[0]["x"]

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

        modelo_path = _caminho_recurso("face_detector.tflite")
        if not os.path.exists(modelo_path):
            import urllib.request
            print("⬇️ Baixando modelo de detecção...")
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
        print("   ✅ Detector MediaPipe Tasks carregado.")
    except Exception as erro:
        erros.append(f"MediaPipe Tasks: {erro}")
        try:
            import mediapipe as mp
            # model_selection=1 = full-range (rostos longe da câmera)
            obj = mp.solutions.face_detection.FaceDetection(
                model_selection=1, min_detection_confidence=0.35
            )
            mediapipe_detector = {"tipo": "antigo", "obj": obj}
            print("   ✅ Detector MediaPipe full-range carregado.")
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
        print(f"   ⚠️ Falha ao carregar detector facial: {mensagem}")
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
    os rostos ficam pequenos demais e ele falha. Esta função tenta 3 vezes:

    1. Frame original (rápido, funciona em close)
    2. Frame ampliado 2x (rostos pequenos ficam detectáveis)
    3. Metades esquerda/direita ampliadas (pessoas nas bordas do quadro)

    Retorna lista no mesmo formato de _detectar_rostos_frame
    (coordenadas normalizadas 0-1 relativas ao frame ORIGINAL).
    """
    # Tentativa 1 — frame original
    rostos = _detectar_rostos_frame(frame, detector)
    if rostos:
        return rostos

    h, w = frame.shape[:2]

    # Tentativa 2 — amplia o frame 2x (coordenadas normalizadas não mudam)
    try:
        ampliado = cv2.resize(frame, (w * 2, h * 2), interpolation=cv2.INTER_LINEAR)
        rostos = _detectar_rostos_frame(ampliado, detector)
        if rostos:
            return rostos
    except Exception:
        pass

    # Tentativa 3 — metades esquerda e direita, cada uma ampliada
    # (pega pessoas coladas nas bordas, longe do centro)
    try:
        resultado = []
        metades = [
            (0.0, frame[:, : w // 2]),       # metade esquerda
            (0.5, frame[:, w // 2 :]),       # metade direita
        ]
        for offset_x, metade in metades:
            metade_grande = cv2.resize(metade, (w, h), interpolation=cv2.INTER_LINEAR)
            detectados = _detectar_rostos_frame(metade_grande, detector)
            for r in detectados:
                # Converte coordenadas da metade de volta para o frame inteiro
                resultado.append({
                    "x": offset_x + r["x"] * 0.5,
                    "y": r["y"],
                    "w": r["w"] * 0.5,
                    "h": r["h"],
                })
        return resultado
    except Exception:
        return []


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
            }
            for x, y, largura, altura in caixas
        ])
    except Exception as erro:
        LOGGER.warning("Erro no fallback OpenCV Haar: %s", erro)
        return []


def _limpar_deteccoes(rostos: list) -> list:
    """Remove caixas inválidas e duplicadas produzidas pelos fallbacks."""
    resultado = []
    for rosto in rostos:
        limpo = {
            "x": max(0.0, min(1.0, float(rosto["x"]))),
            "y": max(0.0, min(1.0, float(rosto["y"]))),
            "w": max(0.0, min(1.0, float(rosto["w"]))),
            "h": max(0.0, min(1.0, float(rosto.get("h", rosto["w"])))),
        }
        if limpo["w"] <= 0 or limpo["h"] <= 0:
            continue
        if any(abs(limpo["x"] - existente["x"]) < 0.04 and
               abs(limpo["y"] - existente["y"]) < 0.04 for existente in resultado):
            continue
        resultado.append(limpo)
    return resultado
# fim do arquivo — deteccao robusta v2
