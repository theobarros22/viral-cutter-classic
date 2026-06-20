"""
reframe.py
----------
Reformata vídeos com suporte a múltiplas qualidades e modos de enquadramento.

Modos disponíveis:
  "tracking"        → 1 pessoa, segue o rosto com zona morta
  "smart_cut"       → 2 pessoas, alterna quem está falando
  "split_screen"    → 2 pessoas lado a lado (topo/baixo)
  "blur_background" → vídeo 16:9 centralizado com fundo desfocado (vinhetas/b-roll)
  "fixo"            → crop central fixo, sem IA
"""

import subprocess
import json
import os
import cv2
import numpy as np
from tracking import detectar_posicoes_rosto, suavizar_posicoes, calcular_x_crop


RESOLUCOES = {
    "9:16":  {"720p": (405, 720),   "1080p": (1080, 1920), "4k": (2160, 3840)},
    "1:1":   {"720p": (720, 720),   "1080p": (1080, 1080), "4k": (2160, 2160)},
    "16:9":  {"720p": (1280, 720),  "1080p": (1920, 1080), "4k": (3840, 2160)},
}


def obter_info_video(caminho_video: str) -> dict:
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
        "altura":  int(stream["height"]),
        "duracao": float(stream.get("duration", 0)),
        "fps": fps
    }


def aplicar_reframe(
    caminho_entrada: str,
    caminho_saida: str,
    formato: str = "9:16",
    qualidade: str = "1080p",
    modo_enquadramento: str = "tracking",
    usar_tracking: bool = True,
    suavizacao: int = 30
) -> bool:
    """
    Aplica reframe no vídeo.

    Parâmetros:
        caminho_entrada: vídeo original
        caminho_saida: onde salvar
        formato: "9:16", "16:9" ou "1:1"
        qualidade: "720p", "1080p" ou "4k"
        modo_enquadramento: qual modo usar
        usar_tracking: legado (False = força fixo)
        suavizacao: suavidade do movimento
    """
    # Compatibilidade com código antigo
    if not usar_tracking:
        modo_enquadramento = "fixo"

    info = obter_info_video(caminho_entrada)
    largura = info["largura"]
    altura  = info["altura"]

    resolucoes_formato = RESOLUCOES.get(formato, RESOLUCOES["9:16"])
    saida_w, saida_h = resolucoes_formato.get(qualidade, resolucoes_formato["1080p"])

    print(f"🎬 Reframe: {formato} | {qualidade} ({saida_w}x{saida_h}) | modo: {modo_enquadramento}")

    # 16:9 — só redimensiona
    if formato == "16:9":
        return _ffmpeg_simples(caminho_entrada, caminho_saida, f"scale={saida_w}:{saida_h}")

    # Calcula dimensões do crop
    if formato == "9:16":
        nova_largura = int(altura * 9 / 16)
        if nova_largura % 2 != 0:
            nova_largura -= 1
        nova_altura = altura
    else:  # 1:1
        lado = min(largura, altura)
        nova_largura = lado
        nova_altura = lado

    # ── Roteamento por modo ───────────────────────────────────────────────────

    if modo_enquadramento == "smart_cut":
        from smart_cut import aplicar_smart_cut
        return aplicar_smart_cut(
            caminho_entrada, caminho_saida,
            saida_w=saida_w, saida_h=saida_h,
            suavizacao=suavizacao
        )

    elif modo_enquadramento == "split_screen":
        from smart_cut import aplicar_split_screen_inteligente
        return aplicar_split_screen_inteligente(
            caminho_entrada, caminho_saida, qualidade=qualidade
        )

    elif modo_enquadramento == "blur_background":
        return _reframe_blur_background(
            caminho_entrada, caminho_saida,
            saida_w, saida_h
        )

    elif modo_enquadramento == "fixo":
        # Modo fixo agora usa blur_background — muito mais bonito que crop central
        return _reframe_blur_background(
            caminho_entrada, caminho_saida,
            saida_w, saida_h
        )

    # Modo tracking (padrão)
    return _reframe_com_tracking(
        caminho_entrada, caminho_saida,
        largura, altura, info["fps"],
        nova_largura, nova_altura,
        saida_w, saida_h, suavizacao
    )


