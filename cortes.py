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


def calcular_threshold_adaptativo(audio, offset_db: int = 16) -> int:
    """
    Calcula o threshold de silêncio com base no volume médio do áudio.

    Um threshold fixo (ex.: -40dB) falha nos extremos:
    - Vídeo com ruído de fundo alto (festa, rua): quase nada fica abaixo
      de -40dB e nenhum silêncio é detectado.
    - Áudio de estúdio muito limpo: até respirações ficam abaixo de -40dB
      e são cortadas, deixando o ritmo artificial.

    A solução é medir o volume médio (dBFS) e considerar silêncio tudo
    que estiver `offset_db` abaixo dele, limitado a uma faixa segura.

    Parâmetros:
        audio: AudioSegment já carregado
        offset_db: quantos dB abaixo da média conta como silêncio

    Retorna:
        threshold em dB (entre -60 e -25)
    """
    dbfs = audio.dBFS
    if dbfs == float("-inf"):  # áudio totalmente mudo
        return -60
    return int(max(-60, min(-25, dbfs - offset_db)))


def refinar_limites_com_palavras(
    segmentos: list,
    transcricao: dict,
    pad_inicio_s: float = 0.20,
    pad_fim_s: float = 0.30,
) -> list:
    """
    Ajusta o início/fim de cada segmento para os limites reais das palavras.

    O Whisper roda com word_timestamps=True, mas os segmentos da análise
    usam tempos de *segmento* (frases inteiras, arredondados). Resultado:
    o corte pode cair no meio de uma palavra. Esta função:

    1. Move o INÍCIO para o começo da primeira palavra dentro do segmento,
       menos um respiro (pad_inicio_s) — o clipe abre já na fala, sem
       decapitar a primeira sílaba.
    2. Move o FIM para o final da última palavra dentro do segmento,
       mais um respiro (pad_fim_s) — a última palavra termina inteira.

    Parâmetros:
        segmentos: lista de segmentos com "inicio" e "fim" em segundos
        transcricao: resultado do Whisper (dict com "segments" → "words")
        pad_inicio_s: respiro antes da primeira palavra
        pad_fim_s: respiro depois da última palavra

    Retorna:
        nova lista de segmentos com limites refinados (originais intactos)
    """
    # Achata todas as palavras da transcrição em uma lista ordenada
    palavras = [
        {"start": float(w["start"]), "end": float(w["end"])}
        for seg in (transcricao or {}).get("segments", [])
        for w in seg.get("words", [])
        if w.get("start") is not None and w.get("end") is not None
    ]
    if not palavras:
        return list(segmentos)
    palavras.sort(key=lambda w: w["start"])

    refinados = []
    for seg in segmentos:
        inicio, fim = float(seg["inicio"]), float(seg["fim"])

        # Palavras que pertencem ao segmento (tolerância de 0.5s nas bordas
        # para absorver o arredondamento dos timestamps de segmento)
        dentro = [w for w in palavras if w["end"] > inicio - 0.5 and w["start"] < fim + 0.5]
        candidatas = [w for w in dentro if w["start"] >= inicio - 0.5]
        if not candidatas:
            refinados.append(seg.copy())
            continue

        primeira = min(candidatas, key=lambda w: w["start"])
        ultimas = [w for w in dentro if w["end"] <= fim + 0.5]
        ultima = max(ultimas, key=lambda w: w["end"]) if ultimas else candidatas[-1]

        novo_inicio = max(0.0, primeira["start"] - pad_inicio_s)
        novo_fim = ultima["end"] + pad_fim_s

        seg_novo = seg.copy()
        if novo_fim > novo_inicio:  # segurança: nunca gera segmento invertido
            seg_novo["inicio"] = round(novo_inicio, 3)
            seg_novo["fim"] = round(novo_fim, 3)
        refinados.append(seg_novo)

    return refinados


def calcular_intervalos_fala(
    duracao_ms: int,
    silencios: list,
    margem_ms: int = 120,
    trecho_minimo_ms: int = 120,
) -> list:
    """Converte silêncios em intervalos que devem permanecer no vídeo."""
    if duracao_ms <= 0:
        return []

    cortes = []
    for inicio, fim in sorted(silencios or []):
        inicio = max(0, int(inicio) + margem_ms)
        fim = min(duracao_ms, int(fim) - margem_ms)
        if fim > inicio:
            cortes.append((inicio, fim))

    intervalos = []
    cursor = 0
    for inicio, fim in cortes:
        if inicio - cursor >= trecho_minimo_ms:
            intervalos.append((cursor, inicio))
        cursor = max(cursor, fim)
    if duracao_ms - cursor >= trecho_minimo_ms:
        intervalos.append((cursor, duracao_ms))
    return intervalos or [(0, duracao_ms)]


