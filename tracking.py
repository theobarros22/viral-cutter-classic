"""
tracking.py
-----------
Detecta rostos e retorna posições suavizadas para o reframe.

Estratégia "zona morta":
- Se o rosto está perto do centro → câmera fica parada
- Só move quando o rosto sai muito do centro
- Movimento suave e gradual, sem tremido
"""

import cv2
import numpy as np


def detectar_posicoes_rosto(caminho_video: str, intervalo_frames: int = 5) -> list:
    """
    Detecta rostos no vídeo e retorna posições X suavizadas.
    Usa zona morta central para evitar movimentos desnecessários.
    """

    detector = None
    usar_mediapipe_novo = False

    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
        import urllib.request
        import os

        modelo_path = "face_detector.tflite"
        if not os.path.exists(modelo_path):
            print("⬇️ Baixando modelo de detecção de rosto...")
            url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
            urllib.request.urlretrieve(url, modelo_path)

        base_options = mp_python.BaseOptions(model_asset_path=modelo_path)
        options = mp_vision.FaceDetectorOptions(
            base_options=base_options,
            min_detection_confidence=0.5
        )
        detector = mp_vision.FaceDetector.create_from_options(options)
        usar_mediapipe_novo = True
        print("✅ MediaPipe novo detectado (0.10+)")

    except Exception:
        try:
            import mediapipe as mp
            mp_face = mp.solutions.face_detection
            detector = mp_face.FaceDetection(
                model_selection=1,
                min_detection_confidence=0.5
            )
            usar_mediapipe_novo = False
            print("✅ MediaPipe antigo detectado")
        except Exception as e2:
            print(f"⚠️ MediaPipe não disponível: {e2}. Usando crop central.")
            detector = None

    if detector is None:
        cap = cv2.VideoCapture(caminho_video)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        return [0.5] * total

    cap = cv2.VideoCapture(caminho_video)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"🎯 Analisando {total_frames} frames para detectar rostos...")

    # Posições brutas detectadas (antes de qualquer suavização)
    posicoes_brutas = [None] * total_frames
    frame_atual = 0
    ultima_posicao_x = 0.5

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_atual % intervalo_frames == 0:
            try:
                if usar_mediapipe_novo:
                    import mediapipe as mp
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(
                        image_format=mp.ImageFormat.SRGB,
                        data=frame_rgb
                    )
                    result = detector.detect(mp_image)
                    if result.detections:
                        det = result.detections[0]
                        bbox = det.bounding_box
                        h, w = frame.shape[:2]
                        centro_x = (bbox.origin_x + bbox.width / 2) / w
                        ultima_posicao_x = max(0.0, min(1.0, centro_x))
                else:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    resultado = detector.process(frame_rgb)
                    if resultado.detections:
                        melhor = max(
                            resultado.detections,
                            key=lambda d: d.location_data.relative_bounding_box.width
                        )
                        bbox = melhor.location_data.relative_bounding_box
                        centro_x = bbox.xmin + (bbox.width / 2)
                        ultima_posicao_x = max(0.0, min(1.0, centro_x))
            except Exception:
                pass

            posicoes_brutas[frame_atual] = ultima_posicao_x

        frame_atual += 1

    cap.release()
    try:
        detector.close()
    except Exception:
        pass

    # Interpola frames não analisados
    posicoes_brutas = _interpolar_posicoes(posicoes_brutas, total_frames)

    # Aplica zona morta + suavização forte
    posicoes_finais = _aplicar_zona_morta(posicoes_brutas)

    print(f"✅ Tracking concluído! {total_frames} frames analisados.")
    return posicoes_finais


def _aplicar_zona_morta(posicoes: list, zona: float = 0.12, velocidade: float = 0.02) -> list:
    """
    Estratégia de câmera profissional:

    - zona: tamanho da zona morta central (0.12 = 12% do frame)
      Se o rosto estiver a menos de 12% do centro → câmera não move
    - velocidade: quão rápido a câmera se move quando precisa (0.02 = 2% por frame)
      Valor baixo = movimento muito suave e gradual

    Como funciona:
    1. A câmera tem uma posição atual (começa no centro = 0.5)
    2. A cada frame, vê onde está o rosto
    3. Se o rosto está dentro da zona morta → não faz nada
    4. Se o rosto saiu da zona → move a câmera LENTAMENTE na direção certa
    5. Resultado: câmera estável, só move quando realmente necessário
    """
    if not posicoes:
        return posicoes

    resultado = list(posicoes)
    posicao_camera = 0.5  # câmera começa no centro

    for i, pos_rosto in enumerate(posicoes):
        # Distância entre o rosto e o centro da câmera atual
        distancia = pos_rosto - posicao_camera

        # Se o rosto está dentro da zona morta, câmera fica parada
        if abs(distancia) <= zona:
            resultado[i] = posicao_camera
        else:
            # Move a câmera suavemente na direção do rosto
            # Só move o excesso além da zona morta, e ainda assim devagar
            excesso = distancia - (zona * (1 if distancia > 0 else -1))
            posicao_camera += excesso * velocidade
            posicao_camera = max(0.0, min(1.0, posicao_camera))
            resultado[i] = posicao_camera

    # Suavização final leve para eliminar qualquer micro-tremido residual
    resultado = suavizar_posicoes(resultado, janela=15)

    return resultado


def _interpolar_posicoes(posicoes: list, total_frames: int) -> list:
    """Preenche frames sem detecção com interpolação linear."""
    resultado = list(posicoes)

    primeiro_valido = next((i for i, p in enumerate(resultado) if p is not None), None)
    if primeiro_valido is None:
        return [0.5] * total_frames

    for i in range(primeiro_valido):
        resultado[i] = resultado[primeiro_valido]

    ultimo_valido = next((i for i, p in enumerate(reversed(resultado)) if p is not None), None)
    if ultimo_valido is not None:
        ultimo_valido = total_frames - 1 - ultimo_valido
        for i in range(ultimo_valido + 1, total_frames):
            resultado[i] = resultado[ultimo_valido]

    i = 0
    while i < total_frames:
        if resultado[i] is None:
            proximo = i + 1
            while proximo < total_frames and resultado[proximo] is None:
                proximo += 1
            if proximo < total_frames:
                val_ant = resultado[i - 1]
                val_prox = resultado[proximo]
                passos = proximo - (i - 1)
                for j in range(i, proximo):
                    frac = (j - (i - 1)) / passos
                    resultado[j] = val_ant + frac * (val_prox - val_ant)
        i += 1

    return resultado


def suavizar_posicoes(posicoes: list, janela: int = 30) -> list:
    """Suaviza posições com média móvel para evitar tremido."""
    if not posicoes:
        return posicoes

    arr = np.array(posicoes, dtype=float)
    kernel = np.ones(janela) / janela
    suavizado = np.convolve(arr, kernel, mode='same')

    metade = janela // 2
    suavizado[:metade] = arr[:metade]
    suavizado[-metade:] = arr[-metade:]

    return suavizado.tolist()


def calcular_x_crop(posicao_x_rosto: float, largura_video: int, largura_crop: int) -> int:
    """Calcula onde começa o crop em X para centralizar no rosto."""
    centro_rosto_px = int(posicao_x_rosto * largura_video)
    x_inicio = centro_rosto_px - (largura_crop // 2)
    x_inicio = max(0, x_inicio)
    x_inicio = min(largura_video - largura_crop, x_inicio)
    return x_inicio
