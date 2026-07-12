"""
musica.py
---------
Módulo de música para o Viral Cutter.
Adiciona trilha sonora a vídeos com sincronização automática de batida.

Funcionalidades planejadas:
1. Upload de música (.mp3, .wav)
2. Detecção automática de beats/batidas (librosa)
3. Sincronização das legendas com os beats
4. Overlay de áudio: mixar música + áudio original
5. Fade in/out automático
6. Ajuste de volume (música vs. fala)
7. Drop detection — identifica os "drops" da música para
   sincronizar com momentos de impacto visual

Dependências necessárias:
    pip install librosa soundfile
    (ffmpeg já está instalado)

Status: ESQUELETO — estrutura pronta, implementação pendente.
"""

import os
import json
import subprocess
import tempfile


# ── Detecção de beats ─────────────────────────────────────────────────────────

def detectar_beats(caminho_musica: str) -> dict:
    """
    Analisa uma música e retorna timestamps dos beats.

    Retorna:
        {
            "bpm": float,
            "beats": [float],        # timestamps em segundos de cada batida
            "downbeats": [float],    # batidas fortes (início de compasso)
            "drops": [float],        # momentos de alta energia (drops)
            "duracao": float,
        }
    """
    try:
        import librosa
    except ImportError:
        raise ImportError(
            "librosa não instalado. Execute: pip install librosa soundfile"
        )

    print(f"🎵 Analisando beats em: {os.path.basename(caminho_musica)}")

    # Carrega áudio
    y, sr = librosa.load(caminho_musica, sr=22050)
    duracao = librosa.get_duration(y=y, sr=sr)

    # Detecta tempo e beats
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    # Detecta onset strength para encontrar "drops"
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    # Drops = picos de energia acima do percentil 90
    import numpy as np
    threshold = np.percentile(onset_env, 90)
    drop_frames = np.where(onset_env > threshold)[0]
    drop_times = librosa.frames_to_time(drop_frames, sr=sr).tolist()

    # Downbeats (simplificado: cada 4 beats)
    downbeats = beat_times[::4] if len(beat_times) >= 4 else beat_times

    bpm = float(tempo) if not hasattr(tempo, '__len__') else float(tempo[0])

    print(f"✅ BPM: {bpm:.0f} | {len(beat_times)} beats | {len(drop_times)} drops")

    return {
        "bpm": bpm,
        "beats": beat_times,
        "downbeats": downbeats,
        "drops": drop_times,
        "duracao": duracao,
    }


# ── Sincronização legendas + beats ────────────────────────────────────────────

def sincronizar_legendas_com_beats(
    palavras: list,
    beats_info: dict,
    modo: str = "beat"
) -> list:
    """
    Ajusta o timing das legendas para coincidir com os beats da música.

    Modos:
        "beat"  — cada palavra aparece no beat mais próximo
        "drop"  — palavras-chave aparecem nos drops (alta energia)
        "livre" — mantém timing original, não sincroniza

    Parâmetros:
        palavras: lista de {texto, inicio, fim}
        beats_info: retorno de detectar_beats()
        modo: tipo de sincronização

    Retorna:
        lista de palavras com timestamps ajustados
    """
    if modo == "livre" or not beats_info:
        return palavras

    beats = beats_info.get("beats", [])
    drops = beats_info.get("drops", [])

    if not beats:
        return palavras

    palavras_sync = []

    for p in palavras:
        p_sync = dict(p)

        if modo == "beat":
            # Encontra o beat mais próximo do início da palavra
            beat_proximo = min(beats, key=lambda b: abs(b - p["inicio"]))
            offset = beat_proximo - p["inicio"]
            p_sync["inicio"] = p["inicio"] + offset
            p_sync["fim"] = p["fim"] + offset

        elif modo == "drop":
            # Palavras mais longas (potencialmente importantes) vão para os drops
            if len(p["texto"]) > 5 and drops:
                drop_proximo = min(drops, key=lambda d: abs(d - p["inicio"]))
                if abs(drop_proximo - p["inicio"]) < 2.0:
                    p_sync["inicio"] = drop_proximo
                    p_sync["fim"] = drop_proximo + (p["fim"] - p["inicio"])

        palavras_sync.append(p_sync)

    return palavras_sync


# ── Overlay de áudio ──────────────────────────────────────────────────────────

def mixar_audio(
    caminho_video: str,
    caminho_musica: str,
    caminho_saida: str,
    volume_musica: float = 0.3,
    volume_fala: float = 1.0,
    fade_in: float = 1.0,
    fade_out: float = 2.0,
    progresso_callback=None,
) -> bool:
    """
    Mixa a música com o áudio original do vídeo via FFmpeg.

    Parâmetros:
        volume_musica: 0.0 a 1.0 — volume da música (0.3 = 30%)
        volume_fala: 0.0 a 1.0 — volume do áudio original
        fade_in: segundos de fade in da música
        fade_out: segundos de fade out da música
    """
    def log(msg):
        print(msg)
        if progresso_callback:
            progresso_callback(msg)

    log("🎵 Mixando áudio...")

    # Obtém duração do vídeo
    duracao = _obter_duracao(caminho_video)
    if duracao <= 0:
        log("❌ Não foi possível obter duração do vídeo.")
        return False

    # FFmpeg: mixa dois áudios
    # [0:a] = áudio do vídeo, [1:a] = música
    fade_out_start = max(0, duracao - fade_out)

    filtro = (
        f"[1:a]volume={volume_musica},"
        f"afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={fade_out_start}:d={fade_out}[musica];"
        f"[0:a]volume={volume_fala}[fala];"
        f"[fala][musica]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", caminho_video,
        "-i", caminho_musica,
        "-filter_complex", filtro,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        caminho_saida,
    ]

    resultado = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )

    if resultado.returncode != 0:
        log(f"❌ Erro no FFmpeg:\n{resultado.stderr[-300:]}")
        return False

    if os.path.exists(caminho_saida):
        log("✅ Áudio mixado com sucesso!")
        return True

    log("❌ Arquivo de saída não gerado.")
    return False


def _obter_duracao(caminho: str) -> float:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", caminho
    ]
    resultado = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if resultado.returncode != 0:
        return 0.0
    dados = json.loads(resultado.stdout)
    return float(dados.get("format", {}).get("duration", 0))
