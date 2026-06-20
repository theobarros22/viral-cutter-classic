"""
smart_cut.py
------------
Implementa os 3 modos de enquadramento inteligente:

Modo 1 — Tracking simples (1 pessoa)
  Já existia no tracking.py — segue o rosto com zona morta

Modo 2 — Smart Cut (2+ pessoas, câmera única)
  Detecta quem está falando e corta para esse rosto
  Como funciona:
    - MediaPipe detecta todos os rostos e suas posições X
    - Análise de energia do áudio detecta quando há fala ativa
    - Combina os dois: "quem está no lado com mais movimento labial"
    - Gera uma sequência de cortes: [pessoa_esquerda, pessoa_direita, ...]

Modo 3 — Split Screen (duas pessoas lado a lado)
  Divide o frame em duas metades verticais 9:16
  Cada metade mostra uma pessoa centralizada
"""

import cv2
import numpy as np
import subprocess
import json
import os


# ── Detecção de rostos múltiplos ──────────────────────────────────────────────

def detectar_rostos_multiplos(caminho_video: str, intervalo_frames: int = 10) -> dict:
    """
    Analisa o vídeo e detecta quantas pessoas aparecem e suas posições.

    Retorna:
        {
          "total_rostos": 2,
          "modo_sugerido": "smart_cut",  # ou "tracking" ou "split_screen"
          "posicoes_por_frame": [
              {"frame": 0, "rostos": [{"x": 0.25, "y": 0.5, "w": 0.15}, ...]},
              ...
          ]
        }
    """
    detector = _inicializar_detector()

    cap = cv2.VideoCapture(caminho_video)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    print(f"🔍 Analisando rostos em {total_frames} frames...")

    posicoes_por_frame = []
    contagem_rostos = []

    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % intervalo_frames == 0:
            rostos = _detectar_rostos_frame(frame, detector)
            posicoes_por_frame.append({
                "frame": frame_idx,
                "tempo": frame_idx / fps,
                "rostos": rostos
            })
            contagem_rostos.append(len(rostos))

        frame_idx += 1

    cap.release()
    _fechar_detector(detector)

    # Decide o modo baseado na quantidade média de rostos
    media_rostos = np.mean(contagem_rostos) if contagem_rostos else 1
    max_rostos = max(contagem_rostos) if contagem_rostos else 1

    if max_rostos >= 2:
        modo_sugerido = "smart_cut"
    else:
        modo_sugerido = "tracking"

    print(f"✅ Análise concluída: média {media_rostos:.1f} rostos | modo sugerido: {modo_sugerido}")

    return {
        "total_rostos": int(round(media_rostos)),
        "max_rostos": max_rostos,
        "modo_sugerido": modo_sugerido,
        "posicoes_por_frame": posicoes_por_frame,
        "fps": fps,
        "total_frames": total_frames
    }


def _detectar_rostos_frame(frame, detector) -> list:
    """Detecta todos os rostos num frame e retorna suas posições."""
    rostos = []
    h, w = frame.shape[:2]

    try:
        if detector is None:
            return rostos

        if isinstance(detector, dict) and detector.get("tipo") == "novo":
            import mediapipe as mp
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            result = detector["obj"].detect(mp_image)
            if result.detections:
                for det in result.detections:
                    bbox = det.bounding_box
                    cx = (bbox.origin_x + bbox.width / 2) / w
                    cy = (bbox.origin_y + bbox.height / 2) / h
                    bw = bbox.width / w
                    rostos.append({"x": cx, "y": cy, "w": bw})
        else:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            resultado = detector.process(frame_rgb)
            if resultado.detections:
                for det in resultado.detections:
                    bbox = det.location_data.relative_bounding_box
                    cx = bbox.xmin + bbox.width / 2
                    cy = bbox.ymin + bbox.height / 2
                    rostos.append({"x": cx, "y": cy, "w": bbox.width})
    except Exception:
        pass

    return rostos


