"""
CoreEngine.py
------------
MÃ³dulo principal de processamento audiovisual para ediÃ§Ã£o de alta retenÃ§Ã£o.
ContÃ©m algoritmos de IA, visÃ£o computacional e pipelines FFmpeg acelerados por hardware.
"""

import os
import sys
import json
import logging
import subprocess
import tempfile
from pathlib import Path

# ConfiguraÃ§Ã£o de Logs
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("CoreEngine")

def _localizar_ffmpeg():
    """Localiza a presenÃ§a do executÃ¡vel FFmpeg no sistema ou pasta local."""
    import shutil
    candidatos = [
        shutil.which("ffmpeg"),
        r"D:\CORTE VIRAL\files\tools\ffmpeg.exe",
        r"D:\CORTE VIRAL\tools\ffmpeg.exe",
    ]
    for c in candidatos:
        if c and os.path.exists(c):
            return c
    return "ffmpeg"  # Fallback para PATH global

FFMPEG_PATH = _localizar_ffmpeg()

# -----------------------------------------------------------------------------
# 1. PREPARAÃ‡ÃƒO E TRANSCRIÃ‡ÃƒO (IA & WORD-LEVEL SYNC)
# -----------------------------------------------------------------------------

def extract_audio(video_path: str, audio_path: str) -> bool:
    """
    Extrai o Ã¡udio do vÃ­deo original em formato .wav otimizado para Whisper.
    EspecificaÃ§Ãµes: 16kHz, mono, PCM 16-bit (pcm_s16le).
    """
    logger.info(f"Iniciando extraÃ§Ã£o de Ã¡udio: {video_path} -> {audio_path}")
    try:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"VÃ­deo de entrada nÃ£o encontrado: {video_path}")
            
        comando = [
            FFMPEG_PATH, "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_path
        ]
        
        resultado = subprocess.run(
            comando, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=True
        )
        logger.info("Ãudio extraÃ­do com sucesso.")
        return True
    except Exception as e:
        logger.error(f"Erro ao extrair Ã¡udio: {e}")
        return False

def transcribe_and_chunk(audio_path: str) -> list:
    """
    Transcreve Ã¡udio localmente usando Faster-Whisper acelerado por CUDA em FP16.
    Implementa Smart Chunking agrupando de 1 a 3 palavras e cortando em silÃªncios > 0.3s.
    Retorna uma lista de dicionÃ¡rios contendo: id, start, end, text.
    """
    logger.info(f"Iniciando transcriÃ§Ã£o com Faster-Whisper: {audio_path}")
    try:
        from faster_whisper import WhisperModel
        
        # Carrega o modelo turbo localmente com CUDA e precisÃ£o FP16
        logger.info("Carregando WhisperModel (turbo) na GPU...")
        modelo = WhisperModel("turbo", device="cuda", compute_type="float16")
        
        # Executa transcriÃ§Ã£o no nÃ­vel de palavras
        segmentos, info = modelo.transcribe(audio_path, word_timestamps=True, language="pt")
        
        palavras = []
        for segment in segmentos:
            if segment.words:
                for w in segment.words:
                    palavras.append({
                        "word": w.word.strip(),
                        "start": w.start,
                        "end": w.end
                    })
        
        logger.info(f"Whisper concluiu. {len(palavras)} palavras detectadas. Aplicando Smart Chunking...")
        
        # Algoritmo de Smart Chunking
        cartoes = []
        if not palavras:
            return cartoes
            
        cartao_atual = []
        id_counter = 1
        
        for i, p in enumerate(palavras):
            # Adiciona palavra ao cartÃ£o atual
            cartao_atual.append(p)
            
            # Verifica condiÃ§Ãµes de quebra
            quebrar = False
            
            # 1. Limite de 3 palavras por cartÃ£o
            if len(cartao_atual) >= 3:
                quebrar = True
                
            # 2. SilÃªncio maior que 0.3 segundos entre a palavra atual e a prÃ³xima
            elif i < len(palavras) - 1:
                silencio = palavras[i + 1]["start"] - p["end"]
                if silencio > 0.3:
                    quebrar = True
                    
            # 3. Ã‰ a Ãºltima palavra
            elif i == len(palavras) - 1:
                quebrar = True
                
            if quebrar:
                texto_cartao = " ".join([w["word"] for w in cartao_atual])
                cartoes.append({
                    "id": id_counter,
                    "start": round(cartao_atual[0]["start"], 3),
                    "end": round(cartao_atual[-1]["end"], 3),
                    "text": texto_cartao.upper(),
                    "words": cartao_atual
                })
                id_counter += 1
                cartao_atual = []
                
        logger.info(f"Smart Chunking finalizado: {len(cartoes)} cartÃµes gerados.")
        return cartoes
    except Exception as e:
        logger.error(f"Erro na transcriÃ§Ã£o: {e}")
        return []

