"""
cortes.py
---------
Responsável por detectar silêncios e realizar os cortes no vídeo.
Usa pydub para análise de áudio e ffmpeg para os cortes finais.
"""

import os
import subprocess
from pydub import AudioSegment, silence
from ffmpeg_utils import argumentos_encoder


def detectar_silencio(caminho_video: str, min_silencio_ms: int = 500, threshold_db: int = -40) -> list:
    """
    Detecta os períodos de silêncio no vídeo.

    Parâmetros:
        caminho_video: caminho para o arquivo de vídeo
        min_silencio_ms: duração mínima em ms para considerar um silêncio (padrão: 500ms)
        threshold_db: volume abaixo do qual considera silêncio (padrão: -40dB)

    Retorna:
        lista de tuplas (inicio_ms, fim_ms) com os períodos de silêncio
    """
    print("🔇 Analisando silêncios no áudio...")
    audio = AudioSegment.from_file(caminho_video)

    periodos_silencio = silence.detect_silence(
        audio,
        min_silence_len=min_silencio_ms,
        silence_thresh=threshold_db
    )

    print(f"✅ {len(periodos_silencio)} períodos de silêncio encontrados.")
    return periodos_silencio


def ajustar_cortes_com_silencio(segmentos: list, silencias: list, margem_ms: int = 200) -> list:
    """
    Ajusta os pontos de corte dos segmentos para coincidirem
    com os silêncios mais próximos (corte mais natural).

    Parâmetros:
        segmentos: lista de segmentos da IA (com inicio e fim em segundos)
        silencias: lista de silêncios detectados (em milissegundos)
        margem_ms: margem máxima de ajuste em milissegundos

    Retorna:
        lista de segmentos com pontos de corte ajustados
    """
    def encontrar_silencio_proximo(tempo_ms, silencias, margem_ms):
        """Encontra o silêncio mais próximo de um timestamp."""
        for inicio_s, fim_s in silencias:
            meio_silencio = (inicio_s + fim_s) / 2
            if abs(meio_silencio - tempo_ms) <= margem_ms:
                return meio_silencio / 1000  # converte para segundos
        return tempo_ms / 1000  # retorna original se não encontrar

    segmentos_ajustados = []
    for seg in segmentos:
        inicio_ms = seg["inicio"] * 1000
        fim_ms = seg["fim"] * 1000

        novo_inicio = encontrar_silencio_proximo(inicio_ms, silencias, margem_ms)
        novo_fim = encontrar_silencio_proximo(fim_ms, silencias, margem_ms)

        seg_ajustado = seg.copy()
        seg_ajustado["inicio"] = novo_inicio
        seg_ajustado["fim"] = novo_fim
        segmentos_ajustados.append(seg_ajustado)

    return segmentos_ajustados


def cortar_clipe(caminho_video: str, inicio: float, fim: float, caminho_saida: str) -> bool:
    """
    Corta um trecho do vídeo usando FFmpeg.

    Parâmetros:
        caminho_video: vídeo original
        inicio: tempo de início em segundos
        fim: tempo de fim em segundos
        caminho_saida: onde salvar o clipe cortado

    Retorna:
        True se o corte foi bem-sucedido, False se houve erro
    """
    duracao = fim - inicio
    if inicio < 0 or duracao <= 0:
        print(f"⚠️ Corte inválido: início={inicio}, fim={fim}")
        return False

    cmd = [
        "ffmpeg",
        "-y",                          # sobrescreve sem perguntar
        "-ss", str(inicio),            # começa aqui
        "-i", caminho_video,           # arquivo de entrada
        "-t", str(duracao),            # duração do clipe
    ]
    cmd += argumentos_encoder(temporario=True)
    cmd += [
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",                 # codec de áudio
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",     # otimiza para web
        caminho_saida
    ]

    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        print(f"⚠️ FFmpeg falhou ao cortar o clipe: {resultado.stderr[-600:]}")
        if os.path.exists(caminho_saida):
            os.remove(caminho_saida)
    return resultado.returncode == 0