def _inicializar_detector():
    """Inicializa o detector MediaPipe (novo ou antigo)."""
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        modelo_path = "face_detector.tflite"
        if not os.path.exists(modelo_path):
            import urllib.request
            url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
            urllib.request.urlretrieve(url, modelo_path)

        base_options = mp_python.BaseOptions(model_asset_path=modelo_path)
        options = mp_vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.5)
        obj = mp_vision.FaceDetector.create_from_options(options)
        return {"tipo": "novo", "obj": obj}
    except Exception:
        try:
            import mediapipe as mp
            return mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
        except Exception:
            return None


def _fechar_detector(detector):
    try:
        if isinstance(detector, dict):
            detector["obj"].close()
        else:
            detector.close()
    except Exception:
        pass


# ── Detecção de voz ativa ─────────────────────────────────────────────────────

def detectar_voz_ativa(caminho_video: str, janela_ms: int = 200) -> list:
    """
    Analisa o áudio e retorna momentos de fala ativa.

    Usa energia RMS do áudio — quando a energia está alta, alguém está falando.

    Retorna lista de dicts:
        [{"tempo": 1.2, "energia": 0.85, "falando": True}, ...]
    """
    print("🎤 Analisando áudio para detectar voz ativa...")

    # Extrai áudio como WAV usando FFmpeg
    caminho_audio = "_temp_audio_analise.wav"
    cmd = [
        "ffmpeg", "-y", "-i", caminho_video,
        "-ac", "1",           # mono
        "-ar", "16000",       # 16kHz
        "-vn",                # sem vídeo
        caminho_audio
    ]
    resultado = subprocess.run(cmd, capture_output=True)
    if resultado.returncode != 0 or not os.path.exists(caminho_audio):
        print("⚠️ Não foi possível extrair áudio. Usando distribuição uniforme.")
        return []

    try:
        # Lê o WAV manualmente (sem dependências extras)
        import wave
        import struct

        with wave.open(caminho_audio, 'rb') as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        # Converte bytes para array de floats
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        # Calcula energia RMS em janelas
        janela_samples = int(sr * janela_ms / 1000)
        resultados = []

        for i in range(0, len(samples) - janela_samples, janela_samples // 2):
            janela = samples[i:i + janela_samples]
            energia = float(np.sqrt(np.mean(janela ** 2)))
            tempo = i / sr
            resultados.append({"tempo": tempo, "energia": energia})

        # Normaliza e define threshold de fala
        if resultados:
            energias = [r["energia"] for r in resultados]
            threshold = np.percentile(energias, 40)  # 40% mais alto = fala ativa
            for r in resultados:
                r["falando"] = r["energia"] > threshold

        os.remove(caminho_audio)
        print(f"✅ Análise de áudio concluída: {len(resultados)} janelas")
        return resultados

    except Exception as e:
        print(f"⚠️ Erro na análise de áudio: {e}")
        if os.path.exists(caminho_audio):
            os.remove(caminho_audio)
        return []


# ── Smart Cut — modo principal ────────────────────────────────────────────────

def gerar_sequencia_smart_cut(analise_rostos: dict, analise_audio: list) -> list:
    """
    Combina análise de rostos + áudio para gerar sequência de cortes.

    Estratégia:
    1. Identifica pessoa da esquerda (x < 0.5) e da direita (x > 0.5)
    2. Sincroniza com momentos de fala ativa
    3. Gera sequência: [{"tempo_inicio": 0, "tempo_fim": 3.5, "foco_x": 0.25}, ...]
       onde foco_x é a posição X do rosto que deve estar no centro do crop

    Retorna lista de segmentos com qual pessoa focar em cada momento.
    """
    posicoes = analise_rostos["posicoes_por_frame"]
    fps = analise_rostos["fps"]

    if not posicoes:
        return []

    sequencia = []
    foco_atual = 0.5      # começa no centro
    tempo_ultimo_corte = 0
    duracao_minima_corte = 2.0  # segundos mínimos antes de cortar novamente

    for i, frame_info in enumerate(posicoes):
        tempo = frame_info["tempo"]
        rostos = frame_info["rostos"]

        if len(rostos) < 2:
            # Só 1 rosto visível — foca nele
            if rostos:
                foco_atual = rostos[0]["x"]
            sequencia.append({
                "tempo": tempo,
                "foco_x": foco_atual,
                "n_rostos": len(rostos)
            })
            continue

        # 2+ rostos — decide quem focar baseado no áudio
        # Ordena rostos por posição X (esquerda → direita)
        rostos_ord = sorted(rostos, key=lambda r: r["x"])

        # Acha a energia de áudio neste momento
        energia_neste_momento = _energia_no_tempo(analise_audio, tempo)

        # Alterna entre rostos com base em mudanças de energia
        # (quando energia sobe, provavelmente começou a falar alguém)
        if i > 0 and (tempo - tempo_ultimo_corte) >= duracao_minima_corte:
            energia_anterior = _energia_no_tempo(analise_audio, tempo - 0.5)
            if energia_neste_momento > energia_anterior * 1.3:
                # Houve aumento de energia — alterna o foco
                foco_atual = _alternar_foco(foco_atual, rostos_ord)
                tempo_ultimo_corte = tempo

        sequencia.append({
            "tempo": tempo,
            "foco_x": foco_atual,
            "n_rostos": len(rostos)
        })

    return sequencia


def _energia_no_tempo(analise_audio: list, tempo: float) -> float:
    """Retorna a energia do áudio num determinado momento."""
    if not analise_audio:
        return 0.5
    # Acha a janela mais próxima
    mais_proximo = min(analise_audio, key=lambda r: abs(r["tempo"] - tempo))
    return mais_proximo["energia"]


def _alternar_foco(foco_atual: float, rostos: list) -> float:
    """Alterna o foco para o outro rosto."""
    if len(rostos) < 2:
        return foco_atual
    # Se está focando na esquerda (x < 0.5), vai para a direita e vice-versa
    if foco_atual < 0.5:
        return rostos[-1]["x"]  # mais à direita
    else:
        return rostos[0]["x"]   # mais à esquerda


# ── Aplicar Smart Cut no vídeo ────────────────────────────────────────────────

def aplicar_smart_cut(
    caminho_entrada: str,
    caminho_saida: str,
    saida_w: int = 1080,
    saida_h: int = 1920,
    suavizacao: int = 45
) -> bool:
    """
    Aplica o Smart Cut no vídeo:
    - Detecta rostos múltiplos
    - Analisa quem está falando
    - Corta para a pessoa certa em cada momento

    Parâmetros:
        caminho_entrada: vídeo original
        caminho_saida: onde salvar
        saida_w, saida_h: resolução de saída
        suavizacao: suavidade das transições (maior = mais suave)
    """
    print("🎬 Iniciando Smart Cut...")

    # Análise
    analise_rostos = detectar_rostos_multiplos(caminho_entrada, intervalo_frames=15)
    analise_audio  = detectar_voz_ativa(caminho_entrada)
    sequencia      = gerar_sequencia_smart_cut(analise_rostos, analise_audio)

    if not sequencia:
        print("⚠️ Smart Cut sem dados. Usando tracking simples como fallback.")
        from tracking import detectar_posicoes_rosto, suavizar_posicoes
        posicoes = detectar_posicoes_rosto(caminho_entrada)
        return _processar_frames_com_posicoes(
            caminho_entrada, caminho_saida,
            posicoes, saida_w, saida_h
        )

    # Converte sequência para lista de posições por frame
    info = _obter_info_video(caminho_entrada)
    total_frames = info["total_frames"]
    fps = info["fps"]

    posicoes = _sequencia_para_posicoes(sequencia, total_frames, fps)

    # Suaviza para transições suaves
    from tracking import suavizar_posicoes
    posicoes = suavizar_posicoes(posicoes, janela=suavizacao)

    return _processar_frames_com_posicoes(
        caminho_entrada, caminho_saida,
        posicoes, saida_w, saida_h
    )


def _sequencia_para_posicoes(sequencia: list, total_frames: int, fps: float) -> list:
    """Converte sequência de cortes para lista de posições por frame."""
    posicoes = [0.5] * total_frames

    for i in range(len(sequencia)):
        frame_atual = int(sequencia[i]["tempo"] * fps)
        frame_prox  = int(sequencia[i + 1]["tempo"] * fps) if i + 1 < len(sequencia) else total_frames

        foco = sequencia[i]["foco_x"]
        for f in range(min(frame_atual, total_frames), min(frame_prox, total_frames)):
            posicoes[f] = foco

    return posicoes


def _processar_frames_com_posicoes(
    caminho_entrada, caminho_saida,
    posicoes, saida_w, saida_h
) -> bool:
    """Processa o vídeo frame a frame aplicando as posições de crop."""
    info = _obter_info_video(caminho_entrada)
    largura = info["largura"]
    altura  = info["altura"]
    fps     = info["fps"]
    total_frames = len(posicoes)

    # Calcula dimensão do crop
    nova_largura = int(altura * 9 / 16)
    if nova_largura % 2 != 0:
        nova_largura -= 1
    nova_altura = altura

    pasta_saida_dir = os.path.dirname(caminho_saida)
    video_sem_audio = os.path.join(pasta_saida_dir, "_smart_cut_temp.mp4")

    cap = cv2.VideoCapture(caminho_entrada)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(video_sem_audio, fourcc, fps, (saida_w, saida_h))

    print(f"🎬 Processando {total_frames} frames com Smart Cut...")
    frame_idx = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        pos_x = posicoes[frame_idx] if frame_idx < len(posicoes) else 0.5
        from tracking import calcular_x_crop
        x_crop = calcular_x_crop(pos_x, largura, nova_largura)

        frame_cortado = frame[0:nova_altura, x_crop:x_crop + nova_largura]
        frame_final = cv2.resize(frame_cortado, (saida_w, saida_h))
        writer.write(frame_final)
        frame_idx += 1

        if frame_idx % 150 == 0:
            pct = int((frame_idx / total_frames) * 100)
            print(f"   ⏳ {pct}% ({frame_idx}/{total_frames} frames)")

    cap.release()
    writer.release()

    # Junta com áudio original
    cmd = [
        "ffmpeg", "-y",
        "-i", video_sem_audio,
        "-i", caminho_entrada,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        caminho_saida
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)

    if os.path.exists(video_sem_audio):
        os.remove(video_sem_audio)

    return resultado.returncode == 0


# ── Split Screen ──────────────────────────────────────────────────────────────

def aplicar_split_screen(
    caminho_entrada: str,
    caminho_saida: str,
    qualidade: str = "1080p"
) -> bool:
    """
    Detecta as duas pessoas no vídeo e cria um split screen 9:16
    com cada pessoa centralizada no seu lado.

    Layout:
    ┌─────────┐
    │ Pessoa  │  ← metade superior (quem está à esquerda)
    │ Esq.    │
    ├─────────┤
    │ Pessoa  │  ← metade inferior (quem está à direita)
    │ Dir.    │
    └─────────┘
    """
    from reframe import RESOLUCOES, _ffmpeg_simples
    saida_w, saida_h = RESOLUCOES["9:16"].get(qualidade, (1080, 1920))
    metade_h = saida_h // 2

    print("🖥️ Criando Split Screen inteligente...")

    info = _obter_info_video(caminho_entrada)
    largura = info["largura"]
    altura  = info["altura"]
    fps     = info["fps"]

    # Detecta posição das pessoas para o split
    analise = detectar_rostos_multiplos(caminho_entrada, intervalo_frames=30)
    posicoes = analise["posicoes_por_frame"]

    # Acha posição média da pessoa da esquerda e da direita
    x_esq_list, x_dir_list = [], []
    for fp in posicoes:
        rostos = fp["rostos"]
        if len(rostos) >= 2:
            rostos_ord = sorted(rostos, key=lambda r: r["x"])
            x_esq_list.append(rostos_ord[0]["x"])
            x_dir_list.append(rostos_ord[-1]["x"])

    x_esq = float(np.mean(x_esq_list)) if x_esq_list else 0.25
    x_dir = float(np.mean(x_dir_list)) if x_dir_list else 0.75

    print(f"   👤 Pessoa esquerda em x={x_esq:.2f} | Pessoa direita em x={x_dir:.2f}")

    # Largura do crop para cada metade (proporção 9:8 para cada metade de 9:16)
    crop_w = int(altura * 9 / 16)
    if crop_w % 2 != 0:
        crop_w -= 1

    # Calcula crop X para cada pessoa
    from tracking import calcular_x_crop
    x_crop_esq = calcular_x_crop(x_esq, largura, crop_w)
    x_crop_dir = calcular_x_crop(x_dir, largura, crop_w)

    pasta_saida_dir = os.path.dirname(caminho_saida)
    video_sem_audio = os.path.join(pasta_saida_dir, "_split_temp.mp4")

    cap = cv2.VideoCapture(caminho_entrada)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(video_sem_audio, fourcc, fps, (saida_w, saida_h))

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_idx = 0

    print(f"🎬 Processando {total_frames} frames para split screen...")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Crop da pessoa da esquerda (metade de cima)
        fatia_esq = frame[0:altura, x_crop_esq:x_crop_esq + crop_w]
        topo = cv2.resize(fatia_esq, (saida_w, metade_h))

        # Crop da pessoa da direita (metade de baixo)
        fatia_dir = frame[0:altura, x_crop_dir:x_crop_dir + crop_w]
        baixo = cv2.resize(fatia_dir, (saida_w, metade_h))

        # Junta as duas metades verticalmente
        frame_final = np.vstack([topo, baixo])
        writer.write(frame_final)

        frame_idx += 1
        if frame_idx % 150 == 0:
            pct = int((frame_idx / total_frames) * 100)
            print(f"   ⏳ {pct}% ({frame_idx}/{total_frames} frames)")

    cap.release()
    writer.release()

    # Junta com áudio
    cmd = [
        "ffmpeg", "-y",
        "-i", video_sem_audio,
        "-i", caminho_entrada,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        caminho_saida
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)

    if os.path.exists(video_sem_audio):
        os.remove(video_sem_audio)

    return resultado.returncode == 0


# ── Detecção automática do modo ideal ────────────────────────────────────────

def sugerir_modo_enquadramento(caminho_video: str) -> dict:
    """
    Analisa o vídeo rapidamente e sugere o melhor modo de enquadramento.

    Retorna:
        {
          "modo": "tracking" | "smart_cut" | "split_screen",
          "motivo": "texto explicando a sugestão",
          "n_pessoas": 1
        }
    """
    print("🧠 Analisando vídeo para sugerir modo de enquadramento...")
    analise = detectar_rostos_multiplos(caminho_video, intervalo_frames=30)

    n = analise["max_rostos"]

    if n <= 1:
        return {
            "modo": "tracking",
            "motivo": "1 pessoa detectada — tracking simples é o ideal",
            "n_pessoas": n
        }
    elif n == 2:
        return {
            "modo": "smart_cut",
            "motivo": "2 pessoas detectadas — Smart Cut alterna quem está falando",
            "n_pessoas": n
        }
    else:
        return {
            "modo": "split_screen",
            "motivo": f"{n} pessoas detectadas — Split Screen mostra todos",
            "n_pessoas": n
        }


# ── Utilitários ───────────────────────────────────────────────────────────────

def _obter_info_video(caminho_video: str) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "v:0", caminho_video
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    dados = json.loads(resultado.stdout)
    stream = dados["streams"][0]
    fps_str = stream.get("r_frame_rate", "30/1")
    num, den = fps_str.split("/")
    fps = round(int(num) / int(den), 2)
    return {
        "largura": int(stream["width"]),
        "altura": int(stream["height"]),
        "duracao": float(stream.get("duration", 0)),
        "fps": fps,
        "total_frames": int(stream.get("nb_frames", 0)) or int(float(stream.get("duration", 0)) * fps)
    }


# ── Modo Dinâmico Inteligente ─────────────────────────────────────────────────

def detectar_modo_para_clipe(caminho_clipe: str) -> str:
    """
    Analisa um clipe específico e decide o melhor modo.

    Regras RÍGIDAS — nunca mostra frame vazio ou pessoa duplicada:
    - Nenhum rosto       → "fixo" (crop central)
    - 1 pessoa predomina → "tracking" (segue o rosto)
    - 2 pessoas CONFIRMADAS em posições X distintas (distância > 20% do frame):
        - Alta variação de energia → "smart_cut" (alterna quem fala)
        - Baixa variação           → "split_screen" (mostra os dois)
    - Dúvida → "tracking" (mais seguro)

    Retorna: "tracking", "smart_cut", "split_screen" ou "fixo"
    """
    detector = _inicializar_detector()
    if detector is None:
        return "tracking"

    cap = cv2.VideoCapture(caminho_clipe)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Amostra 30 frames distribuídos pelo clipe
    intervalo = max(1, total_frames // 30)
    contagens = []
    frames_com_2_rostos_distintos = 0
    frame_idx = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % intervalo == 0:
            rostos = _detectar_rostos_frame(frame, detector)
            contagens.append(len(rostos))

            # Verifica se os 2 rostos estão em posições X DISTINTAS
            # (separação mínima de 20% do frame para não confundir com o mesmo rosto)
            if len(rostos) >= 2:
                rostos_ord = sorted(rostos, key=lambda r: r["x"])
                distancia_x = rostos_ord[-1]["x"] - rostos_ord[0]["x"]
                if distancia_x >= 0.20:  # rostos separados por pelo menos 20% do frame
                    frames_com_2_rostos_distintos += 1

        frame_idx += 1

    cap.release()
    _fechar_detector(detector)

    if not contagens:
        return "fixo"

    total_amostras = len(contagens)
    max_r = max(contagens)
    pct_2_rostos = frames_com_2_rostos_distintos / total_amostras

    if max_r == 0:
        # Nenhum rosto — blur background (vinheta, logo, b-roll)
        return "blur_background"

    if pct_2_rostos < 0.30:
        # Menos de 30% dos frames têm 2 rostos distintos → é 1 pessoa só
        # Usa tracking independente do que o max_r diz
        return "tracking"

    # Confirmado: 2 pessoas distintas em pelo menos 30% dos frames
    # Analisa o áudio para decidir entre smart_cut e split_screen
    audio = detectar_voz_ativa(caminho_clipe)
    if audio:
        energias = [a["energia"] for a in audio]
        variacao = np.std(energias)
        media_e = np.mean(energias)
        # Alta variação = pessoas alternando a fala = smart_cut
        # Baixa variação = falam juntas ou silêncio constante = split_screen
        if variacao > media_e * 0.5:
            return "smart_cut"
        else:
            return "split_screen"

    # Sem áudio analisável → smart_cut é mais seguro que split_screen
    return "smart_cut"


def aplicar_split_screen_inteligente(
    caminho_entrada: str,
    caminho_saida: str,
    qualidade: str = "1080p"
) -> bool:
    """
    Split Screen com centralização correta no rosto de cada pessoa.

    Estratégia:
    - Detecta posição de cada rosto frame a frame
    - Metade de cima: centraliza no rosto da esquerda
    - Metade de baixo: centraliza no rosto da direita
    - Se não encontrar 2 rostos num frame, repete a última posição conhecida
    - Nunca mostra frame vazio
    """
    from reframe import RESOLUCOES
    saida_w, saida_h = RESOLUCOES["9:16"].get(qualidade, (1080, 1920))
    metade_h = saida_h // 2

    print("🖥️ Criando Split Screen inteligente com centralização de rostos...")

    info = _obter_info_video(caminho_entrada)
    largura = info["largura"]
    altura  = info["altura"]
    fps     = info["fps"]
    total_frames = info["total_frames"]

    # Calcula largura do crop para cada metade
    crop_w = int(altura * 9 / 16)
    if crop_w % 2 != 0:
        crop_w -= 1

    # Detecta posição de cada rosto em amostras
    detector = _inicializar_detector()
    cap_analise = cv2.VideoCapture(caminho_entrada)

    # Dicionário: frame_idx → (x_esq, x_dir)
    posicoes_por_frame = {}
    ultima_x_esq = largura * 0.25  # fallback: 25% da largura
    ultima_x_dir = largura * 0.75  # fallback: 75% da largura
    intervalo_analise = 15
    frame_idx = 0

    print(f"   🔍 Analisando posições dos rostos em {total_frames} frames...")

    while cap_analise.isOpened():
        ret, frame = cap_analise.read()
        if not ret:
            break

        if frame_idx % intervalo_analise == 0:
            rostos = _detectar_rostos_frame(frame, detector)
            if len(rostos) >= 2:
                # Ordena por posição X e pega esquerda e direita
                rostos_ord = sorted(rostos, key=lambda r: r["x"])
                ultima_x_esq = rostos_ord[0]["x"] * largura
                ultima_x_dir = rostos_ord[-1]["x"] * largura
            elif len(rostos) == 1:
                # Só 1 rosto — coloca nos dois lados (melhor que mostrar vazio)
                x = rostos[0]["x"] * largura
                ultima_x_esq = x
                ultima_x_dir = x

            posicoes_por_frame[frame_idx] = (ultima_x_esq, ultima_x_dir)

        frame_idx += 1

    cap_analise.release()
    _fechar_detector(detector)

    # Suaviza as posições para evitar tremido
    frames_list = sorted(posicoes_por_frame.keys())
    x_esq_list = [posicoes_por_frame[f][0] for f in frames_list]
    x_dir_list = [posicoes_por_frame[f][1] for f in frames_list]

    if len(x_esq_list) > 10:
        kernel = np.ones(10) / 10
        x_esq_list = np.convolve(x_esq_list, kernel, mode='same').tolist()
        x_dir_list = np.convolve(x_dir_list, kernel, mode='same').tolist()

    # Mapeia frame → posição X suavizada
    def get_posicao(frame_idx, lista_frames, lista_x, fallback):
        if not lista_frames:
            return fallback
        idx = min(range(len(lista_frames)), key=lambda i: abs(lista_frames[i] - frame_idx))
        return lista_x[idx]

    # Processa frames com as posições corretas
    pasta = os.path.dirname(caminho_saida)
    if not pasta:
        pasta = "."
    video_sem_audio = os.path.join(pasta, "_split_inteligente_temp.mp4")

    cap = cv2.VideoCapture(caminho_entrada)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(video_sem_audio, fourcc, fps, (saida_w, saida_h))

    print(f"   🎬 Processando {total_frames} frames...")
    frame_idx = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Pega posição X do centro de cada rosto neste frame
        x_esq = get_posicao(frame_idx, frames_list, x_esq_list, largura * 0.25)
        x_dir = get_posicao(frame_idx, frames_list, x_dir_list, largura * 0.75)

        # Calcula início do crop centralizado no rosto
        from tracking import calcular_x_crop
        x_crop_esq = calcular_x_crop(x_esq / largura, largura, crop_w)
        x_crop_dir = calcular_x_crop(x_dir / largura, largura, crop_w)

        # Garante que o crop não ultrapassa os limites
        x_crop_esq = max(0, min(largura - crop_w, x_crop_esq))
        x_crop_dir = max(0, min(largura - crop_w, x_crop_dir))

        # Aplica crop e redimensiona cada metade
        fatia_esq = frame[0:altura, x_crop_esq:x_crop_esq + crop_w]
        fatia_dir = frame[0:altura, x_crop_dir:x_crop_dir + crop_w]

        topo  = cv2.resize(fatia_esq, (saida_w, metade_h))
        baixo = cv2.resize(fatia_dir, (saida_w, metade_h))

        frame_final = np.vstack([topo, baixo])
        writer.write(frame_final)
        frame_idx += 1

        if frame_idx % 150 == 0:
            pct = int((frame_idx / total_frames) * 100)
            print(f"   ⏳ {pct}% ({frame_idx}/{total_frames} frames)")

    cap.release()
    writer.release()

    # Junta com áudio
    cmd = [
        "ffmpeg", "-y",
        "-i", video_sem_audio, "-i", caminho_entrada,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        caminho_saida
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)

    if os.path.exists(video_sem_audio):
        os.remove(video_sem_audio)

    if resultado.returncode != 0:
        print("⚠️ Erro no split screen. Fallback para tracking...")
        from reframe import _ffmpeg_simples
        nova_largura = int(altura * 9 / 16)
        if nova_largura % 2 != 0:
            nova_largura -= 1
        x = int((largura - nova_largura) / 2)
        return _ffmpeg_simples(
            caminho_entrada, caminho_saida,
            f"crop={nova_largura}:{altura}:{x}:0,scale={saida_w}:{saida_h}"
        )

    return True
