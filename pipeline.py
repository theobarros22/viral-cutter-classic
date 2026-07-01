"""
pipeline.py
-----------
Orquestra o pipeline completo da v2:

1. Detecta pessoas → extrai previews
2. Usuário escolhe quem priorizar
3. Transcreve com Whisper
4. IA identifica segmentos (onde começa/termina cada assunto)
5. Detecta quem fala em cada frame
6. Corta os clipes
7. Aplica enquadramento 9:16 seguindo quem fala
8. Exporta organizados por podcast
"""

import os
import re
import json
import shutil
import subprocess
import threading
from runtime import pasta_dados


# Cache entre etapas
_cache = {}

# ── Cancelamento cooperativo ───────────────────────────────────────────────────
_cancel_event = threading.Event()

def solicitar_cancelamento():
    """Sinaliza para o pipeline interromper após o clipe atual."""
    _cancel_event.set()

def limpar_cancelamento():
    """Reseta o flag de cancelamento antes de iniciar novo processamento."""
    _cancel_event.clear()

def _checar_cancelamento():
    """Lança CancelledError se cancelamento foi solicitado."""
    if _cancel_event.is_set():
        raise RuntimeError("Processamento cancelado pelo usuário.")


# ── Constantes ─────────────────────────────────────────────────────────────────
MAX_EXPORT_RETRIES = 1
_FFPROBE_TIMEOUT = 30  # segundos


# ── Validação FFprobe ──────────────────────────────────────────────────────────

def _localizar_ffprobe() -> str:
    """Retorna o caminho do ffprobe ou 'ffprobe' para usar o PATH."""
    import shutil as _sh
    for cand in [
        _sh.which("ffprobe"),
        r"D:\CORTE VIRAL\files\tools\ffprobe.exe",
        r"D:\CORTE VIRAL\tools\ffprobe.exe",
    ]:
        if cand and os.path.exists(cand):
            return cand
    return "ffprobe"


