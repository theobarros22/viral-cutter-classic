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


def _obter_duracao_segundos(caminho: str) -> float:
    """Retorna a duração do arquivo em segundos usando ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", caminho
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
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


# ── Cache do modelo Whisper ──────────────────────────────────────────────
# O modelo pesa de 500MB (small) a 3GB (large). Sem cache, cada transcrição
# recarrega tudo do disco para a GPU/RAM — segundos a minutos desperdiçados.
# O cache guarda o modelo por (nome, dispositivo) e reutiliza na próxima.
_cache_modelo_whisper: dict = {}


def carregar_modelo_whisper(modelo_nome: str, dispositivo: str):
    """Carrega o modelo Whisper uma única vez e reutiliza nas próximas chamadas."""
    chave = f"{modelo_nome}|{dispositivo}"
    if chave in _cache_modelo_whisper:
        print(f"🎙️ Modelo Whisper '{modelo_nome}' já em memória (cache).")
        return _cache_modelo_whisper[chave]

    print(f"🎙️ Carregando modelo Whisper '{modelo_nome}'...")
    modelo = whisper.load_model(modelo_nome, device=dispositivo)
    _cache_modelo_whisper[chave] = modelo
    return modelo


def _transcrever_faster_whisper(caminho_video: str, idioma: str, modelo_nome: str, dispositivo: str):
    """
    Transcreve com faster-whisper (CTranslate2): ~4x mais rápido que o
    openai-whisper na mesma GPU, com word timestamps mais estáveis.

    Retorna dict no MESMO formato do openai-whisper (text/segments/words),
    ou None se a biblioteca não estiver instalada — o chamador então usa
    o caminho tradicional. Instalar com: pip install faster-whisper
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None

    chave = f"fw|{modelo_nome}|{dispositivo}"
    if chave in _cache_modelo_whisper:
        print(f"🎙️ Modelo faster-whisper '{modelo_nome}' já em memória (cache).")
        modelo = _cache_modelo_whisper[chave]
    else:
        print(f"🚀 Carregando faster-whisper '{modelo_nome}' ({dispositivo})...")
        compute = "float16" if dispositivo == "cuda" else "int8"
        try:
            modelo = WhisperModel(modelo_nome, device=dispositivo, compute_type=compute)
        except Exception as e:
            print(f"⚠️ faster-whisper falhou ao carregar ({e}). Usando openai-whisper.")
            return None
        _cache_modelo_whisper[chave] = modelo

    # Extrai o áudio (mesmo WAV 16kHz mono do caminho tradicional)
    pasta_temp = tempfile.gettempdir()
    wav_temp = os.path.join(pasta_temp, "_whisper_audio_temp.wav")
    alvo = wav_temp if _extrair_audio_wav(caminho_video, wav_temp) else caminho_video

    try:
        print("🎙️ Transcrevendo com faster-whisper... ")
        segmentos_fw, info = modelo.transcribe(
            alvo, language=idioma, word_timestamps=True, vad_filter=True,
        )

        # Converte o gerador do faster-whisper para o formato do openai-whisper
        segments = []
        texto_completo = ""
        for s in segmentos_fw:
            words = [
                {"word": w.word, "start": float(w.start), "end": float(w.end)}
                for w in (s.words or [])
            ]
            segments.append({
                "start": float(s.start),
                "end": float(s.end),
                "text": s.text,
                "words": words,
            })
            texto_completo += s.text
        print(f"✅ Transcrição concluída! {len(segments)} segmentos encontrados.")
        return {"text": texto_completo, "segments": segments, "language": idioma}
    except Exception as e:
        print(f"⚠️ Erro no faster-whisper ({e}). Usando openai-whisper.")
        return None
    finally:
        if os.path.exists(wav_temp):
            try:
                os.remove(wav_temp)
            except OSError:
                pass


