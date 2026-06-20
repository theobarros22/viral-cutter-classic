"""
analise.py
----------
Transcreve o vídeo com Whisper e identifica segmentos.

Dois modos:
- Modo IA (online): usa Claude API para análise semântica profunda
- Modo offline: usa só Whisper + algoritmo local, sem API, sem custo
"""

import whisper
import torch
import json
import re
import subprocess
import os
import tempfile
import hashlib
from runtime import pasta_dados


_MODELO_WHISPER_ATUAL = {"chave": None, "modelo": None}


def _obter_duracao_segundos(caminho: str) -> float:
    """Retorna a duração do arquivo em segundos usando ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", caminho
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        return 0.0
    dados = json.loads(resultado.stdout)
    return float(dados.get("format", {}).get("duration", 0))


def _extrair_audio_wav(caminho_video: str, caminho_wav: str,
                       inicio: float = 0, duracao: float = None) -> bool:
    """
    Extrai áudio do vídeo para WAV 16kHz mono com FFmpeg.
    Muito menor que o vídeo original — resolve o problema de memória.
    """
    cmd = ["ffmpeg", "-y", "-i", caminho_video]
    if inicio > 0:
        cmd = ["ffmpeg", "-y", "-ss", str(inicio), "-i", caminho_video]
    if duracao is not None:
        cmd += ["-t", str(duracao)]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le", caminho_wav]

    resultado = subprocess.run(cmd, capture_output=True)
    return resultado.returncode == 0 and os.path.exists(caminho_wav)


def transcrever_video(caminho_video: str, idioma: str = "pt", modelo_nome: str = "small") -> dict:
    """
    Transcreve o áudio do vídeo usando Whisper na GPU se disponível.

    Para vídeos longos (>20 min), processa em chunks de 20 minutos
    para evitar estouro de memória no espectrograma.
    """
    cache = _carregar_cache_transcricao(caminho_video, idioma, modelo_nome)
    if cache is not None:
        print("⚡ Transcrição encontrada no cache. Pulando Whisper.")
        return cache

    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"

    if dispositivo == "cuda":
        nome_gpu = torch.cuda.get_device_name(0)
        print(f"⚡ GPU detectada: {nome_gpu} — usando aceleração!")
    else:
        print("💻 GPU não disponível — usando CPU (mais lento)")

    print(f"🎙️ Carregando modelo Whisper '{modelo_nome}'...")
    chave_modelo = (modelo_nome, dispositivo)
    modelo = _MODELO_WHISPER_ATUAL["modelo"] if _MODELO_WHISPER_ATUAL["chave"] == chave_modelo else None
    if modelo is None:
        # Mantém somente um modelo na memória para não estourar a VRAM ao
        # alternar entre small/medium/large.
        _MODELO_WHISPER_ATUAL["modelo"] = None
        if dispositivo == "cuda":
            torch.cuda.empty_cache()
        modelo = whisper.load_model(modelo_nome, device=dispositivo)
        _MODELO_WHISPER_ATUAL["chave"] = chave_modelo
        _MODELO_WHISPER_ATUAL["modelo"] = modelo
    else:
        print(f"⚡ Modelo Whisper '{modelo_nome}' já carregado.")

    # Descobre a duração total do vídeo
    duracao_total = _obter_duracao_segundos(caminho_video)
    print(f"📏 Duração do vídeo: {duracao_total:.0f}s ({duracao_total/60:.1f} min)")

    CHUNK_SEGUNDOS = 1200  # 20 minutos por chunk

    if duracao_total <= CHUNK_SEGUNDOS:
        resultado = _transcrever_direto(modelo, caminho_video, idioma, dispositivo)
    else:
        resultado = _transcrever_em_chunks(
            modelo, caminho_video, idioma, dispositivo, duracao_total, CHUNK_SEGUNDOS
        )

    _salvar_cache_transcricao(caminho_video, idioma, modelo_nome, resultado)
    return resultado


def _caminho_cache_transcricao(caminho_video: str, idioma: str, modelo_nome: str) -> str:
    stat = os.stat(caminho_video)
    chave = f"{os.path.abspath(caminho_video)}|{stat.st_size}|{stat.st_mtime_ns}|{idioma}|{modelo_nome}"
    nome = hashlib.sha256(chave.encode("utf-8")).hexdigest() + ".json"
    pasta = os.path.join(pasta_dados(), "cache_transcricoes")
    os.makedirs(pasta, exist_ok=True)
    return os.path.join(pasta, nome)


def _carregar_cache_transcricao(caminho_video: str, idioma: str, modelo_nome: str):
    try:
        caminho = _caminho_cache_transcricao(caminho_video, idioma, modelo_nome)
        with open(caminho, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, ValueError):
        return None


def _salvar_cache_transcricao(caminho_video: str, idioma: str, modelo_nome: str, resultado: dict):
    try:
        caminho = _caminho_cache_transcricao(caminho_video, idioma, modelo_nome)
        with open(caminho, "w", encoding="utf-8") as arquivo:
            json.dump(resultado, arquivo, ensure_ascii=False)
    except (OSError, TypeError):
        pass


def _transcrever_direto(modelo, caminho_video: str, idioma: str, dispositivo: str) -> dict:
    """Extrai áudio para WAV temporário e transcreve de uma vez."""
    pasta_temp = tempfile.gettempdir()
    fd, wav_temp = tempfile.mkstemp(dir=pasta_temp, suffix="_whisper_audio.wav")
    os.close(fd)

    try:
        print("🔊 Extraindo áudio do vídeo...")
        if not _extrair_audio_wav(caminho_video, wav_temp):
            print("⚠️ Falha ao extrair áudio, tentando direto no vídeo...")
            resultado = modelo.transcribe(
                caminho_video, language=idioma, verbose=False,
                fp16=(dispositivo == "cuda")
            )
            return resultado

        print("🎙️ Transcrevendo áudio... (isso pode demorar alguns minutos)")
        resultado = modelo.transcribe(
            wav_temp, language=idioma, verbose=False,
            fp16=(dispositivo == "cuda")
        )
        print(f"✅ Transcrição concluída! {len(resultado['segments'])} segmentos encontrados.")
        return resultado

    finally:
        if os.path.exists(wav_temp):
            os.remove(wav_temp)


def _transcrever_em_chunks(modelo, caminho_video: str, idioma: str,
                            dispositivo: str, duracao_total: float,
                            chunk_seg: float) -> dict:
    """
    Divide o áudio em chunks de ~20 min, transcreve cada um,
    e junta os resultados com timestamps corrigidos.
    """
    pasta_temp = tempfile.gettempdir()
    n_chunks = int(duracao_total // chunk_seg) + 1
    print(f"📦 Vídeo longo — processando em {n_chunks} chunks de {chunk_seg//60:.0f} min")

    todos_segmentos = []
    texto_completo = ""

    for i in range(n_chunks):
        inicio = i * chunk_seg
        inicio_real = max(0, inicio - 5) if i > 0 else 0
        duracao = chunk_seg + (5 if i > 0 else 0)

        if inicio >= duracao_total:
            break

        fd, wav_chunk = tempfile.mkstemp(dir=pasta_temp, suffix=f"_whisper_chunk_{i}.wav")
        os.close(fd)
        print(f"   🔊 Chunk {i+1}/{n_chunks}: {inicio/60:.1f}min → {min((inicio+chunk_seg)/60, duracao_total/60):.1f}min")

        try:
            if not _extrair_audio_wav(caminho_video, wav_chunk, inicio_real, duracao):
                print(f"   ⚠️ Falha ao extrair chunk {i+1}, pulando...")
                continue

            resultado_chunk = modelo.transcribe(
                wav_chunk, language=idioma, verbose=False,
                fp16=(dispositivo == "cuda")
            )

            offset = inicio_real
            for seg in resultado_chunk["segments"]:
                seg_corrigido = dict(seg)
                seg_corrigido["start"] += offset
                seg_corrigido["end"]   += offset

                if todos_segmentos:
                    ultimo_fim = todos_segmentos[-1]["end"]
                    if seg_corrigido["start"] < ultimo_fim - 1:
                        continue

                todos_segmentos.append(seg_corrigido)

            texto_completo += resultado_chunk.get("text", "")

        finally:
            if os.path.exists(wav_chunk):
                os.remove(wav_chunk)

    print(f"✅ Transcrição concluída! {len(todos_segmentos)} segmentos encontrados.")

    return {
        "text": texto_completo,
        "segments": todos_segmentos,
        "language": idioma,
    }


def segmentar_por_assunto(
    transcricao: dict,
    duracao_min: int,
    duracao_max: int,
    nicho: str = "geral",
    modo_offline: bool = False
) -> list:
    """
    Identifica segmentos no vídeo.

    Parâmetros:
        modo_offline: True = usa algoritmo local (sem API, sem custo)
                      False = usa Claude API (mais preciso, precisa de créditos)
    """
    if modo_offline:
        print("📴 Modo offline — usando análise local...")
        return _segmentar_offline(transcricao, duracao_min, duracao_max)
    else:
        try:
            return _segmentar_com_ia(transcricao, duracao_min, duracao_max, nicho)
        except Exception as e:
            print(f"⚠️ Análise online falhou ({e}). Usando modo offline automaticamente...")
            return _segmentar_offline(transcricao, duracao_min, duracao_max)


def _segmentar_com_ia(transcricao: dict, duracao_min: int, duracao_max: int, nicho: str) -> list:
    """
    Usa Claude API para análise semântica profunda.
    Requer créditos na conta Anthropic.
    """
    import anthropic

    segmentos_texto = ""
    for seg in transcricao["segments"]:
        inicio = round(seg["start"], 1)
        fim    = round(seg["end"], 1)
        texto  = seg["text"].strip()
        segmentos_texto += f"[{inicio}s - {fim}s] {texto}\n"

    criterios_nicho = {
        "geral":     "engajamento geral, momentos de impacto emocional, frases marcantes",
        "podcast":   "opiniões fortes, revelações, discordâncias, histórias pessoais, frases de efeito",
        "casamento": "momentos emocionantes, votos, reações, surpresas, choro de alegria",
        "crime":     "revelações, viradas, momentos de tensão, confissões, detalhes chocantes",
        "esporte":   "gols, jogadas incríveis, reações, comemorações, momentos decisivos",
        "educacao":  "insights práticos, dicas aplicáveis, estatísticas surpreendentes, analogias",
    }
    criterio = criterios_nicho.get(nicho, criterios_nicho["geral"])

    prompt = f"""Você é um especialista em conteúdo viral para redes sociais.