def _reframe_blur_background(
    caminho_entrada: str,
    caminho_saida: str,
    saida_w: int = 1080,
    saida_h: int = 1920,
    intensidade_blur: int = 40
) -> bool:
    """
    Efeito blur background:
    - Fundo: vídeo original esticado para 9:16 e fortemente desfocado
    - Centro: vídeo original em tamanho real, centralizado
    - Resultado: visual profissional sem cortar nada

    Usado automaticamente para vinhetas, logos, b-roll e qualquer
    conteúdo sem rosto detectado.

    Parâmetros:
        intensidade_blur: força do desfoque (maior = mais desfocado)
    """
    print("🌫️ Aplicando blur background...")

    # Garante que o blur é ímpar (requisito do OpenCV)
    if intensidade_blur % 2 == 0:
        intensidade_blur += 1

    info = obter_info_video(caminho_entrada)
    largura = info["largura"]
    altura  = info["altura"]
    fps     = info["fps"]

    # Calcula dimensões do vídeo centralizado
    # Mantém proporção original dentro do frame 9:16
    ratio_original = largura / altura
    ratio_saida    = saida_w / saida_h

    if ratio_original > ratio_saida:
        # Vídeo mais largo que o frame — limita pela largura
        vid_w = saida_w
        vid_h = int(saida_w / ratio_original)
    else:
        # Vídeo mais alto que o frame — limita pela altura
        vid_h = saida_h
        vid_w = int(saida_h * ratio_original)

    # Garante par
    vid_w = vid_w if vid_w % 2 == 0 else vid_w - 1
    vid_h = vid_h if vid_h % 2 == 0 else vid_h - 1

    # Posição do vídeo centralizado
    x_offset = (saida_w - vid_w) // 2
    y_offset = (saida_h - vid_h) // 2

    pasta = os.path.dirname(caminho_saida)
    if not pasta:
        pasta = "."
    video_sem_audio = os.path.join(pasta, "_blur_temp.mp4")

    cap = cv2.VideoCapture(caminho_entrada)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(video_sem_audio, fourcc, fps, (saida_w, saida_h))

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_idx = 0

    print(f"   🎬 Processando {total_frames} frames com blur background...")
    print(f"   📐 Vídeo centralizado: {vid_w}x{vid_h} em ({x_offset},{y_offset})")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # ── Camada 1: Fundo desfocado ─────────────────────────────────────
        # Estica o frame para cobrir todo o 9:16
        fundo = cv2.resize(frame, (saida_w, saida_h), interpolation=cv2.INTER_LINEAR)

        # Aplica desfoque gaussiano forte
        fundo = cv2.GaussianBlur(fundo, (intensidade_blur, intensidade_blur), 0)

        # Escurece levemente o fundo para destacar o vídeo central
        fundo = (fundo * 0.6).astype(np.uint8)

        # ── Camada 2: Vídeo original centralizado ─────────────────────────
        vid_central = cv2.resize(frame, (vid_w, vid_h), interpolation=cv2.INTER_LANCZOS4)

        # Cola o vídeo central sobre o fundo desfocado
        fundo[y_offset:y_offset + vid_h, x_offset:x_offset + vid_w] = vid_central

        writer.write(fundo)
        frame_idx += 1

        if frame_idx % 100 == 0:
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

    if resultado.returncode != 0:
        print("⚠️ Erro no blur. Fallback para crop central...")
        x = int((largura - int(altura * 9 / 16)) / 2)
        nova_largura = int(altura * 9 / 16)
        if nova_largura % 2 != 0:
            nova_largura -= 1
        return _ffmpeg_simples(
            caminho_entrada, caminho_saida,
            f"crop={nova_largura}:{altura}:{x}:0,scale={saida_w}:{saida_h}"
        )

    return True


def _reframe_com_tracking(
    caminho_entrada, caminho_saida,
    largura, altura, fps,
    nova_largura, nova_altura,
    saida_w, saida_h, suavizacao
) -> bool:
    """Reframe frame a frame seguindo o rosto com OpenCV."""
    posicoes = detectar_posicoes_rosto(caminho_entrada, intervalo_frames=5)
    if suavizacao > 1:
        posicoes = suavizar_posicoes(posicoes, janela=suavizacao)

    total_frames = len(posicoes)
    pasta = os.path.dirname(caminho_saida)
    if not pasta:
        pasta = "."
    video_sem_audio = os.path.join(pasta, "_frames_temp.mp4")

    print(f"🎬 Processando {total_frames} frames com tracking...")

    cap = cv2.VideoCapture(caminho_entrada)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(video_sem_audio, fourcc, fps, (saida_w, saida_h))

    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        pos_x  = posicoes[frame_idx] if frame_idx < len(posicoes) else 0.5
        x_crop = calcular_x_crop(pos_x, largura, nova_largura)
        y_crop = int((altura - nova_altura) / 2) if nova_altura < altura else 0

        frame_cortado = frame[y_crop:y_crop + nova_altura, x_crop:x_crop + nova_largura]
        frame_final   = cv2.resize(frame_cortado, (saida_w, saida_h))
        writer.write(frame_final)
        frame_idx += 1

        if frame_idx % 100 == 0:
            pct = int((frame_idx / total_frames) * 100)
            print(f"   ⏳ {pct}% ({frame_idx}/{total_frames} frames)")

    cap.release()
    writer.release()

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
        print("⚠️ Erro no tracking. Fallback para blur background...")
        return _reframe_blur_background(caminho_entrada, caminho_saida, saida_w, saida_h)

    return True


def _ffmpeg_simples(caminho_entrada: str, caminho_saida: str, filtro: str) -> bool:
    cmd = [
        "ffmpeg", "-y", "-i", caminho_entrada,
        "-vf", filtro,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        caminho_saida
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    return resultado.returncode == 0


def criar_split_screen(video_cima: str, video_baixo: str, caminho_saida: str) -> bool:
    """Combina dois vídeos separados em split screen vertical."""
    print("🖥️ Criando split screen com dois vídeos...")
    filtro = (
        "[0:v]scale=1080:960,setsar=1[topo];"
        "[1:v]scale=1080:960,setsar=1[baixo];"
        "[topo][baixo]vstack=inputs=2[saida]"
    )
    cmd = [
        "ffmpeg", "-y", "-i", video_cima, "-i", video_baixo,
        "-filter_complex", filtro,
        "-map", "[saida]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", caminho_saida
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    return resultado.returncode == 0