def validar_midia_ffprobe(
    caminho_arquivo: str,
    duracao_esperada: float = None,
    audio_policy: str = "optional",
    tolerancia_duracao: float = None,
    timeout: int = _FFPROBE_TIMEOUT,
) -> dict:
    """
    Valida um arquivo de mídia com FFprobe.

    Parâmetros:
        caminho_arquivo   : caminho absoluto do arquivo a validar.
        duracao_esperada  : duração planejada em segundos (None = não verifica).
        audio_policy      : "required" | "optional" | "none"
        tolerancia_duracao: segundos de tolerância; None = max(0.5, esperada*0.02).
        timeout           : timeout em segundos para o processo ffprobe.

    Retorno:
        dict com chaves: valid, path, video_present, audio_present,
        duration, expected_duration, duration_difference, width, height,
        video_codec, audio_codec, audio_policy, errors, warnings.
    """
    result = {
        "valid": False,
        "path": caminho_arquivo,
        "video_present": False,
        "audio_present": False,
        "duration": None,
        "expected_duration": duracao_esperada,
        "duration_difference": None,
        "width": None,
        "height": None,
        "video_codec": None,
        "audio_codec": None,
        "audio_policy": audio_policy,
        "errors": [],
        "warnings": [],
    }

    # ── 1. Verificações de arquivo ─────────────────────────────────────────────
    if not caminho_arquivo or not os.path.exists(caminho_arquivo):
        result["errors"].append("Arquivo não encontrado.")
        return result

    if os.path.getsize(caminho_arquivo) == 0:
        result["errors"].append("Arquivo com tamanho zero.")
        return result

    # ── 2. Executar FFprobe ────────────────────────────────────────────────────
    ffprobe = _localizar_ffprobe()
    cmd = [
        ffprobe,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        caminho_arquivo,
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        result["errors"].append("FFprobe não encontrado no sistema.")
        return result
    except subprocess.TimeoutExpired:
        result["errors"].append(f"FFprobe excedeu o timeout de {timeout}s.")
        return result
    except Exception as e:
        result["errors"].append(f"Erro ao executar FFprobe: {e}")
        return result

    if proc.returncode != 0:
        detalhe = (proc.stderr or "").strip()[:300]
        result["errors"].append(f"FFprobe retornou código {proc.returncode}. {detalhe}")
        return result

    # ── 3. Parsear JSON ────────────────────────────────────────────────────────
    try:
        dados = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        result["errors"].append(f"Resposta do FFprobe não é JSON válido: {e}")
        return result

    streams = dados.get("streams", [])
    fmt = dados.get("format", {})

    # ── 4. Streams de vídeo e áudio ────────────────────────────────────────────
    stream_video = next((s for s in streams if s.get("codec_type") == "video"), None)
    stream_audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if stream_video:
        result["video_present"] = True
        result["video_codec"] = stream_video.get("codec_name")
        result["width"]  = stream_video.get("width", 0)
        result["height"] = stream_video.get("height", 0)

        if not result["width"] or result["width"] <= 0:
            result["errors"].append("Largura do vídeo inválida.")
        if not result["height"] or result["height"] <= 0:
            result["errors"].append("Altura do vídeo inválida.")
    else:
        result["errors"].append("Nenhum stream de vídeo encontrado.")

    if stream_audio:
        result["audio_present"] = True
        result["audio_codec"] = stream_audio.get("codec_name")

    # ── 5. Política de áudio ───────────────────────────────────────────────────
    if audio_policy == "required" and not result["audio_present"]:
        result["errors"].append("Áudio obrigatório ausente (audio_policy=required).")
    elif audio_policy == "optional" and not result["audio_present"]:
        result["warnings"].append("Clipe sem trilha de áudio (aceito — audio_policy=optional).")
    # "none" → sem verificação de áudio

    # ── 6. Duração ─────────────────────────────────────────────────────────────
    # Tenta obter duração: 1) stream de vídeo → 2) container (format)
    # NOTA: o ternário deve ser avaliado completamente antes do `or`, por isso
    # usamos uma variável intermediária em vez de encadear tudo numa expressão.
    _stream_dur = stream_video.get("duration") if stream_video else None
    dur_raw = _stream_dur or fmt.get("duration")
    if dur_raw:
        try:
            result["duration"] = float(dur_raw)
        except (ValueError, TypeError):
            pass

    if not result["duration"] or result["duration"] <= 0:
        result["errors"].append("Duração inválida ou zero.")
    elif duracao_esperada is not None and duracao_esperada > 0:
        tol = tolerancia_duracao if tolerancia_duracao is not None else max(0.5, duracao_esperada * 0.02)
        diff = abs(result["duration"] - duracao_esperada)
        result["duration_difference"] = round(diff, 3)
        if diff > tol:
            result["errors"].append(
                f"Duração real ({result['duration']:.2f}s) difere da esperada "
                f"({duracao_esperada:.2f}s) em {diff:.2f}s (tolerância: {tol:.2f}s)."
            )

    # ── 7. Resultado final ─────────────────────────────────────────────────────
    result["valid"] = len(result["errors"]) == 0
    return result


def _renomear_invalido(caminho: str) -> str:
    """Renomeia arquivo para .invalid.mp4 para não poluir a pasta de saída."""
    novo = caminho.replace(".mp4", ".invalid.mp4")
    try:
        if os.path.exists(caminho):
            os.replace(caminho, novo)
        return novo
    except OSError:
        return caminho


def _exportar_com_validacao(
    fn_exportar,
    caminho_saida: str,
    duracao_esperada: float,
    audio_policy: str,
    log_fn,
    prefixo_log: str = "",
) -> dict:
    """
    Executa fn_exportar(), valida o resultado com FFprobe e faz 1 retry se inválido.
    Respeita cancelamento cooperativo antes do retry.

    Retorna o dict de validação. 'valid' indica sucesso.
    """
    for tentativa in range(1, MAX_EXPORT_RETRIES + 2):  # até 2 tentativas
        _checar_cancelamento()

        log_fn(f"{prefixo_log} Exportando (tentativa {tentativa}/{MAX_EXPORT_RETRIES + 1})...")
        try:
            fn_exportar()
        except RuntimeError as e:
            # Cancelamento ou erro de exportação
            raise

        log_fn(f"{prefixo_log} Validando arquivo exportado...")
        val = validar_midia_ffprobe(
            caminho_saida,
            duracao_esperada=duracao_esperada,
            audio_policy=audio_policy,
        )

        if val["valid"]:
            if val["warnings"]:
                for w in val["warnings"]:
                    log_fn(f"{prefixo_log} ⚠️ {w}")
            log_fn(f"{prefixo_log} ✅ Clipe validado com sucesso. "
                   f"({val['duration']:.1f}s | {val['width']}x{val['height']} | "
                   f"codec={val['video_codec']})")
            return val

        # Falha
        for err in val["errors"]:
            log_fn(f"{prefixo_log} ❌ Validação: {err}")

        _renomear_invalido(caminho_saida)

        if tentativa > MAX_EXPORT_RETRIES:
            log_fn(f"{prefixo_log} ❌ Falha definitiva após {MAX_EXPORT_RETRIES + 1} tentativa(s).")
            return val

        # Retry
        _checar_cancelamento()
        log_fn(f"{prefixo_log} 🔄 Retry {tentativa}/{MAX_EXPORT_RETRIES}...")

    return val  # nunca alcançado, mas satisfaz linter


def etapa1_detectar_pessoas(
    caminho_video: str,
    pasta_temp: str = None,
    progresso_callback=None
) -> list:
    """
    ETAPA 1: Detecta as pessoas no vídeo e retorna previews.
    Rápido — analisa 30 frames distribuídos nos primeiros 5 minutos.
    """
    def log(msg):
        print(msg)
        if progresso_callback:
            progresso_callback(msg)

    if not caminho_video or not os.path.isfile(caminho_video):
        raise FileNotFoundError("O vídeo selecionado não existe ou não está acessível.")

    # Imports pesados somente quando esta etapa é usada. Isso reduz bastante
    # o tempo entre dar duplo clique e a interface aparecer.
    from rostos import detectar_pessoas_no_video, salvar_previews

    if pasta_temp is None:
        pasta_temp = os.path.join(pasta_dados(), "previews")
    if os.path.isdir(pasta_temp):
        for nome in os.listdir(pasta_temp):
            if nome.lower().endswith(".jpg"):
                try:
                    os.remove(os.path.join(pasta_temp, nome))
                except OSError:
                    pass

    log("🔍 Detectando pessoas no vídeo...")
    # 30 amostras (era 10) — com vídeo de várias câmeras, 10 frames
    # podiam cair todos no mesmo ângulo e deixar pessoas sem detectar
    pessoas = detectar_pessoas_no_video(
        caminho_video,
        max_amostras=30,
        limite_minutos=5.0,
    )

    if not pessoas:
        log("⚠️ Nenhuma pessoa detectada. Usando enquadramento central.")
        _cache["pessoas"] = []
        return []

    pessoas = salvar_previews(pessoas, pasta_temp)
    _cache["pessoas"] = pessoas
    _cache["caminho_video"] = caminho_video

    log(f"✅ {len(pessoas)} pessoa(s) encontrada(s). Escolha quem priorizar.")
    return pessoas


def etapa2_analisar(
    caminho_video: str,
    idioma: str = "pt",
    modelo_whisper: str = "small",
    nicho: str = "podcast",
    duracao_min: int = 30,
    duracao_max: int = 90,
    modo_offline: bool = False,
    progresso_callback=None
) -> list:
    """
    ETAPA 2: Transcreve e identifica segmentos com IA.
    """
    def log(msg):
        print(msg)
        if progresso_callback:
            progresso_callback(msg)

    if not caminho_video or not os.path.isfile(caminho_video):
        raise FileNotFoundError("O vídeo selecionado não existe ou não está acessível.")
    if duracao_min <= 0 or duracao_max < duracao_min:
        raise ValueError("A duração máxima deve ser maior ou igual à duração mínima.")

    from analise import transcrever_video, segmentar_por_assunto

    log(f"📝 Transcrevendo com Whisper '{modelo_whisper}'...")
    transcricao = transcrever_video(caminho_video, idioma, modelo_whisper)
    _cache["transcricao"] = transcricao
    _cache["caminho_video"] = caminho_video

    log(f"🤖 Identificando segmentos (nicho: {nicho})...")
    segmentos = segmentar_por_assunto(transcricao, duracao_min, duracao_max, nicho, modo_offline=modo_offline)

    _cache["segmentos"] = segmentos
    log(f"✅ {len(segmentos)} segmentos identificados!")
    return segmentos


def _etapa3_processar_legado(
    caminho_video: str,
    pasta_saida_base: str,
    segmentos: list,
    pessoas_priorizadas_ids: list = None,
    qualidade: str = "1080p",
    progresso_callback=None
) -> list:
    """
    ETAPA 3: Detecta quem fala, corta e enquadra todos os clipes.

    Parâmetros:
        pessoas_priorizadas_ids: lista de IDs das pessoas escolhidas pelo usuário
                                 (se vazio, prioriza todas)
    """
    def log(msg):
        print(msg)
        if progresso_callback:
            progresso_callback(msg)

    if not caminho_video or not os.path.isfile(caminho_video):
        raise FileNotFoundError("O vídeo selecionado não existe ou não está acessível.")
    if not pasta_saida_base or not str(pasta_saida_base).strip():
        raise ValueError("Informe uma pasta de destino válida.")

    from cortes import cortar_clipe
    from enquadramento import aplicar_enquadramento
    from rostos import detectar_quem_fala_por_frame

    # Cria subpasta com nome do podcast
    nome_video = os.path.splitext(os.path.basename(caminho_video))[0]
    nome_pasta = sanitizar_nome(nome_video)
    pasta_saida = os.path.join(pasta_saida_base, nome_pasta)
    os.makedirs(pasta_saida, exist_ok=True)

    log(f"📁 Exportando para: {pasta_saida}")
    espaco_livre = shutil.disk_usage(pasta_saida).free
    if espaco_livre < 5 * 1024**3:
        raise OSError("Espaço livre insuficiente. Libere pelo menos 5 GB antes de processar.")

    segmentos = _validar_segmentos(segmentos)
    if not segmentos:
        log("⚠️ Nenhum segmento válido para processar.")
        return []

    total = len(segmentos)
    resultados = []

    for i, seg in enumerate(segmentos, 1):
        log(f"   ✂️  [{i}/{total}] {seg.get('titulo', 'Clipe')} ({seg['inicio']}s → {seg['fim']}s)")

        nome_arquivo = f"{i:02d}_{sanitizar_nome(seg.get('titulo', f'clipe_{i:02d}'))}.mp4"
        caminho_temp  = os.path.join(pasta_saida, f"_temp_{nome_arquivo}")
        caminho_final = os.path.join(pasta_saida, nome_arquivo)

        # Corta o clipe do vídeo original
        sucesso = cortar_clipe(caminho_video, seg["inicio"], seg["fim"], caminho_temp)
        if not sucesso:
            if os.path.exists(caminho_temp):
                os.remove(caminho_temp)
            log(f"   ⚠️ Erro ao cortar clipe {i}. Pulando...")
            continue

        # Analisa apenas o clipe selecionado. Antes esta etapa percorria o
        # podcast inteiro, mesmo quando poucos trechos seriam exportados.
        log(f"   🎤 [{i}/{total}] Detectando falante no clipe...")
        posicoes_clipe = detectar_quem_fala_por_frame(
            caminho_temp,
            _cache.get("pessoas", []),
            intervalo_frames=15,
        )

        if not posicoes_clipe:
            posicoes_clipe = [0.5] * 100

        if pessoas_priorizadas_ids and _cache.get("pessoas"):
            posicoes_clipe = _filtrar_por_pessoas_priorizadas(
                posicoes_clipe,
                _cache["pessoas"],
                pessoas_priorizadas_ids,
            )

        log(f"   🎬 [{i}/{total}] Enquadrando...")

        # Aplica enquadramento 9:16
        sucesso = aplicar_enquadramento(
            caminho_temp, caminho_final,
            posicoes_clipe,
            pessoas_priorizadas_ids,
            qualidade=qualidade
        )

        if os.path.exists(caminho_temp):
            os.remove(caminho_temp)

        if not sucesso:
            if os.path.exists(caminho_final):
                os.remove(caminho_final)
            log(f"   ⚠️ Erro no enquadramento do clipe {i}.")
            continue

        if os.path.exists(caminho_final):
            resultados.append({
                "titulo":      seg.get("titulo"),
                "arquivo":     caminho_final,
                "score_viral": seg.get("score_viral", 0),
                "resumo":      seg.get("resumo", ""),
                "duracao":     round(seg["fim"] - seg["inicio"], 1),
            })
            log(f"   ✅ Salvo: {nome_arquivo}")

    log(f"\n🎉 Concluído! {len(resultados)} clipes em: {pasta_saida}")
    return resultados


def _filtrar_por_pessoas_priorizadas(
    posicoes: list,
    pessoas: list,
    ids_priorizados: list
) -> list:
    """
    Ajusta as posições do falante para focar nas pessoas priorizadas.
    Se o falante detectado não está na lista de priorizados,
    mantém a câmera na última pessoa priorizada que falou.
    """
    # Mapa: faixa X → id da pessoa
    pessoas_por_lado = {p["id"]: p["posicao_x"] for p in pessoas}
    priorizadas_x = [pessoas_por_lado[id] for id in ids_priorizados if id in pessoas_por_lado]

    if not priorizadas_x:
        return posicoes

    resultado = list(posicoes)
    ultimo_priorizado = priorizadas_x[0]

    for i, pos_x in enumerate(posicoes):
        if pos_x is None:
            resultado[i] = ultimo_priorizado
            continue

        # Verifica se está próximo de uma pessoa priorizada
        mais_proximo = min(priorizadas_x, key=lambda px: abs(px - pos_x))
        distancia = abs(mais_proximo - pos_x)

        if distancia < 0.25:  # dentro de 25% da posição da pessoa priorizada
            ultimo_priorizado = mais_proximo
            resultado[i] = mais_proximo
        else:
            # Pessoa falando não está na lista de priorizados
            # Mantém câmera na última priorizada
            resultado[i] = ultimo_priorizado

    return resultado


def sanitizar_nome(texto: str) -> str:
    texto = str(texto or "")
    texto = re.sub(r'[<>:"/\\|?*]', '', texto)
    texto = texto.replace(' ', '_')
    return texto[:60] or "clipe"


def _validar_segmentos(segmentos: list) -> list:
    """Descarta cortes inválidos antes de iniciar o processamento pesado."""
    validos = []
    for seg in segmentos or []:
        try:
            inicio = max(0.0, float(seg["inicio"]))
            fim = float(seg["fim"])
        except (KeyError, TypeError, ValueError):
            continue
        if fim <= inicio:
            continue
        copia = dict(seg)
        copia["inicio"] = inicio
        copia["fim"] = fim
        validos.append(copia)
    return validos


def _fundir_intervalos(intervalos: list) -> list:
    """Une clipes sobrepostos para não analisar o mesmo frame duas vezes."""
    fundidos = []
    for inicio, fim in sorted(intervalos):
        if not fundidos or inicio > fundidos[-1][1]:
            fundidos.append([inicio, fim])
        else:
            fundidos[-1][1] = max(fundidos[-1][1], fim)
    return [tuple(item) for item in fundidos]


def _obter_fps(caminho_video: str) -> float:
    import subprocess, json
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "v:0", caminho_video
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0 or not resultado.stdout.strip():
        raise RuntimeError("FFprobe não conseguiu ler o vídeo.")
    dados = json.loads(resultado.stdout)
    stream = dados["streams"][0]
    fps_str = stream.get("r_frame_rate", "30/1")
    num, den = fps_str.split("/")
    den = int(den)
    return round(int(num) / den, 2) if den else 30.0


# Implementacao recuperavel. Esta definicao substitui a versao anterior acima.
def etapa3_processar(
    caminho_video: str,
    pasta_saida_base: str,
    segmentos: list,
    pessoas_priorizadas_ids: list = None,
    qualidade: str = "1080p",
    perfil: str = "equilibrado",
    retomar: bool = True,
    remover_pausas: bool = False,
    min_silencio_ms: int = 700,
    margem_silencio_ms: int = 120,
    progresso_callback=None
) -> list:
    """Corta e enquadra os clipes, salvando um checkpoint apos cada etapa."""
    import time
    import traceback
    from datetime import datetime
    from checkpoint import (
        caminho_checkpoint, carregar_checkpoint, criar_id_trabalho,
        novo_checkpoint, resultados_concluidos, salvar_checkpoint,
    )
    from cortes import cortar_clipe
    from enquadramento import aplicar_enquadramento
    from rostos import detectar_quem_fala_por_frame

    arquivo_log_trabalho = None

    def log(msg):
        print(msg)
        if arquivo_log_trabalho:
            with open(arquivo_log_trabalho, "a", encoding="utf-8") as arquivo:
                horario = datetime.now().astimezone().isoformat(timespec="seconds")
                arquivo.write(f"{horario} {msg}\n")
        if progresso_callback:
            progresso_callback(msg)

    def formatar_tempo(segundos):
        segundos = max(0, int(segundos))
        horas, resto = divmod(segundos, 3600)
        minutos, segundos = divmod(resto, 60)
        if horas:
            return f"{horas}h {minutos:02d}min"
        if minutos:
            return f"{minutos}min {segundos:02d}s"
        return f"{segundos}s"

    if not caminho_video or not os.path.isfile(caminho_video):
        raise FileNotFoundError("O video selecionado nao existe ou nao esta acessivel.")
    if not pasta_saida_base or not str(pasta_saida_base).strip():
        raise ValueError("Informe uma pasta de destino valida.")

    nome_video = os.path.splitext(os.path.basename(caminho_video))[0]
    pasta_saida = os.path.join(pasta_saida_base, sanitizar_nome(nome_video))
    os.makedirs(pasta_saida, exist_ok=True)
    log(f"Exportando para: {pasta_saida}")

    if shutil.disk_usage(pasta_saida).free < 5 * 1024**3:
        raise OSError("Espaco livre insuficiente. Libere pelo menos 5 GB.")

    id_trabalho = criar_id_trabalho(
        caminho_video, segmentos, qualidade, pessoas_priorizadas_ids, perfil,
        remover_pausas, min_silencio_ms, margem_silencio_ms,
    )
    arquivo_checkpoint = caminho_checkpoint(pasta_saida, id_trabalho)
    arquivo_log_trabalho = os.path.join(
        pasta_saida, f"viral_cutter_{id_trabalho}.log"
    )
    log("")
    log("=== Nova sessao de processamento ===")
    log(f"Video: {caminho_video}")
    log(f"Qualidade: {qualidade}")
    log(f"Perfil: {perfil}")
    checkpoint = carregar_checkpoint(arquivo_checkpoint) if retomar else None

    if checkpoint is not None and checkpoint.get("segmentos"):
        segmentos = _validar_segmentos(checkpoint["segmentos"])
        log("Analise anterior recuperada do checkpoint.")
    else:
        segmentos = _validar_segmentos(segmentos)

    if not segmentos:
        raise ValueError(
            "Nenhuma analise anterior foi encontrada. Execute TRANSCRIBIR & ANALISAR primeiro."
        )

    total = len(segmentos)
    if checkpoint is None:
        checkpoint = novo_checkpoint(
            id_trabalho, caminho_video, segmentos, qualidade,
            pessoas_priorizadas_ids, perfil
        )
        salvar_checkpoint(arquivo_checkpoint, checkpoint)

    concluidos = resultados_concluidos(checkpoint) if retomar else {}
    resultados_por_indice = dict(concluidos)
    inicio_sessao = time.monotonic()
    novos_concluidos = 0
    if concluidos:
        log(f"RETOMANDO: {len(concluidos)}/{total} clipe(s) ja concluidos.")
    log(f"Checkpoint: {arquivo_checkpoint}")
    log(f"Log persistente: {arquivo_log_trabalho}")
    log(f"Progresso inicial: {len(concluidos)}/{total} ({len(concluidos) / total * 100:.0f}%)")

    for i, seg in enumerate(segmentos, 1):
        if i in concluidos:
            log(f"   [{i}/{total}] Ja concluido. Pulando.")
            continue

        nome_arquivo = f"{i:02d}_{sanitizar_nome(seg.get('titulo', f'clipe_{i:02d}'))}.mp4"
        caminho_temp = os.path.join(pasta_saida, f"_temp_{nome_arquivo}")
        caminho_compacto = None
        caminho_final = os.path.join(pasta_saida, nome_arquivo)
        log(f"   [{i}/{total}] {seg.get('titulo', 'Clipe')}")

        checkpoint["status"] = "processando"
        checkpoint["clipes"][str(i)] = {
            "status": "processando",
            "etapa": "corte",
            "titulo": seg.get("titulo", f"Clipe {i}"),
            "inicio": seg["inicio"],
            "fim": seg["fim"],
            "arquivo": caminho_final,
        }
        salvar_checkpoint(arquivo_checkpoint, checkpoint)

        try:
            inicio_corte = time.monotonic()
            if not cortar_clipe(caminho_video, seg["inicio"], seg["fim"], caminho_temp):
                raise RuntimeError(f"Falha ao cortar o clipe {i}.")
            tempo_corte = time.monotonic() - inicio_corte

            if remover_pausas:
                caminho_compacto = os.path.join(pasta_saida, f"_compacto_{nome_arquivo}")
                log(f"   [{i}/{total}] Removendo pausas internas...")
                from cortes import remover_silencios
                resumo_silencio = remover_silencios(
                    caminho_temp,
                    caminho_compacto,
                    min_silencio_ms=min_silencio_ms,
                    margem_ms=margem_silencio_ms,
                )
                if resumo_silencio["alterado"]:
                    os.replace(caminho_compacto, caminho_temp)
                    log(
                        f"   [{i}/{total}] "
                        f"{resumo_silencio['removido_ms'] / 1000:.1f}s de pausas removidos."
                    )
                elif os.path.exists(caminho_compacto):
                    os.remove(caminho_compacto)

            checkpoint["clipes"][str(i)]["etapa"] = "deteccao_falante"
            salvar_checkpoint(arquivo_checkpoint, checkpoint)
            log(f"   [{i}/{total}] Detectando falante...")
            inicio_falante = time.monotonic()
            intervalo_falante = 30 if perfil == "rapido" else (8 if perfil == "qualidade" else 15)
            posicoes = detectar_quem_fala_por_frame(
                caminho_temp,
                _cache.get("pessoas", []),
                intervalo_frames=intervalo_falante,
                analisar_audio=(perfil != "rapido"),
            ) or [0.5] * 100
            tempo_falante = time.monotonic() - inicio_falante

            if pessoas_priorizadas_ids and _cache.get("pessoas"):
                posicoes = _filtrar_por_pessoas_priorizadas(
                    posicoes, _cache["pessoas"], pessoas_priorizadas_ids
                )

            checkpoint["clipes"][str(i)]["etapa"] = "enquadramento"
            salvar_checkpoint(arquivo_checkpoint, checkpoint)
            log(f"   [{i}/{total}] Enquadrando...")
            inicio_enquadramento = time.monotonic()
            sucesso = aplicar_enquadramento(
                caminho_temp, caminho_final, posicoes,
                pessoas_priorizadas_ids, qualidade=qualidade, perfil=perfil
            )
            tempo_enquadramento = time.monotonic() - inicio_enquadramento
            if not sucesso or not os.path.isfile(caminho_final):
                raise RuntimeError(f"Falha no enquadramento do clipe {i}.")

            # ── Validação FFprobe pós-enquadramento ───────────────────────
            checkpoint["clipes"][str(i)]["etapa"] = "validacao"
            salvar_checkpoint(arquivo_checkpoint, checkpoint)
            _dur_esperada = seg["fim"] - seg["inicio"]
            _val = validar_midia_ffprobe(
                caminho_final,
                duracao_esperada=_dur_esperada,
                audio_policy="optional",
            )
            if not _val["valid"]:
                for _err in _val["errors"]:
                    log(f"   [{i}/{total}] ⚠️ Validação: {_err}")
                _renomear_invalido(caminho_final)
                _checar_cancelamento()
                log(f"   [{i}/{total}] 🔄 Retry 1/{MAX_EXPORT_RETRIES} — re-enquadrando...")
                # caminho_temp ainda existe (finally só remove ao sair do bloco try)
                if not os.path.exists(caminho_temp):
                    if not cortar_clipe(caminho_video, seg["inicio"], seg["fim"], caminho_temp):
                        log(f"   [{i}/{total}] ❌ Retry: falha ao re-cortar clipe.")
                        checkpoint["clipes"][str(i)].update(
                            {"status": "erro", "erro": "validacao_falhou_apos_retry"}
                        )
                        salvar_checkpoint(arquivo_checkpoint, checkpoint)
                        continue
                _sucesso_retry = aplicar_enquadramento(
                    caminho_temp, caminho_final, posicoes,
                    pessoas_priorizadas_ids, qualidade=qualidade, perfil=perfil
                )
                if not _sucesso_retry or not os.path.isfile(caminho_final):
                    log(f"   [{i}/{total}] ❌ Retry: falha no enquadramento.")
                    checkpoint["clipes"][str(i)].update(
                        {"status": "erro", "erro": "enquadramento_retry_falhou"}
                    )
                    salvar_checkpoint(arquivo_checkpoint, checkpoint)
                    continue
                _val2 = validar_midia_ffprobe(
                    caminho_final,
                    duracao_esperada=_dur_esperada,
                    audio_policy="optional",
                )
                if not _val2["valid"]:
                    for _err in _val2["errors"]:
                        log(f"   [{i}/{total}] ❌ Retry validação: {_err}")
                    _renomear_invalido(caminho_final)
                    log(
                        f"   [{i}/{total}] ❌ Clipe {i} permanece inválido após "
                        f"{MAX_EXPORT_RETRIES + 1} tentativa(s). Pulando."
                    )
                    checkpoint["clipes"][str(i)].update(
                        {"status": "erro", "erro": "validacao_ffprobe_falhou"}
                    )
                    salvar_checkpoint(arquivo_checkpoint, checkpoint)
                    continue
                else:
                    log(f"   [{i}/{total}] ✅ Retry validado com sucesso.")
                    for _w in _val2["warnings"]:
                        log(f"   [{i}/{total}] ⚠️ {_w}")
            else:
                # Validação OK na primeira tentativa
                for _w in _val["warnings"]:
                    log(f"   [{i}/{total}] ⚠️ {_w}")
                log(
                    f"   [{i}/{total}] ✅ Validado: {_val['duration']:.1f}s | "
                    f"{_val['width']}x{_val['height']} | {_val['video_codec']}"
                )

            resultado = {
                "titulo": seg.get("titulo"),
                "arquivo": caminho_final,
                "score_viral": seg.get("score_viral", 0),
                "resumo": seg.get("resumo", ""),
                "duracao": round(seg["fim"] - seg["inicio"], 1),
                "tempos": {
                    "corte": round(tempo_corte, 1),
                    "falante": round(tempo_falante, 1),
                    "enquadramento": round(tempo_enquadramento, 1),
                },
            }
            resultados_por_indice[i] = resultado
            novos_concluidos += 1
            concluidos_total = len(resultados_por_indice)
            percentual = concluidos_total / total * 100
            decorrido = time.monotonic() - inicio_sessao
            media_por_clipe = decorrido / novos_concluidos
            estimativa = media_por_clipe * (total - concluidos_total)
            checkpoint["clipes"][str(i)] = {
                "status": "concluido",
                "etapa": "concluido",
                "resultado": resultado,
            }
            checkpoint["progresso_percentual"] = round(percentual, 1)
            checkpoint["estimativa_segundos"] = round(estimativa)
            checkpoint["ultimo_erro"] = None
            salvar_checkpoint(arquivo_checkpoint, checkpoint)
            log(f"   Salvo: {nome_arquivo}")
            log(
                f"   Tempos: corte {formatar_tempo(tempo_corte)} | "
                f"falante {formatar_tempo(tempo_falante)} | "
                f"enquadramento {formatar_tempo(tempo_enquadramento)}"
            )
            log(
                f"   Progresso: {concluidos_total}/{total} ({percentual:.0f}%)"
                f" | estimativa restante: {formatar_tempo(estimativa)}"
            )
        except Exception as erro:
            checkpoint["status"] = "interrompido"
            checkpoint["ultimo_erro"] = {
                "clipe": i,
                "mensagem": str(erro),
                "traceback": traceback.format_exc(),
            }
            checkpoint["clipes"][str(i)].update(
                {"status": "erro", "erro": str(erro)}
            )
            salvar_checkpoint(arquivo_checkpoint, checkpoint)
            if os.path.exists(caminho_final):
                os.remove(caminho_final)
            log(f"   Processo interrompido no clipe {i}: {erro}")
            log("   Progresso salvo. Execute novamente para continuar.")
            log(traceback.format_exc())
            raise
        finally:
            if os.path.exists(caminho_temp):
                os.remove(caminho_temp)
            if caminho_compacto and os.path.exists(caminho_compacto):
                os.remove(caminho_compacto)

    resultados = [
        resultados_por_indice[indice] for indice in sorted(resultados_por_indice)
    ]
    checkpoint["status"] = "concluido"
    checkpoint["progresso_percentual"] = 100.0
    checkpoint["estimativa_segundos"] = 0
    checkpoint["ultimo_erro"] = None
    salvar_checkpoint(arquivo_checkpoint, checkpoint)
    log(f"Concluido! {len(resultados)} clipes em: {pasta_saida}")
    return resultados


# ---------------------------------------------------------------------------
# ETAPA 4 — EFEITOS VIRAIS (legendas ASS + zoom dinâmico + SFX)
# ---------------------------------------------------------------------------

def etapa4_efeitos_virais(
    resultados: list,
    modelo_whisper: str = "base",
    idioma: str = "pt",
    aplicar_zoom: bool = True,
    aplicar_sfx: bool = True,
    pasta_sfx: str = None,
    intensidade: str = "medio",   # "leve" | "medio" | "intenso"
    progresso_callback=None,
) -> list:
    """
    Recebe clipes já exportados e aplica em UM único comando FFmpeg por clipe:
      1. Transcrição word-level (openai-whisper) → Smart Chunking
      2. Análise de efeitos com IA contextual (CoreEngine / fallback heurístico)
      3. Legenda ASS (caixa alta, pop-up, karaokê) — gerada antes, queimada no passe único
      4. Zoom dinâmico + legenda + SFX — todos no mesmo filter_complex/filter_graph
    Retorna resultados atualizados com 'arquivo_viral' quando bem-sucedido e
    'erro_viral' quando falhou, sem interromper os demais clipes.

    Parâmetro intensidade:
      "leve"    → zoom 1.08, silêncio_chunk 0.5s, poucas ênfases
      "medio"   → zoom 1.15, silêncio_chunk 0.3s (padrão)
      "intenso" → zoom 1.22, silêncio_chunk 0.2s, mais SFX
    """
    import tempfile
    import traceback as _traceback

    # ── Tabela de intensidade ─────────────────────────────────────────────────
    _INTENSIDADE = {
        "leve":    {"zoom_fator": 1.08, "zoom_dur": 0.3, "silencio_chunk": 0.5, "vol_sfx": 0.4},
        "medio":   {"zoom_fator": 1.15, "zoom_dur": 0.45, "silencio_chunk": 0.3, "vol_sfx": 0.6},
        "intenso": {"zoom_fator": 1.22, "zoom_dur": 0.6,  "silencio_chunk": 0.2, "vol_sfx": 0.8},
    }
    cfg = _INTENSIDADE.get(intensidade, _INTENSIDADE["medio"])

    def log(msg):
        print(msg)
        if progresso_callback:
            progresso_callback(msg)

    # ── Dependências ──────────────────────────────────────────────────────────
    try:
        import whisper as _whisper
    except ImportError:
        log("❌ openai-whisper não encontrado. Instale com: pip install openai-whisper")
        return resultados

    try:
        from CoreEngine import analyze_context_for_viral_effects, generate_subtitles_ass
    except ImportError as e:
        log(f"❌ CoreEngine não encontrado: {e}")
        return resultados

    # ── Localiza FFmpeg ───────────────────────────────────────────────────────
    import shutil as _shutil
    _ffmpeg = None
    for _cand in [
        _shutil.which("ffmpeg"),
        r"D:\CORTE VIRAL\files\tools\ffmpeg.exe",
        r"D:\CORTE VIRAL\tools\ffmpeg.exe",
    ]:
        if _cand and os.path.exists(_cand):
            _ffmpeg = _cand
            break
    _ffmpeg = _ffmpeg or "ffmpeg"

    if pasta_sfx is None:
        pasta_sfx = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sfx")

    log(f"\n🎬 Etapa 4 — Efeitos Virais | intensidade={intensidade}")
    log(f"   Whisper: {modelo_whisper} | Idioma: {idioma}")

    total = len(resultados)
    resultados_atualizados = []
    n_sucesso = 0
    n_falha = 0

    for i, resultado in enumerate(resultados, 1):
        caminho_clip = resultado.get("arquivo", "")
        titulo = resultado.get("titulo", f"Clipe {i}")
        path_ass = None  # garante que existe antes do bloco finally

        if not caminho_clip or not os.path.isfile(caminho_clip):
            log(f"   [{i}/{total}] ⚠️ Arquivo não encontrado, pulando: {caminho_clip}")
            resultados_atualizados.append(resultado)
            continue

        log(f"\n   [{i}/{total}] ▶ '{titulo}'")

        try:
            # ── 1. Transcrição word-level ──────────────────────────────────
            log(f"   [{i}/{total}] 🎙️ Transcrevendo...")
            modelo_wh = _whisper.load_model(modelo_whisper)
            transcricao = modelo_wh.transcribe(
                caminho_clip,
                language=idioma,
                word_timestamps=True,
                verbose=False,
            )

            palavras = [
                {"word": w["word"].strip(), "start": w["start"], "end": w["end"]}
                for seg in transcricao.get("segments", [])
                for w in seg.get("words", [])
                if w["word"].strip()
            ]

            # Smart Chunking com limiar de silêncio por intensidade
            silencio_chunk = cfg["silencio_chunk"]
            cartoes, cartao_atual, id_counter = [], [], 1
            for idx_p, p in enumerate(palavras):
                cartao_atual.append(p)
                quebrar = (
                    len(cartao_atual) >= 3
                    or (idx_p == len(palavras) - 1)
                    or (palavras[idx_p + 1]["start"] - p["end"] > silencio_chunk
                        if idx_p < len(palavras) - 1 else False)
                )
                if quebrar:
                    cartoes.append({
                        "id": id_counter,
                        "start": round(cartao_atual[0]["start"], 3),
                        "end":   round(cartao_atual[-1]["end"],  3),
                        "text":  " ".join(w["word"] for w in cartao_atual).upper(),
                    })
                    id_counter += 1
                    cartao_atual = []

            if not cartoes:
                log(f"   [{i}/{total}] ⚠️ Sem palavras detectadas. Clipe mantido sem efeitos.")
                resultado_copia = dict(resultado)
                resultado_copia["erro_viral"] = "sem_palavras"
                resultados_atualizados.append(resultado_copia)
                n_falha += 1
                continue

            log(f"   [{i}/{total}] ✅ {len(cartoes)} cartões")

            # ── 2. Análise com IA ──────────────────────────────────────────
            log(f"   [{i}/{total}] 🤖 Analisando com IA...")
            cartoes_enriquecidos = analyze_context_for_viral_effects(cartoes)

            # ── 3. Gerar arquivo .ass ──────────────────────────────────────
            fd_ass, path_ass = tempfile.mkstemp(suffix=".ass")
            os.close(fd_ass)
            generate_subtitles_ass(cartoes_enriquecidos, path_ass)
            escaped_ass = path_ass.replace("\\", "/").replace(":", "\\:")

            # ── 4. Montar filter_complex único ─────────────────────────────
            # Vídeo: zoom condicional → legenda ASS
            timestamps_zoom = [
                c["start"] for c in cartoes_enriquecidos if c.get("zoom")
            ] if aplicar_zoom else []

            if timestamps_zoom:
                fator = cfg["zoom_fator"]
                dur   = cfg["zoom_dur"]
                conds = "+".join(
                    f"between(t,{t:.3f},{t + dur:.3f})" for t in timestamps_zoom
                )
                expr_zoom = f"if(gt({conds},0),{fator:.3f},1)"
                vf_video = (
                    f"[0:v]scale=w='iw*({expr_zoom})':h='ih*({expr_zoom})':eval=frame,"
                    f"crop=1080:1920:(iw-1080)/2:(ih-1920)/2,"
                    f"ass='{escaped_ass}'[vout]"
                )
            else:
                vf_video = f"[0:v]ass='{escaped_ass}'[vout]"

            # Áudio: SFX com adelay → amix com voz
            inputs_sfx = []
            sfx_filters = []
            rotulos_sfx = []
            idx_sfx = 1

            if aplicar_sfx and os.path.isdir(pasta_sfx):
                vol_sfx = cfg["vol_sfx"]
                for c in cartoes_enriquecidos:
                    sfx_nome = c.get("sfx")
                    if not sfx_nome:
                        continue
                    sfx_path = next(
                        (os.path.join(pasta_sfx, sfx_nome + ext)
                         for ext in (".wav", ".mp3")
                         if os.path.exists(os.path.join(pasta_sfx, sfx_nome + ext))),
                        None,
                    )
                    if sfx_path:
                        delay_ms = int(c["start"] * 1000)
                        inputs_sfx += ["-i", sfx_path]
                        sfx_filters.append(
                            f"[{idx_sfx}:a]volume={vol_sfx:.2f},"
                            f"adelay={delay_ms}|{delay_ms}[sfx{idx_sfx}]"
                        )
                        rotulos_sfx.append(f"[sfx{idx_sfx}]")
                        idx_sfx += 1

            if sfx_filters:
                n_mix = 1 + len(rotulos_sfx)
                af_audio = (
                    ";".join(sfx_filters)
                    + f";[0:a]{''.join(rotulos_sfx)}"
                    + f"amix=inputs={n_mix}:duration=first:normalize=0[aout]"
                )
                filter_complex = vf_video + ";" + af_audio
                map_audio = "[aout]"
            else:
                filter_complex = vf_video
                map_audio = "0:a?"

            # ── 5. Executar FFmpeg — único passe, fallback robusto ─────────
            caminho_viral = caminho_clip.replace(".mp4", "_viral.mp4")
            cmd_base = (
                [_ffmpeg, "-y", "-i", caminho_clip]
                + inputs_sfx
                + ["-filter_complex", filter_complex,
                   "-map", "[vout]", "-map", map_audio,
                   "-c:a", "aac"]
            )

            encoder_usado = None
            _NVENC_ERROS = (
                "nvenc", "no capable devices", "out of memory",
                "invalid session", "driver", "not support",
                "nvcuda", "cuda", "no nvidia",
            )

            for encoder in ("h264_nvenc", "libx264"):
                cmd_tentativa = cmd_base + ["-c:v", encoder, caminho_viral]
                try:
                    proc = subprocess.run(
                        cmd_tentativa,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    encoder_usado = encoder
                    break
                except subprocess.CalledProcessError as err:
                    stderr_lower = (err.stderr or "").lower()
                    if encoder == "h264_nvenc":
                        motivo = next(
                            (m for m in _NVENC_ERROS if m in stderr_lower),
                            "erro desconhecido"
                        )
                        log(f"   [{i}/{total}] ⚠️ NVENC indisponível ({motivo}). Usando CPU...")
                        continue
                    raise RuntimeError(
                        f"FFmpeg falhou com ambos os encoders.\n{err.stderr[-800:]}"
                    )

            if path_ass and os.path.exists(path_ass):
                os.remove(path_ass)
                path_ass = None

            log(f"   [{i}/{total}] ✅ FFmpeg concluído [{encoder_usado}]")

            # ── Validação FFprobe do arquivo viral ─────────────────────────
            _val_viral = validar_midia_ffprobe(
                caminho_viral,
                duracao_esperada=resultado.get("duracao"),
                audio_policy="optional",
            )
            if not _val_viral["valid"]:
                for _err in _val_viral["errors"]:
                    log(f"   [{i}/{total}] ❌ Viral inválido: {_err}")
                _renomear_invalido(caminho_viral)
                log(f"   [{i}/{total}] ⚠️ Arquivo viral inválido — preservando clipe original.")
                resultado_copia = dict(resultado)
                # arquivo_viral aponta para o original como fallback
                resultado_copia["arquivo_viral"] = resultado.get("arquivo")
                resultado_copia["efeito_falhou"] = True
                resultado_copia["erro_viral"] = "validacao_ffprobe_falhou"
                resultados_atualizados.append(resultado_copia)
                n_falha += 1
            else:
                for _w in _val_viral["warnings"]:
                    log(f"   [{i}/{total}] ⚠️ {_w}")
                log(
                    f"   [{i}/{total}] ✅ '{os.path.basename(caminho_viral)}' validado "
                    f"({_val_viral['duration']:.1f}s | {_val_viral['width']}x{_val_viral['height']})"
                )
                resultado_atualizado = dict(resultado)
                resultado_atualizado["arquivo_viral"] = caminho_viral
                resultados_atualizados.append(resultado_atualizado)
                n_sucesso += 1

        except Exception as e:
            log(f"   [{i}/{total}] ❌ Falha no clipe '{titulo}': {e}")
            log(f"   {_traceback.format_exc()}")
            resultado_copia = dict(resultado)
            resultado_copia["erro_viral"] = str(e)
            resultados_atualizados.append(resultado_copia)
            n_falha += 1
        finally:
            if path_ass and os.path.exists(path_ass):
                os.remove(path_ass)

    log(
        f"\n🎉 Etapa 4 concluída — "
        f"{n_sucesso} com efeitos, {n_falha} sem efeitos (falha ou sem fala)."
    )
    if n_falha:
        falhos = [
            r.get("titulo", "?")
            for r in resultados_atualizados
            if r.get("erro_viral")
        ]
        log(f"   Clipes sem efeito: {', '.join(falhos)}")
    return resultados_atualizados