def _analisar_silencios_ffmpeg(caminho_video: str, min_silencio_ms: int, threshold_db) -> tuple:
    """
    Detecta silêncios via FFmpeg (silencedetect) — ordens de magnitude mais
    rápido que o pydub, que carrega o áudio inteiro na RAM e processa
    janela a janela em Python puro.

    Se threshold_db=None, mede antes o volume médio (volumedetect) e usa
    média − 16dB, travado entre −60 e −25 (mesma regra do adaptativo).

    Retorna (duracao_ms, threshold_db, silencios) ou None em falha —
    o chamador então usa o caminho pydub tradicional.
    """
    from ffmpeg_utils import obter_duracao
    import re

    duracao_s = obter_duracao(caminho_video)
    if duracao_s <= 0:
        return None

    try:
        # 1. Threshold adaptativo via volumedetect (só áudio, rápido)
        if threshold_db is None:
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-i", caminho_video, "-vn",
                 "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            m = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", r.stderr)
            if not m:
                return None
            media_db = float(m.group(1))
            threshold_db = int(max(-60, min(-25, media_db - 16)))
            print(f"🔉 Threshold adaptativo: {threshold_db}dB (volume médio {media_db:.1f}dB) [FFmpeg]")

        # 2. Silêncios via silencedetect
        dur_min_s = max(200, int(min_silencio_ms)) / 1000.0
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", caminho_video, "-vn",
             "-af", f"silencedetect=noise={int(threshold_db)}dB:d={dur_min_s:.3f}",
             "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        inicios = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", r.stderr)]
        fins = [float(x) for x in re.findall(r"silence_end:\s*(-?[\d.]+)", r.stderr)]

        silencios = []
        for idx, ini in enumerate(inicios):
            fim = fins[idx] if idx < len(fins) else duracao_s  # silêncio até o final
            silencios.append((max(0, int(ini * 1000)), int(fim * 1000)))

        return (int(duracao_s * 1000), int(threshold_db), silencios)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def remover_silencios(
    caminho_video: str,
    caminho_saida: str,
    min_silencio_ms: int = 700,
    threshold_db: int = None,
    margem_ms: int = 120,
) -> dict:
    """
    Remove pausas internas e preserva uma pequena respiração entre falas.

    threshold_db=None (padrão) ativa o threshold adaptativo, calculado
    a partir do volume médio do áudio — mais preciso que um valor fixo.

    Caminho rápido: FFmpeg silencedetect. Fallback: pydub.
    """
    analise = _analisar_silencios_ffmpeg(caminho_video, min_silencio_ms, threshold_db)
    if analise is not None:
        duracao_ms, threshold_db, silencios = analise
    else:
        audio = AudioSegment.from_file(caminho_video)
        duracao_ms = len(audio)
        if threshold_db is None:
            threshold_db = calcular_threshold_adaptativo(audio)
            print(f"🔉 Threshold adaptativo: {threshold_db}dB (volume médio {audio.dBFS:.1f}dBFS)")
        silencios = silence.detect_silence(
            audio,
            min_silence_len=max(200, int(min_silencio_ms)),
            silence_thresh=int(threshold_db),
        )
    intervalos = calcular_intervalos_fala(duracao_ms, silencios, margem_ms)

    if len(intervalos) == 1 and intervalos[0] == (0, duracao_ms):
        return {"alterado": False, "removido_ms": 0, "intervalos": intervalos}

    filtros = []
    entradas_concat = []
    for indice, (inicio, fim) in enumerate(intervalos):
        inicio_s, fim_s = inicio / 1000, fim / 1000
        filtros.append(
            f"[0:v]trim=start={inicio_s:.3f}:end={fim_s:.3f},"
            f"setpts=PTS-STARTPTS[v{indice}]"
        )
        filtros.append(
            f"[0:a]atrim=start={inicio_s:.3f}:end={fim_s:.3f},"
            f"asetpts=PTS-STARTPTS[a{indice}]"
        )
        entradas_concat.append(f"[v{indice}][a{indice}]")

    filtros.append(
        "".join(entradas_concat)
        + f"concat=n={len(intervalos)}:v=1:a=1[vout][aout]"
    )
    cmd = ["ffmpeg", "-y", "-i", caminho_video, "-filter_complex", ";".join(filtros)]
    cmd += ["-map", "[vout]", "-map", "[aout]"]
    cmd += argumentos_encoder(temporario=True)
    cmd += ["-c:a", "aac", "-pix_fmt", "yuv420p", "-movflags", "+faststart", caminho_saida]

    resultado = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if resultado.returncode != 0:
        if os.path.exists(caminho_saida):
            os.remove(caminho_saida)
        raise RuntimeError(f"FFmpeg não conseguiu remover os silêncios: {resultado.stderr[-600:]}")

    mantido_ms = sum(fim - inicio for inicio, fim in intervalos)
    return {
        "alterado": True,
        "removido_ms": max(0, duracao_ms - mantido_ms),
        "intervalos": intervalos,
    }