def transcrever_video(caminho_video: str, idioma: str = "pt", modelo_nome: str = "small") -> dict:
    """
    Transcreve o áudio do vídeo usando Whisper na GPU se disponível.

    Preferência: faster-whisper (4x mais rápido, sem precisar de chunks —
    ele processa áudio longo em streaming). Fallback: openai-whisper com
    chunks de 20 minutos.
    """
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"

    if dispositivo == "cuda":
        nome_gpu = torch.cuda.get_device_name(0)
        print(f"⚡ GPU detectada: {nome_gpu} — usando aceleração!")
    else:
        print("💻 GPU não disponível — usando CPU (mais lento)")

    # ── Caminho rápido: faster-whisper (se instalado) ────────────────────
    resultado_fw = _transcrever_faster_whisper(caminho_video, idioma, modelo_nome, dispositivo)
    if resultado_fw is not None:
        return resultado_fw

    # ── Caminho tradicional: openai-whisper ──────────────────────────────
    modelo = carregar_modelo_whisper(modelo_nome, dispositivo)

    # Descobre a duração total do vídeo
    duracao_total = _obter_duracao_segundos(caminho_video)
    print(f"📏 Duração do vídeo: {duracao_total:.0f}s ({duracao_total/60:.1f} min)")

    CHUNK_SEGUNDOS = 1200  # 20 minutos por chunk

    if duracao_total <= CHUNK_SEGUNDOS:
        return _transcrever_direto(modelo, caminho_video, idioma, dispositivo)
    else:
        return _transcrever_em_chunks(modelo, caminho_video, idioma, dispositivo,
                                       duracao_total, CHUNK_SEGUNDOS)