Nicho do vídeo: {nicho.upper()}
Critérios de viralidade para este nicho: {criterio}

Abaixo está a transcrição de um vídeo longo com timestamps (em segundos).
Analise o conteúdo e identifique os melhores segmentos para criar clipes curtos e virais.

REGRAS:
- Cada clipe deve ter entre {duracao_min} e {duracao_max} segundos
- Prefira segmentos com começo e fim claros (início de assunto, conclusão, virada)
- Dê uma pontuação de viralidade de 1 a 10 para cada clipe
- Retorne APENAS um JSON válido, sem texto extra

TRANSCRIÇÃO:
{segmentos_texto}

Retorne um array JSON com este formato exato:
[
  {{
    "titulo": "Título chamativo para o clipe",
    "inicio": 12.5,
    "fim": 67.3,
    "score_viral": 8,
    "resumo": "Por que este trecho é viral: motivo curto"
  }}
]"""

    print("🤖 Analisando conteúdo com IA...")
    cliente = anthropic.Anthropic()
    resposta = cliente.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    texto_resposta = resposta.content[0].text.strip()
    if texto_resposta.startswith("```"):
        linhas = texto_resposta.split("\n")
        texto_resposta = "\n".join(linhas[1:-1])

    segmentos = json.loads(texto_resposta)
    print(f"✅ IA identificou {len(segmentos)} segmentos virais.")
    return segmentos


def _segmentar_offline(transcricao: dict, duracao_min: int, duracao_max: int) -> list:
    """
    Detecta segmentos usando apenas o Whisper — sem API, sem internet, sem custo.

    Como funciona:
    1. Analisa as pausas longas na fala (silêncios naturais entre assuntos)
    2. Detecta mudanças de assunto por palavras-chave de transição
    3. Agrupa segmentos respeitando duração mínima e máxima
    4. Gera título automático com as primeiras palavras do segmento
    5. Score baseado em heurísticas (perguntas, exclamações, palavras de impacto)
    """
    segs = transcricao["segments"]
    if not segs:
        return []

    print("📴 Detectando segmentos por pausas e transições de assunto...")

    # Palavras que indicam início de novo assunto
    palavras_transicao = {
        "pt": ["mas", "porém", "então", "agora", "falando nisso", "outro ponto",
               "além disso", "por outro lado", "voltando", "sobre isso", "a questão",
               "o problema", "o que acontece", "vou te contar", "imagina", "olha",
               "sabe o que", "e aí", "mas olha", "mas espera"],
        "en": ["but", "however", "now", "so", "anyway", "moving on", "speaking of",
               "the thing is", "here's the thing", "let me tell you", "imagine",
               "look", "you know what", "and then", "but wait"],
    }

    idioma = "pt"  # padrão
    transicoes = palavras_transicao.get(idioma, palavras_transicao["pt"])

    # Palavras de alto impacto para o score
    palavras_impacto = [
        "nunca", "sempre", "impossível", "incrível", "absurdo", "chocante",
        "verdade", "mentira", "segredo", "revelação", "confissão", "morte",
        "vida", "dinheiro", "traição", "amor", "ódio", "medo", "coragem",
        "never", "always", "impossible", "incredible", "secret", "truth",
        "shocking", "revealed", "money", "betrayal", "love", "hate", "fear"
    ]

    # ── Passo 1: Detecta pontos de corte naturais ─────────────────────────
    pontos_corte = [segs[0]["start"]]  # começa no início

    for i in range(1, len(segs)):
        seg_anterior = segs[i - 1]
        seg_atual    = segs[i]

        # Pausa longa entre segmentos (> 1.5 segundos = possível mudança de assunto)
        pausa = seg_atual["start"] - seg_anterior["end"]
        if pausa > 1.5:
            pontos_corte.append(seg_atual["start"])
            continue

        # Palavra de transição no início do segmento
        texto_lower = seg_atual["text"].strip().lower()
        for transicao in transicoes:
            if texto_lower.startswith(transicao):
                pontos_corte.append(seg_atual["start"])
                break

    pontos_corte.append(segs[-1]["end"])  # termina no fim

    # ── Passo 2: Agrupa em blocos respeitando duração min/max ─────────────
    blocos = []
    inicio_bloco = pontos_corte[0]
    textos_bloco = []

    for i in range(len(segs)):
        seg = segs[i]
        textos_bloco.append(seg["text"].strip())
        duracao_atual = seg["end"] - inicio_bloco

        # Verifica se este é um ponto de corte
        proximo_corte = seg["end"] in pontos_corte or (
            i + 1 < len(segs) and segs[i + 1]["start"] in pontos_corte
        )

        if duracao_atual >= duracao_min and (proximo_corte or duracao_atual >= duracao_max):
            # Salva o bloco
            blocos.append({
                "inicio":  inicio_bloco,
                "fim":     seg["end"],
                "textos":  list(textos_bloco),
                "duracao": duracao_atual,
            })
            # Começa novo bloco
            inicio_bloco = segs[i + 1]["start"] if i + 1 < len(segs) else seg["end"]
            textos_bloco = []

    # Adiciona último bloco se tiver conteúdo suficiente
    if textos_bloco and (segs[-1]["end"] - inicio_bloco) >= duracao_min / 2:
        blocos.append({
            "inicio":  inicio_bloco,
            "fim":     segs[-1]["end"],
            "textos":  textos_bloco,
            "duracao": segs[-1]["end"] - inicio_bloco,
        })

    # ── Passo 3: Gera título e score para cada bloco ──────────────────────
    segmentos = []
    for i, bloco in enumerate(blocos):
        texto_completo = " ".join(bloco["textos"])

        # Título: primeiras 8-12 palavras do bloco, limpo
        palavras = texto_completo.split()[:12]
        titulo = " ".join(palavras)
        titulo = re.sub(r'[^\w\s\'-]', '', titulo).strip()
        if len(titulo) > 60:
            titulo = titulo[:57] + "..."

        # Score baseado em heurísticas
        score = _calcular_score_offline(texto_completo, palavras_impacto)

        segmentos.append({
            "titulo":      titulo if titulo else f"Segmento {i + 1}",
            "inicio":      round(bloco["inicio"], 1),
            "fim":         round(bloco["fim"], 1),
            "score_viral": score,
            "resumo":      f"Segmento de {round(bloco['duracao'])}s detectado automaticamente",
        })

    print(f"✅ {len(segmentos)} segmentos detectados no modo offline.")
    return segmentos


def _calcular_score_offline(texto: str, palavras_impacto: list) -> int:
    """
    Calcula score de viralidade usando heurísticas simples.
    Sem IA — baseado em características do texto.
    """
    score = 5  # score base
    texto_lower = texto.lower()

    # Perguntas aumentam engajamento
    score += min(2, texto.count("?"))

    # Exclamações indicam emoção
    score += min(1, texto.count("!"))

    # Palavras de impacto
    for palavra in palavras_impacto:
        if palavra in texto_lower:
            score += 1
            break  # máximo +1 por palavras de impacto

    # Textos mais longos tendem a ter mais conteúdo
    if len(texto) > 500:
        score += 1

    # Limita entre 1 e 10
    return max(1, min(10, score))