# -----------------------------------------------------------------------------
# 2. RITMO E QUEBRA DE PADRÃƒO (EFEITOS VIRAIS)
# -----------------------------------------------------------------------------

def remove_silences(video_path: str, output_path: str) -> bool:
    """
    Remove trechos silenciosos > 0.4s usando 'silencedetect' do FFmpeg para fazer jump cuts.
    """
    logger.info(f"Analisando silÃªncios para jump cuts: {video_path}")
    try:
        # 1. Detectar silÃªncios
        comando_detect = [
            FFMPEG_PATH, "-i", video_path,
            "-af", "silencedetect=noise=-35dB:d=0.4",
            "-f", "null", "-"
        ]
        resultado = subprocess.run(
            comando_detect, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=True
        )
        linhas = resultado.stderr.splitlines()
        
        silence_starts = []
        silence_ends = []
        
        for linha in linhas:
            if "silence_start" in linha:
                parts = linha.split("silence_start:")
                silence_starts.append(float(parts[1].split()[0]))
            elif "silence_end" in linha:
                parts = linha.split("silence_end:")
                silence_ends.append(float(parts[1].split()[0]))
                
        # Obter duraÃ§Ã£o total do vÃ­deo
        duracao = 0.0
        cmd_dur = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", video_path
        ]
        res_dur = subprocess.run(
            cmd_dur, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if res_dur.returncode == 0:
            duracao = float(json.loads(res_dur.stdout).get("format", {}).get("duration", 0.0))
            
        logger.info(f"SilÃªncios detectados: {len(silence_starts)}. DuraÃ§Ã£o total: {duracao}s")
        
        # Calcular trechos de fala a manter
        trechos = []
        inicio = 0.0
        for start, end in zip(silence_starts, silence_ends):
            if start > inicio:
                trechos.append((inicio, start))
            inicio = end
        if inicio < duracao:
            trechos.append((inicio, duracao))
            
        if not trechos:
            logger.warning("Nenhum trecho de Ã¡udio/fala detectado no vÃ­deo. Mantendo original.")
            import shutil
            shutil.copy2(video_path, output_path)
            return True
            
        # Construir filtro de concatenaÃ§Ã£o FFmpeg para jump cuts rÃ¡pidos
        select_v = []
        select_a = []
        for i, (s, e) in enumerate(trechos):
            select_v.append(f"between(t,{s:.3f},{e:.3f})")
            select_a.append(f"between(t,{s:.3f},{e:.3f})")
            
        filt_v = f"select='{' + '.join(select_v)}',setpts=N/FRAME_RATE/TB"
        filt_a = f"aselect='{' + '.join(select_a)}',asetpts=N/SR/TB"
        
        comando_render = [
            FFMPEG_PATH, "-y",
            "-i", video_path,
            "-vf", filt_v,
            "-af", filt_a,
            "-c:v", "h264_nvenc",  # Usar aceleraÃ§Ã£o de GPU
            "-c:a", "aac",
            output_path
        ]
        
        subprocess.run(comando_render, check=True)
        logger.info(f"Jump cuts renderizados em: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Erro ao remover silÃªncios: {e}")
        return False

def apply_auto_zoom(video_path: str, timestamps_picos: list, output_path: str) -> bool:
    """
    Aplica efeito de Punch-In (15% a 20% zoom seco) nos instantes de picos ou Ãªnfases.
    Fica em zoom nos timestamps dados e volta ao enquadramento normal nos intervalos vazios.
    """
    logger.info(f"Aplicando auto-zoom dinÃ¢mico baseados em {len(timestamps_picos)} picos.")
    try:
        # Monta expressÃµes condicionais para o filtro crop do FFmpeg
        # Zoom de 15% significa cortar 85% do tamanho
        condicoes = []
        for t in timestamps_picos:
            # MantÃ©m zoom por 1 segundo apÃ³s o pico
            condicoes.append(f"between(t,{t:.3f},{t+1.0:.3f})")
            
        if condicoes:
            expr_is_zoom = " + ".join(condicoes)
            crop_w = f"'if({expr_is_zoom}, in_w*0.85, in_w)'"
            crop_h = f"'if({expr_is_zoom}, in_h*0.85, in_h)'"
            crop_x = "'(in_w-out_w)/2'"
            crop_y = "'(in_h-out_h)/2'"
        else:
            crop_w = "in_w"
            crop_h = "in_h"
            crop_x = "0"
            crop_y = "0"
            
        comando = [
            FFMPEG_PATH, "-y",
            "-i", video_path,
            "-vf", f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=1080:1920",
            "-c:v", "h264_nvenc",
            "-c:a", "copy",
            output_path
        ]
        subprocess.run(comando, check=True)
        logger.info("Filtro de zoom aplicado.")
        return True
    except Exception as e:
        logger.error(f"Erro ao aplicar auto zoom: {e}")
        return False

def auto_framing(video_path: str, output_path: str) -> bool:
    """
    Rastreia o rosto do locutor frame a frame via MediaPipe,
    ajustando as coordenadas de corte do FFmpeg para centralizar o locutor no formato 9:16 vertical.
    """
    logger.info(f"Iniciando Auto-Framing MediaPipe (Face Detection) para {video_path}")
    try:
        import cv2
        import numpy as np
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
        
        # Localiza o modelo facial tflite
        modelo_path = r"D:\CORTE VIRAL\files\face_detector.tflite"
        base_options = mp_python.BaseOptions(model_asset_path=modelo_path)
        options = mp_vision.FaceDetectorOptions(
            base_options=base_options,
            min_detection_confidence=0.35
        )
        detector = mp_vision.FaceDetector.create_from_options(options)
        
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        target_w = int(height * (9/16))
        if target_w > width:
            target_w = width
            
        logger.info(f"DimensÃµes originais: {width}x{height}. Largura alvo: {target_w}")
        
        x_centers = []
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            results = detector.detect(mp_image)
            
            x_center = width / 2.0
            if results.detections:
                bbox = results.detections[0].bounding_box
                x_center = bbox.origin_x + bbox.width / 2.0
                
            x_centers.append(x_center)
            
        cap.release()
        
        # SuavizaÃ§Ã£o por mÃ©dia mÃ³vel (Janela de 30 frames para evitar jitter)
        window = 30
        x_centers_smooth = np.convolve(x_centers, np.ones(window)/window, mode='same')
        
        # Re-enquadramento via OpenCV
        logger.info("Processando re-enquadramento via OpenCV e gravando saÃ­da...")
        cap = cv2.VideoCapture(video_path)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (target_w, height))
        
        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            x_center = x_centers_smooth[frame_idx]
            crop_x = int(x_center - target_w / 2.0)
            crop_x = max(0, min(width - target_w, crop_x))
            
            cropped = frame[0:height, crop_x:crop_x+target_w]
            out.write(cropped)
            frame_idx += 1
            
        cap.release()
        out.release()
        
        # Adiciona o Ã¡udio original de volta ao vÃ­deo cropado
        temp_no_audio = output_path + ".temp.mp4"
        os.rename(output_path, temp_no_audio)
        
        cmd_merge = [
            FFMPEG_PATH, "-y",
            "-i", temp_no_audio,
            "-i", video_path,
            "-map", "0:v", "-map", "1:a?",
            "-c:v", "copy", "-c:a", "aac",
            output_path
        ]
        subprocess.run(cmd_merge, check=True)
        os.remove(temp_no_audio)
        
        logger.info("Auto-framing concluÃ­do com sucesso!")
        return True
    except Exception as e:
        logger.error(f"Erro no auto-framing: {e}")
        return False