def detectar_silencio(caminho_video: str, min_silencio_ms: int = 500, threshold_db: int = None) -> list:
    """
    Detecta os períodos de silêncio no vídeo.

    Parâmetros:
        caminho_video: caminho para o arquivo de vídeo
        min_silencio_ms: duração mínima em ms para considerar um silêncio (padrão: 500ms)
        threshold_db: volume abaixo do qual considera silêncio
                      (None = adaptativo, baseado no volume médio do áudio)

    Retorna:
        lista de tuplas (inicio_ms, fim_ms) com os períodos de silêncio
    """
    print("🔇 Analisando silêncios no áudio...")

    # Caminho rápido: FFmpeg silencedetect
    analise = _analisar_silencios_ffmpeg(caminho_video, min_silencio_ms, threshold_db)
    if analise is not None:
        _, _, periodos_silencio = analise
        print(f"✅ {len(periodos_silencio)} períodos de silêncio encontrados. [FFmpeg]")
        return periodos_silencio

    # Fallback: pydub
    audio = AudioSegment.from_file(caminho_video)

    if threshold_db is None:
        threshold_db = calcular_threshold_adaptativo(audio)
        print(f"🔉 Threshold adaptativo: {threshold_db}dB")

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
        """
        Encontra o silêncio MAIS PRÓXIMO de um timestamp.

        Versão anterior retornava o PRIMEIRO silêncio dentro da margem
        (ordem da lista), o que podia puxar o corte para o lado errado.
        Agora compara todos os candidatos e escolhe o de menor distância.
        """
        melhor = None
        menor_distancia = None
        for inicio_s, fim_s in silencias:
            meio_silencio = (inicio_s + fim_s) / 2
            distancia = abs(meio_silencio - tempo_ms)
            if distancia <= margem_ms and (menor_distancia is None or distancia < menor_distancia):
                melhor = meio_silencio
                menor_distancia = distancia
        if melhor is not None:
            return melhor / 1000  # converte para segundos
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


def validar_hook(seg: dict, duracao_min_s: float = 1.0, duracao_max_s: float = 5.0) -> tuple:
    """
    Valida os dados de hook de um segmento e retorna (hook_inicio, hook_fim)
    ou None se o hook não deve ser aplicado.

    Regras:
    - hook_inicio/hook_fim precisam existir e ser números válidos
    - o hook precisa estar DENTRO do clipe (com folga de 0.2s nas bordas)
    - duração entre duracao_min_s e duracao_max_s
    - se o hook começa nos primeiros 5s do clipe, não aplica (o clipe já
      abre com a frase forte — cold open seria repetição imediata)
    """
    try:
        h_ini = float(seg.get("hook_inicio"))
        h_fim = float(seg.get("hook_fim"))
        inicio = float(seg["inicio"])
        fim = float(seg["fim"])
    except (TypeError, ValueError, KeyError):
        return None

    if h_ini < inicio - 0.2 or h_fim > fim + 0.2:
        return None  # hook fora do clipe
    duracao = h_fim - h_ini
    if duracao < duracao_min_s or duracao > duracao_max_s:
        return None  # duração fora da faixa útil
    if h_ini <= inicio + 5.0:
        return None  # clipe já abre com a frase forte

    return (max(inicio, h_ini), min(fim, h_fim))


def cortar_clipe_com_hook(
    caminho_video: str,
    inicio: float,
    fim: float,
    hook_inicio: float,
    hook_fim: float,
    caminho_saida: str,
) -> bool:
    """
    Corta o clipe abrindo com o HOOK (cold open): a frase de maior impacto
    aparece primeiro, depois o clipe roda do início normalmente.

    Estrutura do resultado: [hook 1.5-3.5s] + [clipe completo inicio→fim]

    É o padrão dos cortes virais de referência — os primeiros 2 segundos
    decidem se a pessoa continua assistindo.
    """
    if inicio < 0 or fim <= inicio or hook_fim <= hook_inicio:
        print(f"⚠️ Hook inválido: clipe {inicio}-{fim}, hook {hook_inicio}-{hook_fim}")
        return False

    filtros = (
        # Trecho 1: o hook (frase de impacto)
        f"[0:v]trim=start={hook_inicio:.3f}:end={hook_fim:.3f},setpts=PTS-STARTPTS[v0];"
        f"[0:a]atrim=start={hook_inicio:.3f}:end={hook_fim:.3f},asetpts=PTS-STARTPTS[a0];"
        # Trecho 2: o clipe completo
        f"[0:v]trim=start={inicio:.3f}:end={fim:.3f},setpts=PTS-STARTPTS[v1];"
        f"[0:a]atrim=start={inicio:.3f}:end={fim:.3f},asetpts=PTS-STARTPTS[a1];"
        # Emenda os dois
        f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[vout][aout]"
    )

    cmd = ["ffmpeg", "-y", "-i", caminho_video, "-filter_complex", filtros]
    cmd += ["-map", "[vout]", "-map", "[aout]"]
    cmd += argumentos_encoder(temporario=True)
    cmd += [
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-movflags", "+faststart",
        caminho_saida,
    ]

    resultado = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if resultado.returncode != 0:
        print(f"⚠️ FFmpeg falhou no corte com hook: {resultado.stderr[-600:]}")
        if os.path.exists(caminho_saida):
            os.remove(caminho_saida)
    return resultado.returncode == 0


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

    resultado = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if resultado.returncode != 0:
        print(f"⚠️ FFmpeg falhou ao cortar o clipe: {resultado.stderr[-600:]}")
        if os.path.exists(caminho_saida):
            os.remove(caminho_saida)
    return resultado.returncode == 0