def _transcrever_direto(modelo, caminho_video: str, idioma: str, dispositivo: str) -> dict:
    """Extrai áudio para WAV temporário e transcreve de uma vez."""
    pasta_temp = tempfile.gettempdir()
    wav_temp = os.path.join(pasta_temp, "_whisper_audio_temp.wav")

    try:
        print("🔊 Extraindo áudio do vídeo...")
        if not _extrair_audio_wav(caminho_video, wav_temp):
            print("⚠️ Falha ao extrair áudio, tentando direto no vídeo...")
            resultado = modelo.transcribe(
                caminho_video, language=idioma, verbose=False,
                fp16=(dispositivo == "cuda"),
                word_timestamps=True
            )
            return resultado

        print("🎙️ Transcrevendo áudio... (isso pode demorar alguns minutos)")
        resultado = modelo.transcribe(
            wav_temp, language=idioma, verbose=False,
            fp16=(dispositivo == "cuda"),
            word_timestamps=True
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

        wav_chunk = os.path.join(pasta_temp, f"_whisper_chunk_{i}.wav")
        print(f"   🔊 Chunk {i+1}/{n_chunks}: {inicio/60:.1f}min → {min((inicio+chunk_seg)/60, duracao_total/60):.1f}min")

        try:
            if not _extrair_audio_wav(caminho_video, wav_chunk, inicio_real, duracao):
                print(f"   ⚠️ Falha ao extrair chunk {i+1}, pulando...")
                continue

            resultado_chunk = modelo.transcribe(
                wav_chunk, language=idioma, verbose=False,
                fp16=(dispositivo == "cuda"),
                word_timestamps=True
            )

            offset = inicio_real
            for seg in resultado_chunk["segments"]:
                seg_corrigido = dict(seg)
                seg_corrigido["start"] += offset
                seg_corrigido["end"]   += offset

                # Corrige timestamps das palavras também
                if "words" in seg_corrigido and seg_corrigido["words"]:
                    seg_corrigido["words"] = [
                        {**w, "start": w["start"] + offset, "end": w["end"] + offset}
                        for w in seg_corrigido["words"]
                    ]

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
        segmentos = _segmentar_offline(transcricao, duracao_min, duracao_max)
    else:
        try:
            segmentos = _segmentar_com_ia(transcricao, duracao_min, duracao_max, nicho)
        except Exception as e:
            msg = str(e).lower()
            # Falta de créditos → cai pro offline (já existia).
            if "credit" in msg or "balance" in msg or "billing" in msg:
                print("⚠️ Créditos da API insuficientes. Usando modo offline automaticamente...")
                segmentos = _segmentar_offline(transcricao, duracao_min, duracao_max)
            # Chave ausente/ inválida ou sem autenticação → em vez de derrubar
            # a análise com um traceback críptico, degrada pro offline e avisa.
            elif any(t in msg for t in (
                "authentication", "api_key", "api key", "x-api-key",
                "auth_token", "credentials", "unauthorized", "401",
                "could not resolve authentication",
            )):
                print("⚠️ Chave da API Anthropic ausente ou inválida. "
                      "Usando modo offline automaticamente. "
                      "Para usar a análise com IA, configure ANTHROPIC_API_KEY "
                      "e reabra o programa (ou marque 'Modo offline' para não ver este aviso).")
                segmentos = _segmentar_offline(transcricao, duracao_min, duracao_max)
            else:
                raise

    # Ajuste de score por nicho — roda em ambos os modos
    if segmentos and nicho and nicho != "geral":
        print(f"\n🎯 Ajustando scores para nicho: {nicho.upper()}...")
        segmentos = ajustar_score_por_nicho(segmentos, nicho)

    return segmentos


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
        "crime":     "revelações chocantes, confissões, viradas de investigação, momentos de tensão máxima",
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
- HOOK: para cada clipe, identifique a frase de MAIOR impacto dentro dele
  (a mais chocante, curiosa ou emocionante — aquela que faria alguém parar de
  rolar o feed). Informe hook_inicio e hook_fim em timestamps ABSOLUTOS da
  transcrição, com duração entre 1.5 e 3.5 segundos, sempre DENTRO do clipe.
  Se a frase mais forte já está nos primeiros 5 segundos do clipe, use null
  nos dois campos (o clipe já abre forte, não precisa de cold open).
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
    "resumo": "Por que este trecho é viral: motivo curto",
    "hook_inicio": 45.2,
    "hook_fim": 47.8
  }}
]"""

    print("🤖 Analisando conteúdo com IA...")
    cliente = anthropic.Anthropic()
    resposta = cliente.messages.create(
        model="claude-opus-4-5",
        # 2000 tokens truncava o JSON em vídeos longos (muitos segmentos),
        # derrubando o json.loads com erro confuso. 8000 cobre com folga.
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )

    texto_resposta = resposta.content[0].text.strip()
    if texto_resposta.startswith("```"):
        linhas = texto_resposta.split("\n")
        texto_resposta = "\n".join(linhas[1:-1])

    try:
        segmentos = json.loads(texto_resposta)
    except json.JSONDecodeError:
        # Resposta truncada ou com texto extra: salva os objetos completos
        # que existirem dentro do array em vez de perder a análise inteira.
        segmentos = _salvar_json_parcial(texto_resposta)
        if segmentos is None:
            raise RuntimeError(
                "A IA retornou um JSON inválido/incompleto. "
                "Tente novamente ou use o modo offline."
            )
        print(f"⚠️ JSON incompleto da IA — {len(segmentos)} segmentos recuperados.")
    print(f"✅ IA identificou {len(segmentos)} segmentos virais.")
    return segmentos


def _salvar_json_parcial(texto: str):
    """
    Recupera os objetos completos de um array JSON truncado.
    Retorna lista de dicts ou None se nada aproveitável.
    """
    inicio = texto.find("[")
    if inicio == -1:
        return None
    corpo = texto[inicio:]
    # Corta no último fechamento de objeto e fecha o array manualmente
    ultimo = corpo.rfind("}")
    if ultimo == -1:
        return None
    candidato = corpo[: ultimo + 1].rstrip().rstrip(",") + "]"
    try:
        dados = json.loads(candidato)
        return dados if isinstance(dados, list) and dados else None
    except json.JSONDecodeError:
        return None


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


# ──────────────────────────────────────────────────────────────────────────────
# SCORE POR NICHO — pós-processamento aplicado em ambos os modos (IA e offline)
# ──────────────────────────────────────────────────────────────────────────────

_NICHO_CONFIG = {
    "podcast": {
        "descricao": "Podcast / Entrevista",
        # Palavras que adicionam +1 ao score (máx. +2 total por categoria)
        "palavras_alta_viralidade": [
            "nunca", "sempre", "impossível", "discordo", "mentira", "verdade",
            "confessou", "revelou", "segredo", "polêmico", "nunca contei",
            "primeira vez", "surpreendente", "chocante", "absurdo",
            "contraditório", "exatamente o oposto", "curiosamente",
        ],
        "palavras_narrativa_pessoal": [
            "quando eu", "na minha vida", "minha história", "passei por",
            "aprendi que", "mudou minha", "transformou", "experiência",
            "aconteceu comigo", "lembro quando",
        ],
        "palavras_engajamento": [
            "o que você acha", "concorda", "discorda", "pergunta",
            "deixa eu te perguntar", "você sabia", "imagina",
        ],
        # Penaliza conteúdo genérico e sem opinião
        "palavras_penalizar": [
            "bom dia", "boa tarde", "bem-vindo", "hoje vamos falar",
            "canal", "inscreva-se", "like", "comentem",
        ],
        # Pesos: quanto cada sinal vale no ajuste final (-2 a +2)
        "peso_perguntas": 1.2,
        "peso_exclamacoes": 0.8,
        "peso_duracao_ideal": (45, 90),   # faixa de duração considerada ideal (s)
        "bonus_duracao_ideal": 1,
    },
    "casamento": {
        "descricao": "Casamento / Cerimônia",
        "palavras_alta_viralidade": [
            "te amo", "amor da minha vida", "para sempre", "prometo",
            "emocionante", "lágrimas", "choro", "surpresa", "inacreditável",
            "lindo", "linda", "maravilhoso", "feliz", "especial",
            "inesquecível", "perfeito", "momento único",
        ],
        "palavras_narrativa_pessoal": [
            "quando te vi", "nossa história", "desde quando", "sempre soube",
            "meu coração", "mudou tudo", "nunca imaginei",
        ],
        "palavras_engajamento": [
            "chora", "que lindo", "que emoção", "nossa", "gente",
        ],
        "palavras_penalizar": [
            "orçamento", "fornecedor", "pacote", "buffet", "contrato",
            "preço", "valor", "parcelado",
        ],
        "peso_perguntas": 0.5,
        "peso_exclamacoes": 1.5,
        "peso_duracao_ideal": (30, 75),
        "bonus_duracao_ideal": 1,
    },
    "esporte": {
        "descricao": "Esporte / Competição",
        "palavras_alta_viralidade": [
            "gol", "impossível", "inacreditável", "recorde", "nunca visto",
            "campeão", "vitória", "derrota", "decisivo", "final",
            "virada", "empate", "pênalti", "expulsão", "lesão",
            "melhor do mundo", "história", "lendário",
        ],
        "palavras_narrativa_pessoal": [
            "jogada do", "momento que", "torcida", "estádio", "emoção",
        ],
        "palavras_engajamento": [
            "que jogada", "olha isso", "não acredito", "incrível",
        ],
        "palavras_penalizar": [
            "patrocinador", "contrato", "rescisão", "salário",
        ],
        "peso_perguntas": 0.7,
        "peso_exclamacoes": 1.8,
        "peso_duracao_ideal": (20, 60),
        "bonus_duracao_ideal": 1,
    },
    "crime": {
        "descricao": "Crime / Investigação",
        "palavras_alta_viralidade": [
            "confissão", "assassinato", "suspeito", "culpado", "inocente",
            "revelação", "prova", "evidência", "mistério", "chocante",
            "nunca revelado", "segredo", "documentos", "testemunha",
            "investigação", "descoberta",
        ],
        "palavras_narrativa_pessoal": [
            "crime aconteceu", "quando encontraram", "na madrugada",
            "ninguém sabia", "anos depois", "descobriram que",
        ],
        "palavras_engajamento": [
            "você vai se chocar", "parece mentira", "inacreditável",
            "impossível acreditar",
        ],
        "palavras_penalizar": [],
        "peso_perguntas": 1.5,
        "peso_exclamacoes": 1.0,
        "peso_duracao_ideal": (45, 120),
        "bonus_duracao_ideal": 1,
    },
    "educacao": {
        "descricao": "Educação / Conteúdo Didático",
        "palavras_alta_viralidade": [
            "você não sabia", "erro comum", "a maioria erra", "dica",
            "segredo", "truque", "hack", "pesquisa mostra", "estudos",
            "estatística", "surpreendente", "na prática", "resultado",
            "mudou minha", "funciona assim", "por que isso acontece",
        ],
        "palavras_narrativa_pessoal": [
            "aprendi que", "descobri que", "testei", "funcionou",
            "na prática", "exemplo real",
        ],
        "palavras_engajamento": [
            "você sabia que", "imagine", "pensa comigo",
            "como assim", "por quê",
        ],
        "palavras_penalizar": [
            "introdução", "capítulo", "aula", "módulo", "assista até o final",
        ],
        "peso_perguntas": 1.8,
        "peso_exclamacoes": 0.7,
        "peso_duracao_ideal": (40, 90),
        "bonus_duracao_ideal": 1,
    },
    "geral": {
        "descricao": "Conteúdo Geral",
        "palavras_alta_viralidade": [
            "incrível", "impossível", "nunca", "sempre", "segredo",
            "revelação", "surpreendente", "chocante", "absurdo",
        ],
        "palavras_narrativa_pessoal": [
            "minha história", "aconteceu comigo", "aprendi",
        ],
        "palavras_engajamento": [
            "você sabia", "imagina", "pensa",
        ],
        "palavras_penalizar": [],
        "peso_perguntas": 1.0,
        "peso_exclamacoes": 1.0,
        "peso_duracao_ideal": (30, 90),
        "bonus_duracao_ideal": 0,
    },
}


def ajustar_score_por_nicho(segmentos: list, nicho: str) -> list:
    """
    Pós-processa os scores de viralidade aplicando pesos específicos do nicho.

    Funciona em cima de qualquer score — seja gerado pela IA (Claude) ou offline.
    Não substitui: apenas calibra o score com sinais que o modelo geral pode ignorar.

    Regras:
    - Máximo de ajuste: ±2 pontos
    - Score final sempre entre 1 e 10
    - Registra o ajuste em 'score_ajuste' para debug
    """
    cfg = _NICHO_CONFIG.get(nicho, _NICHO_CONFIG["geral"])

    ajustados = []
    for seg in segmentos:
        texto = (seg.get("resumo", "") + " " + seg.get("titulo", "")).lower()
        score_original = seg.get("score_viral", 5)
        ajuste = 0.0

        # ── Palavras de alta viralidade para o nicho ──────────────────────
        hits_virais = sum(1 for p in cfg["palavras_alta_viralidade"] if p in texto)
        if hits_virais >= 3:
            ajuste += 1.0
        elif hits_virais >= 1:
            ajuste += 0.5

        # ── Narrativa pessoal / história ──────────────────────────────────
        hits_narrativa = sum(1 for p in cfg["palavras_narrativa_pessoal"] if p in texto)
        if hits_narrativa >= 2:
            ajuste += 0.5
        elif hits_narrativa >= 1:
            ajuste += 0.25

        # ── Palavras de engajamento ───────────────────────────────────────
        hits_eng = sum(1 for p in cfg["palavras_engajamento"] if p in texto)
        if hits_eng >= 1:
            ajuste += 0.25

        # ── Penaliza conteúdo genérico ────────────────────────────────────
        hits_penal = sum(1 for p in cfg["palavras_penalizar"] if p in texto)
        if hits_penal >= 2:
            ajuste -= 1.0
        elif hits_penal >= 1:
            ajuste -= 0.5

        # ── Duração ideal para o nicho ────────────────────────────────────
        duracao = seg.get("duracao") or (seg.get("fim", 0) - seg.get("inicio", 0))
        dur_min, dur_max = cfg["peso_duracao_ideal"]
        if dur_min <= duracao <= dur_max:
            ajuste += cfg["bonus_duracao_ideal"]

        # ── Aplica pesos de perguntas e exclamações no título/resumo ─────
        n_perguntas = texto.count("?")
        n_exclamacoes = texto.count("!")
        ajuste += min(0.5, n_perguntas * cfg["peso_perguntas"] * 0.2)
        ajuste += min(0.5, n_exclamacoes * cfg["peso_exclamacoes"] * 0.15)

        # ── Limita o ajuste total a ±2 e o score final a [1, 10] ─────────
        ajuste = max(-2.0, min(2.0, ajuste))
        score_novo = round(max(1, min(10, score_original + ajuste)))

        copia = dict(seg)
        copia["score_viral"] = score_novo
        copia["score_ajuste"] = round(ajuste, 2)
        copia["nicho"] = nicho
        ajustados.append(copia)

        if ajuste != 0:
            sinal = "+" if ajuste > 0 else ""
            print(f"   Score [{seg.get('titulo', '?')[:30]}]: "
                  f"{score_original} → {score_novo} ({sinal}{ajuste:.1f} | nicho={nicho})")

    return ajustados