# -----------------------------------------------------------------------------
# 3. ESTILIZAÃ‡ÃƒO E DESIGN DE SOM (ESTILO DOCUMENTÃRIO)
# -----------------------------------------------------------------------------

def generate_subtitles_ass(lista_cartoes: list, ass_path: str) -> bool:
    """
    Cria arquivo de legenda .ass ultraestilizado.
    EspecificaÃ§Ãµes: Caixa Alta, borda preta grossa, sombra suave, Pop-up e destaque KaraokÃª em amarelo.
    """
    logger.info(f"Gerando legendas ASS em: {ass_path}")
    try:
        header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,95,&HFFFFFF,&H00FFFF,&H000000,&H000000,-1,0,0,0,100,100,0,0,1,10,4,2,50,50,600,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        def format_time(t):
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            cs = int(round((t % 1) * 100))
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
            
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header)
            for c in lista_cartoes:
                start_str = format_time(c["start"])
                end_str = format_time(c["end"])
                text = c["text"].upper()
                
                # Pop-up animation tag: inicia pequena (80%) e escala para 100% em 100ms
                anim_tag = r"{\fscx80\fscy80\t(0,100,\fscx100\fscy100)}"
                
                # Efeito KaraokÃª palavra por palavra
                palavras = text.split()
                duracao_total = c["end"] - c["start"]
                dur_por_palavra = (duracao_total / len(palavras)) * 100  # em centÃ©simos de segundo
                
                k_text = ""
                for i, p in enumerate(palavras):
                    k_text += rf"{{\k{int(dur_por_palavra)}}}{p} "
                
                f.write(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{anim_tag}{k_text.strip()}\n")
                
        logger.info("Legenda ASS gravada.")
        return True
    except Exception as e:
        logger.error(f"Erro ao gerar legendas ASS: {e}")
        return False

def apply_audio_ducking(video_path: str, background_music_path: str, output_path: str) -> bool:
    """
    Mixa a mÃºsica de fundo aplicando sidechain compression (-25dB quando hÃ¡ voz).
    """
    logger.info("Aplicando sidechain audio ducking...")
    try:
        # Filtro de compressÃ£o de Ã¡udio sidechain
        # Reduz mÃºsica de fundo (track 1) baseada no volume da voz (track 0)
        filter_str = (
            "[0:a]asplit[voice_main][voice_side];"
            "[1:a]volume=0.3[music_low];"
            "[music_low][voice_side]sidechaincompress=threshold=0.08:ratio=10:attack=15:release=200[music_ducked];"
            "[voice_main][music_ducked]amix=inputs=2:duration=first[aout]"
        )
        
        comando = [
            FFMPEG_PATH, "-y",
            "-i", video_path,
            "-i", background_music_path,
            "-filter_complex", filter_str,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            output_path
        ]
        
        subprocess.run(comando, check=True)
        logger.info(f"Ducking finalizado: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Erro no audio ducking: {e}")
        return False

def sync_sfx_and_brolls(video_path: str, lista_cartoes: list, pasta_assets: str, output_path: str) -> bool:
    """
    Combina B-rolls (vÃ­deos de cobertura) e SFX baseados em palavras-chave presentes nos cartÃµes.
    Procura arquivos whoosh.wav/pop.wav e vÃ­deos na pasta_assets.
    """
    logger.info("Iniciando sincronizaÃ§Ã£o de SFX e B-Rolls...")
    try:
        # DicionÃ¡rio de trigger words
        sfx_keywords = {
            "ERRO": "pop.wav",
            "MUDAR": "whoosh.wav",
            "VÃDEO": "pop.wav",
            "IMPOSSÃVEL": "whoosh.wav"
        }
        
        cmd_inputs = ["-i", video_path]
        amix_filters = ["[0:a]"]
        overlay_filters = ["[0:v]"]
        
        # Localiza arquivos SFX/B-roll
        input_idx = 1
        for c in lista_cartoes:
            words = c["text"].split()
            for w in words:
                clean_w = w.strip(".,!?\"'")
                if clean_w in sfx_keywords:
                    sfx_file = os.path.join(pasta_assets, sfx_keywords[clean_w])
                    if os.path.exists(sfx_file):
                        cmd_inputs += ["-i", sfx_file]
                        # Atrasar Ã¡udio atÃ© o inÃ­cio da palavra
                        delay_ms = int(c["start"] * 1000)
                        amix_filters.append(f"[{input_idx}:a]adelay={delay_ms}|{delay_ms}[sfx_{input_idx}];")
                        overlay_filters.append(f"[sfx_{input_idx}]")
                        input_idx += 1
                        
        # Mixagem de Ã¡udio
        if len(overlay_filters) > 1:
            inputs_count = len(overlay_filters)
            audio_graph = "".join(amix_filters) + "".join(f"{overlay_filters[i]}" for i in range(inputs_count)) + f"amix=inputs={inputs_count}:duration=first[aout]"
            comando = [FFMPEG_PATH, "-y"] + cmd_inputs + ["-filter_complex", audio_graph, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", output_path]
        else:
            comando = [FFMPEG_PATH, "-y", "-i", video_path, "-c", "copy", output_path]
            
        subprocess.run(comando, check=True)
        logger.info("SFX/B-rolls sincronizados.")
        return True
    except Exception as e:
        logger.error(f"Erro ao sincronizar SFX/B-rolls: {e}")
        return False

# -----------------------------------------------------------------------------
# 4. COMPOSIÃ‡ÃƒO AVANÃ‡ADA
# -----------------------------------------------------------------------------

def apply_3d_text_mask(video_path: str, ass_path: str, output_path: str) -> bool:
    """
    Renderiza legendas por trÃ¡s do locutor usando segmentaÃ§Ã£o de fundo do MediaPipe.
    Fluxo: Base original + Legenda ASS + Recorte do locutor por cima (Selfie Segmentation).
    """
    logger.info("Aplicando mÃ¡scara 3D de texto (Text Behind Person)...")
    try:
        import cv2
        import numpy as np
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
        
        # Download model if not exists
        modelo_path = r"D:\CORTE VIRAL\files\selfie_segmenter.tflite"
        if not os.path.exists(modelo_path):
            import urllib.request
            logger.info("Baixando modelo selfie segmenter para mÃ¡scara 3D...")
            url = "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite"
            urllib.request.urlretrieve(url, modelo_path)
            
        base_options = mp_python.BaseOptions(model_asset_path=modelo_path)
        options = mp_vision.ImageSegmenterOptions(
            base_options=base_options,
            output_category_mask=True
        )
        segmenter = mp_vision.ImageSegmenter.create_from_options(options)
        
        # 1. Primeiro cria o vÃ­deo temporÃ¡rio com legendas normais aplicadas
        escaped_ass_path = ass_path.replace("\\", "/").replace(":", "\\:")
        temp_subbed = output_path + ".subbed.mp4"
        cmd_sub = [
            FFMPEG_PATH, "-y",
            "-i", video_path,
            "-vf", f"ass='{escaped_ass_path}'",
            "-c:a", "copy",
            temp_subbed
        ]
        subprocess.run(cmd_sub, check=True)
        
        # 2. Segmentar locutor frame a frame e compor: original com mÃ¡scara sobre o vÃ­deo com legenda
        cap_orig = cv2.VideoCapture(video_path)
        cap_sub = cv2.VideoCapture(temp_subbed)
        
        fps = cap_orig.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap_orig.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap_orig.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        while cap_orig.isOpened() and cap_sub.isOpened():
            ret_orig, frame_orig = cap_orig.read()
            ret_sub, frame_sub = cap_sub.read()
            
            if not ret_orig or not ret_sub:
                break
                
            frame_rgb = cv2.cvtColor(frame_orig, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            results = segmenter.segment(mp_image)
            category_mask = results.category_mask.numpy_view()
            
            # MÃ¡scara binÃ¡ria do corpo
            mask = category_mask > 0.5
            mask_3d = np.dstack([mask] * 3)
            
            # ComposiÃ§Ã£o: Se pessoa (mÃ¡scara), usa original. SenÃ£o, usa com legenda.
            composite = np.where(mask_3d, frame_orig, frame_sub)
            out.write(composite)
            
        cap_orig.release()
        cap_sub.release()
        out.release()
        
        if os.path.exists(temp_subbed):
            os.remove(temp_subbed)
            
        # Adicionar o Ã¡udio de volta
        temp_no_audio = output_path + ".temp.mp4"
        os.rename(output_path, temp_no_audio)
        
        cmd_merge = [
            FFMPEG_PATH, "-y",
            "-i", temp_no_audio,
            "-i", video_path,
            "-map", "0:v", "-map", "1:a?",
            "-c:v", "copy", "-c:a", "aac",
            output_path
        ]
        subprocess.run(cmd_merge, check=True)
        os.remove(temp_no_audio)
        
        logger.info("Texto 3D (por trÃ¡s do locutor) aplicado.")
        return True
    except Exception as e:
        logger.error(f"Erro ao aplicar mÃ¡scara 3D de texto: {e}")
        return False

def render_split_screen(video_topo_path: str, video_base_path: str, output_path: str) -> bool:
    """
    Empilha verticalmente o vÃ­deo do topo e o vÃ­deo da base no formato 9:16.
    Ajusta resoluÃ§Ãµes e concatena a duraÃ§Ã£o para o menor tamanho comum.
    """
    logger.info("Criando Split-Screen vertical...")
    try:
        # Filtro de empilhamento vertical do FFmpeg (vstack)
        # Redimensiona ambos para 1080x960 (formando uma tela de 1080x1920 juntos)
        filter_complex = (
            "[0:v]scale=1080:960,setsar=1[top];"
            "[1:v]scale=1080:960,setsar=1[bottom];"
            "[top][bottom]vstack=inputs=2[vsplit]"
        )
        
        comando = [
            FFMPEG_PATH, "-y",
            "-i", video_topo_path,
            "-i", video_base_path,
            "-filter_complex", filter_complex,
            "-map", "[vsplit]",
            "-map", "0:a?",  # MantÃ©m Ã¡udio do vÃ­deo do topo
            "-shortest",     # Corta no menor tempo
            "-c:v", "h264_nvenc",
            "-c:a", "aac",
            output_path
        ]
        
        subprocess.run(comando, check=True)
        logger.info(f"Split-Screen concluÃ­do: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Erro no split screen: {e}")
        return False


# -----------------------------------------------------------------------------
# 5. MÃ“DULO DE INTELIGÃŠNCIA ARTIFICIAL CONTEXTUAL
# -----------------------------------------------------------------------------

def analyze_context_for_viral_effects(json_timestamps: list) -> list:
    """
    Envia o roteiro estruturado para um modelo de linguagem local (via Ollama)
    com um prompt focado em direÃ§Ã£o criativa e ediÃ§Ã£o.
    Retorna o JSON dos cartÃµes enriquecido com: zoom, sfx, broll_keyword e text_style.
    Caso o Ollama esteja inacessÃ­vel, ativa um fallback heurÃ­stico local.
    """
    logger.info("Iniciando anÃ¡lise contextual de efeitos com IA...")
    
    # Prepara o roteiro textual para o prompt
    roteiro = []
    for item in json_timestamps:
        roteiro.append(f"ID {item['id']}: {item['text']} (InÃ­cio: {item['start']}s)")
        
    roteiro_str = "\n".join(roteiro)
    
    prompt = f"""VocÃª Ã© um Diretor de VÃ­deo de Alta RetenÃ§Ã£o (estilo TikTok/Reels).
Analise o roteiro a seguir e decida as intenÃ§Ãµes de ediÃ§Ã£o para cada cartÃ£o (ID).
Para cada ID, vocÃª deve decidir:
1. 'zoom': true/false (true para momentos de Ãªnfase, gancho inicial, mudanÃ§a de assunto ou palavras fortes).
2. 'sfx': nome do efeito sonoro ('cinematic_boom', 'whoosh', 'pop', 'vinyl_pause', 'scratch' ou null).
3. 'broll_keyword': palavra-chave curta em inglÃªs para buscar um vÃ­deo de cobertura correspondente (ex: 'money', 'crypto', 'confused', 'success', 'city' ou null).
4. 'text_style': se o estilo deve ser 'emphasis' (destaque em laranja/cor chamativa) ou 'standard' (branco).

Roteiro:
{roteiro_str}

Retorne estritamente um JSON no seguinte formato (sem explicaÃ§Ãµes ou comentÃ¡rios adicionais):
[
  {{"id": 1, "zoom": true, "sfx": "whoosh", "broll_keyword": "ideas", "text_style": "emphasis"}},
  ...
]
"""
    
    # Tenta chamar o Ollama local (llama3)
    url_ollama = "http://127.0.0.1:11434/api/generate"
    payload = {
        "model": "llama3.1:8b",
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    
    import urllib.request
    
    ai_decisions = {}
    try:
        req = urllib.request.Request(
            url_ollama,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as res:
            resp_data = json.loads(res.read().decode("utf-8"))
            response_text = resp_data.get("response", "[]")
            decisions = json.loads(response_text)
            for d in decisions:
                ai_decisions[int(d["id"])] = d
            logger.info("AnÃ¡lise contextual da IA local (Ollama) concluÃ­da com sucesso.")
    except Exception as e:
        logger.warning(f"Ollama local indisponÃ­vel ou erro na resposta ({e}). Usando analisador heurÃ­stico local.")
        # Fallback HeurÃ­stico Local baseado em regras simples de PNL
        palavras_impacto = {"ERRO", "MUDAR", "IMPOSSÃVEL", "DINHEIRO", "SEGREDO", "NUNCA", "APRENDA", "VÃDEO", "ATENÃ‡ÃƒO", "RETENÃ‡ÃƒO"}
        palavras_broll = {
            "DINHEIRO": "money",
            "MUDAR": "transition",
            "VÃDEO": "camera",
            "ERRO": "mistake",
            "SEGREDO": "mystery",
            "BRASIL": "brazil",
            "CIDADE": "city"
        }
        
        for idx, item in enumerate(json_timestamps):
            id_item = item["id"]
            text = item["text"].upper()
            words = text.split()
            
            # PadrÃµes heurÃ­sticos
            zoom = idx == 0 or any(w in palavras_impacto for w in words) or (idx % 4 == 0)
            sfx = "whoosh" if zoom and idx > 0 else ("pop" if any(w in palavras_impacto for w in words) else None)
            
            broll = None
            for w in words:
                clean_w = w.strip(".,!?")
                if clean_w in palavras_broll:
                    broll = palavras_broll[clean_w]
                    break
                    
            style = "emphasis" if any(w in palavras_impacto for w in words) else "standard"
            
            ai_decisions[id_item] = {
                "id": id_item,
                "zoom": zoom,
                "sfx": sfx,
                "broll_keyword": broll,
                "text_style": style
            }
            
    # Aplica as decisÃµes no JSON original
    resultado_enriquecido = []
    for item in json_timestamps:
        dec = ai_decisions.get(item["id"], {
            "zoom": False,
            "sfx": None,
            "broll_keyword": None,
            "text_style": "standard"
        })
        
        item_copy = item.copy()
        item_copy["zoom"] = dec.get("zoom", False)
        item_copy["sfx"] = dec.get("sfx")
        item_copy["broll_keyword"] = dec.get("broll_keyword")
        item_copy["text_style"] = dec.get("text_style", "standard")
        
        resultado_enriquecido.append(item_copy)
        
    return resultado_enriquecido


def compile_ai_edit_to_ffmpeg(video_path: str, json_ai_processed: list, output_path: str, background_music_path: str = None, pasta_assets: str = None) -> bool:
    """
    Traduz todas as decisÃµes da IA em filtros lineares do FFmpeg de forma integrada em uma Ãºnica passagem:
    1. Executa jump-cuts (remoÃ§Ã£o de silÃªncio).
    2. Aplica re-enquadramento (Face-Tracking) e zoom dinÃ¢mico (Punch-In de 15% nos picos da IA).
    3. Renderiza legendas ASS estilizadas com destaque colorido.
    4. Sincroniza SFX (pop/whoosh) nos tempos das palavras e aplica ducking de Ã¡udio na trilha.
    """
    logger.info(f"Compilando ediÃ§Ã£o de IA contextual para: {output_path}")
    try:
        import cv2
        import numpy as np
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
        
        # 1. Analisa e remove silÃªncios antes do processamento frame-a-frame
        fd_temp_jc, path_temp_jc = tempfile.mkstemp(suffix="_jc.mp4")
        os.close(fd_temp_jc)
        
        if not remove_silences(video_path, path_temp_jc):
            logger.warning("Falha ao prÃ©-processar silÃªncios. Usando vÃ­deo original.")
            shutil.copy2(video_path, path_temp_jc)
            
        # 2. Configura detector facial para enquadramento e zoom dinÃ¢mico
        modelo_path = r"D:\CORTE VIRAL\files\face_detector.tflite"
        base_options = mp_python.BaseOptions(model_asset_path=modelo_path)
        options = mp_vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.35)
        detector = mp_vision.FaceDetector.create_from_options(options)
        
        cap = cv2.VideoCapture(path_temp_jc)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        target_w = int(height * (9/16))
        if target_w > width:
            target_w = width
            
        # Primeiro passe: Rastreia a face em cada frame do vÃ­deo
        x_centers = []
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            results = detector.detect(mp_image)
            
            x_center = width / 2.0
            if results.detections:
                bbox = results.detections[0].bounding_box
                x_center = bbox.origin_x + bbox.width / 2.0
            x_centers.append(x_center)
        cap.release()
        
        # SuavizaÃ§Ã£o
        window = 30
        x_centers_smooth = np.convolve(x_centers, np.ones(window)/window, mode='same')
        
        # Segundo passe: Grava os frames cropados com face-tracking e zoom condicional
        fd_temp_cropped, path_temp_cropped = tempfile.mkstemp(suffix="_crop.mp4")
        os.close(fd_temp_cropped)
        
        cap = cv2.VideoCapture(path_temp_jc)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(path_temp_cropped, fourcc, fps, (1080, 1920))
        
        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            time_sec = frame_idx / fps
            
            # Verifica se estÃ¡ em perÃ­odo de zoom decidido pela IA
            em_zoom = False
            for item in json_ai_processed:
                if item.get("zoom") and item["start"] <= time_sec <= item["end"]:
                    em_zoom = True
                    break
                    
            x_center = x_centers_smooth[frame_idx]
            
            # Modifica tamanho do crop caso esteja com zoom ativo (Punch-In de 15%)
            fator_escala = 0.85 if em_zoom else 1.0
            w_crop = int(target_w * fator_escala)
            h_crop = int(height * fator_escala)
            
            crop_x = int(x_center - w_crop / 2.0)
            crop_x = max(0, min(width - w_crop, crop_x))
            crop_y = int((height - h_crop) / 2.0)
            
            cropped_frame = frame[crop_y:crop_y+h_crop, crop_x:crop_x+w_crop]
            resized_frame = cv2.resize(cropped_frame, (1080, 1920), interpolation=cv2.INTER_LANCZOS4)
            out.write(resized_frame)
            frame_idx += 1
            
        cap.release()
        out.release()
        
        # Adiciona Ã¡udio do jumpcut de volta ao vÃ­deo cropado
        fd_temp_merged, path_temp_merged = tempfile.mkstemp(suffix="_merge.mp4")
        os.close(fd_temp_merged)
        
        cmd_merge = [
            FFMPEG_PATH, "-y",
            "-i", path_temp_cropped,
            "-i", path_temp_jc,
            "-map", "0:v", "-map", "1:a?",
            "-c:v", "copy", "-c:a", "aac",
            path_temp_merged
        ]
        subprocess.run(cmd_merge, check=True)
        
        # 3. Gera e aplica legendas ASS estilizadas
        fd_ass, path_ass = tempfile.mkstemp(suffix=".ass")
        os.close(fd_ass)
        
        generate_subtitles_ass(json_ai_processed, path_ass)
        
        escaped_ass_path = path_ass.replace("\\", "/").replace(":", "\\:")
        fd_temp_subbed, path_temp_subbed = tempfile.mkstemp(suffix="_sub.mp4")
        os.close(fd_temp_subbed)
        
        cmd_sub = [
            FFMPEG_PATH, "-y",
            "-i", path_temp_merged,
            "-vf", f"ass='{escaped_ass_path}'",
            "-c:a", "copy",
            path_temp_subbed
        ]
        subprocess.run(cmd_sub, check=True)
        
        # 4. Mixagem final de efeitos sonoros e mÃºsica de fundo
        # Se background_music_path ou SFX forem passados, aplica sidechain compressor
        inputs = ["-i", path_temp_subbed]
        amix_filters = ["[0:a]"]
        input_idx = 1
        
        if pasta_assets:
            for item in json_ai_processed:
                sfx_name = item.get("sfx")
                if sfx_name:
                    sfx_file = os.path.join(pasta_assets, f"{sfx_name}.wav")
                    if not os.path.exists(sfx_file):
                        # Tenta .mp3
                        sfx_file = os.path.join(pasta_assets, f"{sfx_name}.mp3")
                    if os.path.exists(sfx_file):
                        inputs += ["-i", sfx_file]
                        delay_ms = int(item["start"] * 1000)
                        amix_filters.append(f"[{input_idx}:a]adelay={delay_ms}|{delay_ms}[sfx_{input_idx}];")
                        input_idx += 1
                        
        if background_music_path and os.path.exists(background_music_path):
            inputs += ["-i", background_music_path]
            music_idx = input_idx
            
            # Mixagem de SFX primeiro, depois sidechain compression da trilha
            audio_graph = "".join(amix_filters)
            audio_graph += "".join(f"[sfx_{i}]" for i in range(1, music_idx))
            audio_graph += f"amix=inputs={music_idx}:duration=first[voice_mix];"
            audio_graph += f"[{music_idx}:a]volume=0.25[bg_music];"
            audio_graph += f"[bg_music][voice_mix]sidechaincompress=threshold=0.08:ratio=8:attack=15:release=200[bg_ducked];"
            audio_graph += f"[voice_mix][bg_ducked]amix=inputs=2:duration=first[aout]"
            
            comando_final = [FFMPEG_PATH, "-y"] + inputs + [
                "-filter_complex", audio_graph,
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "h264_nvenc",
                "-c:a", "aac",
                output_path
            ]
        else:
            # Sem mÃºsica de fundo, apenas mixa SFX se houver
            if input_idx > 1:
                audio_graph = "".join(amix_filters)
                audio_graph += "".join(f"[sfx_{i}]" for i in range(1, input_idx))
                audio_graph += f"amix=inputs={input_idx}:duration=first[aout]"
                comando_final = [FFMPEG_PATH, "-y"] + inputs + [
                    "-filter_complex", audio_graph,
                    "-map", "0:v",
                    "-map", "[aout]",
                    "-c:v", "h264_nvenc",
                    "-c:a", "aac",
                    output_path
                ]
            else:
                comando_final = [FFMPEG_PATH, "-y", "-i", path_temp_subbed, "-c", "copy", output_path]
                
        subprocess.run(comando_final, check=True)
        logger.info(f"EdiÃ§Ã£o de IA contextual compilada com sucesso: {output_path}")
        
        # Limpeza de temporÃ¡rios
        for p in [path_temp_jc, path_temp_cropped, path_temp_merged, path_ass, path_temp_subbed]:
            if os.path.exists(p):
                os.remove(p)
                
        return True
    except Exception as e:
        logger.error(f"Erro ao compilar ediÃ§Ã£o de IA: {e}")
        return False


