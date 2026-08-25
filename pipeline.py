"""
pipeline.py
-----------
Orquestra o pipeline completo da v2:

1. Detecta pessoas â†’ extrai previews
2. UsuÃ¡rio escolhe quem priorizar
3. Transcreve com Whisper
4. IA identifica segmentos (onde comeÃ§a/termina cada assunto)
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
from runtime import configurar_console_utf8, pasta_dados


configurar_console_utf8()


# Cache entre etapas
_cache = {}


def _pasta_estado() -> str:
    """Pasta gravavel onde o estado da analise sobrevive ao fechamento do app."""
    from runtime import pasta_dados
    caminho = os.path.join(pasta_dados(), "estado")
    os.makedirs(caminho, exist_ok=True)
    return caminho


def _persistir_estado(caminho_video: str) -> None:
    """Grava pessoas, transcricao e segmentos para a retomada nao re-transcrever."""
    from checkpoint import salvar_estado_analise
    try:
        salvar_estado_analise(_pasta_estado(), caminho_video, {
            "pessoas": _cache.get("pessoas") or [],
            "transcricao": _cache.get("transcricao"),
            "segmentos": _cache.get("segmentos") or [],
        })
    except (OSError, ValueError, ImportError):
        # Persistir e uma otimizacao de retomada: falhar aqui nunca derruba
        # o processamento em andamento.
        pass


def restaurar_estado_analise(caminho_video: str) -> dict:
    """Reidrata o cache em memoria a partir do estado salvo em disco.

    Retorna o que foi reaproveitado, para a interface mostrar no resumo.
    """
    from checkpoint import carregar_estado_analise
    if not caminho_video or not os.path.isfile(caminho_video):
        return {}
    if _cache.get("caminho_video") == caminho_video and _cache.get("transcricao"):
        return {}
    try:
        dados = carregar_estado_analise(_pasta_estado(), caminho_video)
    except (OSError, ValueError, ImportError):
        return {}
    if not dados:
        return {}
    reaproveitado = {}
    for chave in ("pessoas", "transcricao", "segmentos"):
        valor = dados.get(chave)
        if valor:
            _cache[chave] = valor
            reaproveitado[chave] = len(valor) if isinstance(valor, (list, dict)) else 1
    if reaproveitado:
        _cache["caminho_video"] = caminho_video
    return reaproveitado

# â”€â”€ Cancelamento cooperativo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_cancel_event = threading.Event()
_processamentos_ativos = set()
_processamentos_lock = threading.Lock()


def _normalizar_chave_processamento(chave: str) -> str:
    return os.path.normcase(os.path.abspath(str(chave)))


def _reservar_processamento(chave: str) -> bool:
    """Reserva atomicamente um projeto; False indica execução duplicada."""
    chave = _normalizar_chave_processamento(chave)
    with _processamentos_lock:
        if chave in _processamentos_ativos:
            return False
        _processamentos_ativos.add(chave)
        return True


def _liberar_processamento(chave: str) -> None:
    chave = _normalizar_chave_processamento(chave)
    with _processamentos_lock:
        _processamentos_ativos.discard(chave)

def _bloquear_processamento_duplicado(funcao):
    """Impede dois callbacks de escreverem no mesmo projeto ao mesmo tempo."""
    from functools import wraps

    @wraps(funcao)
    def executar(caminho_video, pasta_saida_base, *args, **kwargs):
        nome_video = os.path.splitext(os.path.basename(caminho_video))[0]
        chave = os.path.join(pasta_saida_base, sanitizar_nome(nome_video))
        if not _reservar_processamento(chave):
            raise RuntimeError(
                "Este vídeo já está sendo processado. Aguarde a execução atual; "
                "não clique em PROCESSAR novamente."
            )
        try:
            return funcao(caminho_video, pasta_saida_base, *args, **kwargs)
        finally:
            _liberar_processamento(chave)

    return executar

def solicitar_cancelamento():
    """Sinaliza para o pipeline interromper apÃ³s o clipe atual."""
    _cancel_event.set()

def limpar_cancelamento():
    """Reseta o flag de cancelamento antes de iniciar novo processamento."""
    _cancel_event.clear()

def _checar_cancelamento():
    """LanÃ§a CancelledError se cancelamento foi solicitado."""
    if _cancel_event.is_set():
        raise RuntimeError("Processamento cancelado pelo usuÃ¡rio.")


# â”€â”€ Constantes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
MAX_EXPORT_RETRIES = 1
_FFPROBE_TIMEOUT = 30  # segundos


# â”€â”€ ValidaÃ§Ã£o FFprobe â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _localizar_ffprobe() -> str:
    """Retorna o caminho do ffprobe usando resolução unificada."""
    from ffmpeg_utils import localizar_ffprobe
    return localizar_ffprobe()


def validar_midia_ffprobe(
    caminho_arquivo: str,
    duracao_esperada: float = None,
    audio_policy: str = "optional",
    tolerancia_duracao: float = None,
    timeout: int = _FFPROBE_TIMEOUT,
) -> dict:
    """
    Valida um arquivo de mÃ­dia com FFprobe.

    ParÃ¢metros:
        caminho_arquivo   : caminho absoluto do arquivo a validar.
        duracao_esperada  : duraÃ§Ã£o planejada em segundos (None = nÃ£o verifica).
        audio_policy      : "required" | "optional" | "none"
        tolerancia_duracao: segundos de tolerÃ¢ncia; None = max(0.5, esperada*0.02).
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

    # â”€â”€ 1. VerificaÃ§Ãµes de arquivo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not caminho_arquivo or not os.path.exists(caminho_arquivo):
        result["errors"].append("Arquivo nÃ£o encontrado.")
        return result

    if os.path.getsize(caminho_arquivo) == 0:
        result["errors"].append("Arquivo com tamanho zero.")
        return result

    # â”€â”€ 2. Executar FFprobe â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        result["errors"].append("FFprobe nÃ£o encontrado no sistema.")
        return result
    except subprocess.TimeoutExpired:
        result["errors"].append(f"FFprobe excedeu o timeout de {timeout}s.")
        return result
    except Exception as e:
        result["errors"].append(f"Erro ao executar FFprobe: {e}")
        return result

    if proc.returncode != 0:
        detalhe = (proc.stderr or "").strip()[:300]
        result["errors"].append(f"FFprobe retornou cÃ³digo {proc.returncode}. {detalhe}")
        return result

    # â”€â”€ 3. Parsear JSON â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        dados = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        result["errors"].append(f"Resposta do FFprobe nÃ£o Ã© JSON vÃ¡lido: {e}")
        return result

    streams = dados.get("streams", [])
    fmt = dados.get("format", {})

    # â”€â”€ 4. Streams de vÃ­deo e Ã¡udio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    stream_video = next((s for s in streams if s.get("codec_type") == "video"), None)
    stream_audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if stream_video:
        result["video_present"] = True
        result["video_codec"] = stream_video.get("codec_name")
        result["width"]  = stream_video.get("width", 0)
        result["height"] = stream_video.get("height", 0)

        if not result["width"] or result["width"] <= 0:
            result["errors"].append("Largura do vÃ­deo invÃ¡lida.")
        if not result["height"] or result["height"] <= 0:
            result["errors"].append("Altura do vÃ­deo invÃ¡lida.")
    else:
        result["errors"].append("Nenhum stream de vÃ­deo encontrado.")

    if stream_audio:
        result["audio_present"] = True
        result["audio_codec"] = stream_audio.get("codec_name")

    # â”€â”€ 5. PolÃ­tica de Ã¡udio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if audio_policy == "required" and not result["audio_present"]:
        result["errors"].append("Ãudio obrigatÃ³rio ausente (audio_policy=required).")
    elif audio_policy == "optional" and not result["audio_present"]:
        result["warnings"].append("Clipe sem trilha de Ã¡udio (aceito â€” audio_policy=optional).")
    # "none" â†’ sem verificaÃ§Ã£o de Ã¡udio

    # â”€â”€ 6. DuraÃ§Ã£o â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Tenta obter duraÃ§Ã£o: 1) stream de vÃ­deo â†’ 2) container (format)
    # NOTA: o ternÃ¡rio deve ser avaliado completamente antes do `or`, por isso
    # usamos uma variÃ¡vel intermediÃ¡ria em vez de encadear tudo numa expressÃ£o.
    _stream_dur = stream_video.get("duration") if stream_video else None
    dur_raw = _stream_dur or fmt.get("duration")
    if dur_raw:
        try:
            result["duration"] = float(dur_raw)
        except (ValueError, TypeError):
            pass

    if not result["duration"] or result["duration"] <= 0:
        result["errors"].append("DuraÃ§Ã£o invÃ¡lida ou zero.")
    elif duracao_esperada is not None and duracao_esperada > 0:
        tol = tolerancia_duracao if tolerancia_duracao is not None else max(0.5, duracao_esperada * 0.02)
        diff = abs(result["duration"] - duracao_esperada)
        result["duration_difference"] = round(diff, 3)
        if diff > tol:
            result["errors"].append(
                f"DuraÃ§Ã£o real ({result['duration']:.2f}s) difere da esperada "
                f"({duracao_esperada:.2f}s) em {diff:.2f}s (tolerÃ¢ncia: {tol:.2f}s)."
            )

    # â”€â”€ 7. Resultado final â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    result["valid"] = len(result["errors"]) == 0
    return result


def _renomear_invalido(caminho: str) -> str:
    """Renomeia arquivo para .invalid.mp4 para nÃ£o poluir a pasta de saÃ­da."""
    base, ext = os.path.splitext(caminho)
    novo = f"{base}.invalid{ext or '.mp4'}"
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
    Executa fn_exportar(), valida o resultado com FFprobe e faz 1 retry se invÃ¡lido.
    Respeita cancelamento cooperativo antes do retry.

    Retorna o dict de validaÃ§Ã£o. 'valid' indica sucesso.
    """
    for tentativa in range(1, MAX_EXPORT_RETRIES + 2):  # atÃ© 2 tentativas
        _checar_cancelamento()

        log_fn(f"{prefixo_log} Exportando (tentativa {tentativa}/{MAX_EXPORT_RETRIES + 1})...")
        try:
            fn_exportar()
        except RuntimeError as e:
            # Cancelamento ou erro de exportaÃ§Ã£o
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
                    log_fn(f"{prefixo_log} âš ï¸ {w}")
            log_fn(f"{prefixo_log} âœ… Clipe validado com sucesso. "
                   f"({val['duration']:.1f}s | {val['width']}x{val['height']} | "
                   f"codec={val['video_codec']})")
            return val

        # Falha
        for err in val["errors"]:
            log_fn(f"{prefixo_log} âŒ ValidaÃ§Ã£o: {err}")

        _renomear_invalido(caminho_saida)

        if tentativa > MAX_EXPORT_RETRIES:
            log_fn(f"{prefixo_log} âŒ Falha definitiva apÃ³s {MAX_EXPORT_RETRIES + 1} tentativa(s).")
            return val

        # Retry
        _checar_cancelamento()
        log_fn(f"{prefixo_log} ðŸ”„ Retry {tentativa}/{MAX_EXPORT_RETRIES}...")

    return val  # nunca alcanÃ§ado, mas satisfaz linter


def etapa1_detectar_pessoas(
    caminho_video: str,
    pasta_temp: str = None,
    progresso_callback=None
) -> list:
    """
    ETAPA 1: Detecta as pessoas no vÃ­deo e retorna previews.
    RÃ¡pido â€” analisa 30 frames distribuÃ­dos nos primeiros 5 minutos.
    """
    def log(msg):
        try:
            print(msg)
        except UnicodeEncodeError:
            # Console Windows em cp1252 nÃ£o imprime emoji â€” degrada sem quebrar
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        if progresso_callback:
            progresso_callback(msg)

    if not caminho_video or not os.path.isfile(caminho_video):
        raise FileNotFoundError("O vÃ­deo selecionado nÃ£o existe ou nÃ£o estÃ¡ acessÃ­vel.")

    # Imports pesados somente quando esta etapa Ã© usada. Isso reduz bastante
    # o tempo entre dar duplo clique e a interface aparecer.
    from rostos import detectar_pessoas_no_video, salvar_previews, VideoIlegivelError

    if pasta_temp is None:
        pasta_temp = os.path.join(pasta_dados(), "previews")
    if os.path.isdir(pasta_temp):
        for nome in os.listdir(pasta_temp):
            if nome.lower().endswith(".jpg"):
                try:
                    os.remove(os.path.join(pasta_temp, nome))
                except OSError:
                    pass

    log("ðŸ” Detectando pessoas no vÃ­deo...")
    # 30 amostras (era 10) â€” com vÃ­deo de vÃ¡rias cÃ¢meras, 10 frames
    # podiam cair todos no mesmo Ã¢ngulo e deixar pessoas sem detectar
    try:
        pessoas = detectar_pessoas_no_video(
            caminho_video,
            max_amostras=30,
            limite_minutos=5.0,
        )
    except VideoIlegivelError as e:
        # VÃ­deo incompleto (upload ainda rodando) ou corrompido: mostra a
        # mensagem clara na interface, sem traceback e sem fingir "0 pessoas".
        log(str(e))
        _cache["pessoas"] = []
        return []

    if not pessoas:
        log("âš ï¸ Nenhuma pessoa detectada. Usando enquadramento central.")
        _cache["pessoas"] = []
        return []

    pessoas = salvar_previews(pessoas, pasta_temp)
    _cache["pessoas"] = pessoas
    _cache["caminho_video"] = caminho_video
    _persistir_estado(caminho_video)

    log(f"âœ… {len(pessoas)} pessoa(s) encontrada(s). Escolha quem priorizar.")
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
        try:
            print(msg)
        except UnicodeEncodeError:
            # Console Windows em cp1252 nÃ£o imprime emoji â€” degrada sem quebrar
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        if progresso_callback:
            progresso_callback(msg)

    if not caminho_video or not os.path.isfile(caminho_video):
        raise FileNotFoundError("O vÃ­deo selecionado nÃ£o existe ou nÃ£o estÃ¡ acessÃ­vel.")
    if duracao_min <= 0 or duracao_max < duracao_min:
        raise ValueError("A duraÃ§Ã£o mÃ¡xima deve ser maior ou igual Ã  duraÃ§Ã£o mÃ­nima.")

    from analise import transcrever_video, segmentar_por_assunto

    log(f"ðŸ“ Transcrevendo com Whisper '{modelo_whisper}'...")
    transcricao = transcrever_video(caminho_video, idioma, modelo_whisper)
    _cache["transcricao"] = transcricao
    _cache["caminho_video"] = caminho_video

    log(f"ðŸ¤– Identificando segmentos (nicho: {nicho})...")
    segmentos = segmentar_por_assunto(transcricao, duracao_min, duracao_max, nicho, modo_offline=modo_offline)

    # â”€â”€ Refinamento de precisÃ£o â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Os segmentos vÃªm com tempos de frase (arredondados). Aqui ajustamos
    # inÃ­cio/fim para os limites reais das palavras (word timestamps do
    # Whisper), com um pequeno respiro â€” o corte nunca decapita palavra.
    from cortes import refinar_limites_com_palavras
    segmentos = refinar_limites_com_palavras(segmentos, transcricao)
    log("âœ‚ï¸ Limites de corte refinados com timestamps de palavras.")

    _cache["segmentos"] = segmentos
    _persistir_estado(caminho_video)
    log(f"âœ… {len(segmentos)} segmentos identificados!")
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

    ParÃ¢metros:
        pessoas_priorizadas_ids: lista de IDs das pessoas escolhidas pelo usuÃ¡rio
                                 (se vazio, prioriza todas)
    """
    def log(msg):
        try:
            print(msg)
        except UnicodeEncodeError:
            # Console Windows em cp1252 nÃ£o imprime emoji â€” degrada sem quebrar
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        if progresso_callback:
            progresso_callback(msg)

    if not caminho_video or not os.path.isfile(caminho_video):
        raise FileNotFoundError("O vÃ­deo selecionado nÃ£o existe ou nÃ£o estÃ¡ acessÃ­vel.")
    if not pasta_saida_base or not str(pasta_saida_base).strip():
        raise ValueError("Informe uma pasta de destino vÃ¡lida.")

    from cortes import cortar_clipe
    from enquadramento import aplicar_enquadramento
    from rostos import detectar_quem_fala_por_frame

    # Cria subpasta com nome do podcast
    nome_video = os.path.splitext(os.path.basename(caminho_video))[0]
    nome_pasta = sanitizar_nome(nome_video)
    pasta_saida = os.path.join(pasta_saida_base, nome_pasta)
    os.makedirs(pasta_saida, exist_ok=True)

    log(f"ðŸ“ Exportando para: {pasta_saida}")
    espaco_livre = shutil.disk_usage(pasta_saida).free
    if espaco_livre < 5 * 1024**3:
        raise OSError("EspaÃ§o livre insuficiente. Libere pelo menos 5 GB antes de processar.")

    segmentos = _validar_segmentos(segmentos)
    if not segmentos:
        log("âš ï¸ Nenhum segmento vÃ¡lido para processar.")
        return []

    total = len(segmentos)
    resultados = []

    for i, seg in enumerate(segmentos, 1):
        log(f"   âœ‚ï¸  [{i}/{total}] {seg.get('titulo', 'Clipe')} ({seg['inicio']}s â†’ {seg['fim']}s)")

        nome_arquivo = f"{i:02d}_{sanitizar_nome(seg.get('titulo', f'clipe_{i:02d}'))}.mp4"
        caminho_temp  = os.path.join(pasta_saida, f"_temp_{nome_arquivo}")
        caminho_final = os.path.join(pasta_saida, nome_arquivo)

        # Corta o clipe do vÃ­deo original
        sucesso = cortar_clipe(caminho_video, seg["inicio"], seg["fim"], caminho_temp)
        if not sucesso:
            if os.path.exists(caminho_temp):
                os.remove(caminho_temp)
            log(f"   âš ï¸ Erro ao cortar clipe {i}. Pulando...")
            continue

        # Analisa apenas o clipe selecionado. Antes esta etapa percorria o
        # podcast inteiro, mesmo quando poucos trechos seriam exportados.
        log(f"   ðŸŽ¤ [{i}/{total}] Detectando falante no clipe...")
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

        log(f"   ðŸŽ¬ [{i}/{total}] Enquadrando...")

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
            log(f"   âš ï¸ Erro no enquadramento do clipe {i}.")
            continue

        if os.path.exists(caminho_final):
            resultados.append({
                "titulo":      seg.get("titulo"),
                "arquivo":     caminho_final,
                "score_viral": seg.get("score_viral", 0),
                "resumo":      seg.get("resumo", ""),
                "duracao":     round(seg["fim"] - seg["inicio"], 1),
            })
            log(f"   âœ… Salvo: {nome_arquivo}")

    log(f"\nðŸŽ‰ ConcluÃ­do! {len(resultados)} clipes em: {pasta_saida}")
    return resultados


def _filtrar_por_pessoas_priorizadas(
    posicoes: list,
    pessoas: list,
    ids_priorizados: list
) -> list:
    """
    Ajusta as posiÃ§Ãµes do falante para focar nas pessoas priorizadas.
    Se o falante detectado nÃ£o estÃ¡ na lista de priorizados,
    mantÃ©m a cÃ¢mera na Ãºltima pessoa priorizada que falou.
    """
    # Mapa: faixa X â†’ id da pessoa
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

        # Verifica se estÃ¡ prÃ³ximo de uma pessoa priorizada
        mais_proximo = min(priorizadas_x, key=lambda px: abs(px - pos_x))
        distancia = abs(mais_proximo - pos_x)

        if distancia < 0.25:  # dentro de 25% da posiÃ§Ã£o da pessoa priorizada
            ultimo_priorizado = mais_proximo
            resultado[i] = mais_proximo
        else:
            # Pessoa falando nÃ£o estÃ¡ na lista de priorizados
            # MantÃ©m cÃ¢mera na Ãºltima priorizada
            resultado[i] = ultimo_priorizado

    return resultado


def sanitizar_nome(texto: str) -> str:
    texto = str(texto or "")
    texto = re.sub(r'[<>:"/\\|?*]', '', texto)
    texto = texto.replace(' ', '_')
    return texto[:60] or "clipe"


def _validar_segmentos(segmentos: list) -> list:
    """Descarta cortes invÃ¡lidos antes de iniciar o processamento pesado."""
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
    """Une clipes sobrepostos para nÃ£o analisar o mesmo frame duas vezes."""
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
    resultado = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if resultado.returncode != 0 or not resultado.stdout.strip():
        raise RuntimeError("FFprobe nÃ£o conseguiu ler o vÃ­deo.")
    dados = json.loads(resultado.stdout)
    stream = dados["streams"][0]
    fps_str = stream.get("r_frame_rate", "30/1")
    num, den = fps_str.split("/")
    den = int(den)
    return round(int(num) / den, 2) if den else 30.0


# Implementacao recuperavel. Esta definicao substitui a versao anterior acima.
@_bloquear_processamento_duplicado
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
    aplicar_hook: bool = False,
    progresso_callback=None,
    progresso_evento_callback=None,
) -> list:
    """Corta e enquadra os clipes, salvando um checkpoint apos cada etapa."""
    import time
    import traceback
    from datetime import datetime
    from checkpoint import (
        atualizar_progresso, caminho_checkpoint, carregar_checkpoint, criar_id_trabalho,
        inspecionar_retomada, novo_checkpoint, salvar_checkpoint,
    )
    from cortes import cortar_clipe, cortar_clipe_com_hook, validar_hook
    from enquadramento import aplicar_enquadramento
    from rostos import detectar_quem_fala_por_frame

    arquivo_log_trabalho = None

    def log(msg):
        try:
            print(msg)
        except UnicodeEncodeError:
            # Console Windows em cp1252 nÃ£o imprime emoji â€” degrada sem quebrar
            print(msg.encode("ascii", errors="replace").decode("ascii"))
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
        remover_pausas, min_silencio_ms, margem_silencio_ms, aplicar_hook,
    )
    arquivo_checkpoint = caminho_checkpoint(pasta_saida, id_trabalho)
    arquivo_log_trabalho = os.path.join(
        pasta_saida, f"viral_cutter_{id_trabalho}.log"
    )
    log("")
    log("=== Nova sessao de processamento ===")
    log(f"Video: {caminho_video}")
    # Retomada em processo novo: pessoas/transcricao/segmentos vivem so em
    # memoria durante a sessao. Sem reidratar, a deteccao de falante recebe
    # lista vazia e o clipe morre com "Nenhuma pessoa validada para enquadrar".
    _reaproveitado = restaurar_estado_analise(caminho_video)
    if _reaproveitado:
        log(f"Estado da analise reaproveitado do disco: {_reaproveitado}")
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

    inventario = inspecionar_retomada(
        checkpoint, pasta_saida, segmentos, caminho_log=arquivo_log_trabalho
    ) if retomar else {
        "concluidos": {}, "pendentes": list(range(1, total + 1)), "invalidos": [],
        "em_revisao": [], "prontos": [],
    }
    concluidos = {}
    for indice, arquivo in inventario["concluidos"].items():
        item = checkpoint["clipes"].get(str(indice), {})
        resultado = item.get("resultado") or {
            "titulo": segmentos[indice - 1].get("titulo"),
            "arquivo": arquivo,
            "score_viral": segmentos[indice - 1].get("score_viral", 0),
            "resumo": segmentos[indice - 1].get("resumo", ""),
            "duracao": round(segmentos[indice - 1]["fim"] - segmentos[indice - 1]["inicio"], 1),
            "inicio": segmentos[indice - 1]["inicio"],
            "fim": segmentos[indice - 1]["fim"],
        }
        concluidos[indice] = resultado
        # Preserva o status "revisar": um clipe sem enquadramento seguro nao
        # vira "concluido" so porque o arquivo existe.
        estado = "revisar" if indice in inventario.get("em_revisao", []) else "concluido"
        checkpoint["clipes"][str(indice)] = {
            "status": estado, "etapa": estado, "resultado": resultado,
            "motivos_revisao": resultado.get("motivos_revisao") or [],
        }
    for indice in inventario["invalidos"]:
        checkpoint["clipes"].setdefault(str(indice), {})["status"] = "pendente"
    if retomar and (inventario["concluidos"] or inventario["invalidos"]):
        salvar_checkpoint(arquivo_checkpoint, checkpoint)
    resultados_por_indice = dict(concluidos)
    inicio_sessao = time.monotonic()
    novos_concluidos = 0
    amostras_tempo = []

    def publicar_progresso(indice, etapa):
        evento = atualizar_progresso(
            checkpoint, indice=indice, etapa=etapa,
            concluidos=len(resultados_por_indice), total=total,
            inicio_sessao=inicio_sessao, agora=time.monotonic(),
            amostras=amostras_tempo,
        )
        salvar_checkpoint(arquivo_checkpoint, checkpoint)
        if progresso_evento_callback:
            progresso_evento_callback(evento)
        return evento
    if concluidos:
        _em_revisao = inventario.get("em_revisao") or []
        log(
            f"RETOMANDO: {len(concluidos) - len(_em_revisao)} pronto(s), "
            f"{len(inventario.get('pendentes') or [])} pendente(s), "
            f"{len(inventario.get('invalidos') or [])} invalido(s), "
            f"{len(_em_revisao)} em revisao - de {total} clipe(s)."
        )
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
        publicar_progresso(i, "corte")

        try:
            inicio_corte = time.monotonic()

            # â”€â”€ Hook automÃ¡tico (cold open) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Se ativado e a anÃ¡lise identificou a frase de maior impacto,
            # o clipe abre com ela antes de rodar do inÃ­cio.
            hook = validar_hook(seg) if aplicar_hook else None
            duracao_hook_s = 0.0  # segundos que o hook ADICIONA ao clipe
            if hook is not None:
                h_ini, h_fim = hook
                log(f"   [{i}/{total}] ðŸª Hook: abrindo com a frase de {h_ini:.1f}s-{h_fim:.1f}s")
                cortou = cortar_clipe_com_hook(
                    caminho_video, seg["inicio"], seg["fim"], h_ini, h_fim, caminho_temp
                )
                if cortou:
                    duracao_hook_s = h_fim - h_ini
                else:
                    log(f"   [{i}/{total}] âš ï¸ Corte com hook falhou. Usando corte normal...")
                    cortou = cortar_clipe(caminho_video, seg["inicio"], seg["fim"], caminho_temp)
            else:
                cortou = cortar_clipe(caminho_video, seg["inicio"], seg["fim"], caminho_temp)

            if not cortou:
                raise RuntimeError(f"Falha ao cortar o clipe {i}.")
            tempo_corte = time.monotonic() - inicio_corte

            duracao_pausas_removidas_s = 0.0  # segundos REMOVIDOS do clipe
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
                    duracao_pausas_removidas_s = resumo_silencio["removido_ms"] / 1000.0
                    os.replace(caminho_compacto, caminho_temp)
                    log(
                        f"   [{i}/{total}] "
                        f"{resumo_silencio['removido_ms'] / 1000:.1f}s de pausas removidos."
                    )
                elif os.path.exists(caminho_compacto):
                    os.remove(caminho_compacto)

            checkpoint["clipes"][str(i)]["etapa"] = "deteccao_falante"
            publicar_progresso(i, "deteccao_falante")
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
            publicar_progresso(i, "enquadramento")
            log(f"   [{i}/{total}] Enquadrando...")
            inicio_enquadramento = time.monotonic()
            relatorio_enq = {}
            sucesso = aplicar_enquadramento(
                caminho_temp, caminho_final, posicoes,
                pessoas_priorizadas_ids, qualidade=qualidade, perfil=perfil,
                relatorio=relatorio_enq
            )
            tempo_enquadramento = time.monotonic() - inicio_enquadramento
            if not sucesso or not os.path.isfile(caminho_final):
                raise RuntimeError(f"Falha no enquadramento do clipe {i}.")

            # â”€â”€ ValidaÃ§Ã£o FFprobe pÃ³s-enquadramento â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            checkpoint["clipes"][str(i)]["etapa"] = "validacao"
            publicar_progresso(i, "validacao")
            # DuraÃ§Ã£o esperada = corte base + hook (cold open) âˆ’ pausas removidas.
            # Sem esses ajustes a validaÃ§Ã£o rejeitava clipes corretos: o hook
            # ADICIONA segundos e o remove-pausas SUBTRAI.
            _dur_esperada = (
                seg["fim"] - seg["inicio"]
                + duracao_hook_s
                - duracao_pausas_removidas_s
            )
            _val = validar_midia_ffprobe(
                caminho_final,
                duracao_esperada=_dur_esperada,
                audio_policy="optional",
            )
            if not _val["valid"]:
                for _err in _val["errors"]:
                    log(f"   [{i}/{total}] âš ï¸ ValidaÃ§Ã£o: {_err}")
                _renomear_invalido(caminho_final)
                _checar_cancelamento()
                log(f"   [{i}/{total}] ðŸ”„ Retry 1/{MAX_EXPORT_RETRIES} â€” re-enquadrando...")
                # caminho_temp ainda existe (finally sÃ³ remove ao sair do bloco try)
                _dur_esperada_retry = _dur_esperada
                if not os.path.exists(caminho_temp):
                    if not cortar_clipe(caminho_video, seg["inicio"], seg["fim"], caminho_temp):
                        log(f"   [{i}/{total}] âŒ Retry: falha ao re-cortar clipe.")
                        checkpoint["clipes"][str(i)].update(
                            {"status": "erro", "erro": "validacao_falhou_apos_retry"}
                        )
                        salvar_checkpoint(arquivo_checkpoint, checkpoint)
                        continue
                    # O re-corte Ã© SEM hook e SEM remoÃ§Ã£o de pausas â€” a duraÃ§Ã£o
                    # esperada volta a ser a do segmento puro. Sem este ajuste,
                    # a validaÃ§Ã£o do retry rejeitava clipes corretos.
                    _dur_esperada_retry = seg["fim"] - seg["inicio"]
                relatorio_enq = {}
                _sucesso_retry = aplicar_enquadramento(
                    caminho_temp, caminho_final, posicoes,
                    pessoas_priorizadas_ids, qualidade=qualidade, perfil=perfil,
                    relatorio=relatorio_enq
                )
                if not _sucesso_retry or not os.path.isfile(caminho_final):
                    log(f"   [{i}/{total}] âŒ Retry: falha no enquadramento.")
                    checkpoint["clipes"][str(i)].update(
                        {"status": "erro", "erro": "enquadramento_retry_falhou"}
                    )
                    salvar_checkpoint(arquivo_checkpoint, checkpoint)
                    continue
                _val2 = validar_midia_ffprobe(
                    caminho_final,
                    duracao_esperada=_dur_esperada_retry,
                    audio_policy="optional",
                )
                if not _val2["valid"]:
                    for _err in _val2["errors"]:
                        log(f"   [{i}/{total}] âŒ Retry validaÃ§Ã£o: {_err}")
                    _renomear_invalido(caminho_final)
                    log(
                        f"   [{i}/{total}] âŒ Clipe {i} permanece invÃ¡lido apÃ³s "
                        f"{MAX_EXPORT_RETRIES + 1} tentativa(s). Pulando."
                    )
                    checkpoint["clipes"][str(i)].update(
                        {"status": "erro", "erro": "validacao_ffprobe_falhou"}
                    )
                    salvar_checkpoint(arquivo_checkpoint, checkpoint)
                    continue
                else:
                    log(f"   [{i}/{total}] âœ… Retry validado com sucesso.")
                    for _w in _val2["warnings"]:
                        log(f"   [{i}/{total}] âš ï¸ {_w}")
            else:
                # ValidaÃ§Ã£o OK na primeira tentativa
                for _w in _val["warnings"]:
                    log(f"   [{i}/{total}] âš ï¸ {_w}")
                log(
                    f"   [{i}/{total}] âœ… Validado: {_val['duration']:.1f}s | "
                    f"{_val['width']}x{_val['height']} | {_val['video_codec']}"
                )

            # Enquadramento seguro: sem modo seguro o clipe NAO conta como
            # concluido - vai para revisao manual com o motivo registrado.
            precisa_revisao = bool(relatorio_enq.get("revisar"))
            motivos_revisao = list(relatorio_enq.get("motivos") or [])
            instantes_revisao = list(relatorio_enq.get("instantes") or [])
            if precisa_revisao:
                _onde = (
                    " em " + ", ".join(f"{t:.1f}s" for t in instantes_revisao[:6])
                    if instantes_revisao else ""
                )
                log(
                    f"   [{i}/{total}] REVISAR enquadramento: "
                    f"{', '.join(motivos_revisao)}{_onde}"
                )

            resultado = {
                "titulo": seg.get("titulo"),
                "arquivo": caminho_final,
                "revisar": precisa_revisao,
                "motivos_revisao": motivos_revisao,
                "instantes_revisao": instantes_revisao,
                "score_viral": seg.get("score_viral", 0),
                "resumo": seg.get("resumo", ""),
                "duracao": round(seg["fim"] - seg["inicio"], 1),
                # Metadados para o SLICING da etapa 4: com eles as legendas
                # sÃ£o fatiadas da transcriÃ§Ã£o-mestre, sem re-transcrever.
                "inicio": seg["inicio"],
                "fim": seg["fim"],
                "hook_aplicado": [h_ini, h_fim] if duracao_hook_s > 0 else None,
                "pausas_removidas": duracao_pausas_removidas_s > 0,
                "tempos": {
                    "corte": round(tempo_corte, 1),
                    "falante": round(tempo_falante, 1),
                    "enquadramento": round(tempo_enquadramento, 1),
                },
            }
            resultados_por_indice[i] = resultado
            if not precisa_revisao:
                novos_concluidos += 1
            concluidos_total = len(resultados_por_indice)
            percentual = concluidos_total / total * 100
            decorrido = time.monotonic() - inicio_sessao
            amostras_tempo.append(time.monotonic() - inicio_corte)
            checkpoint["clipes"][str(i)] = {
                "status": "revisar" if precisa_revisao else "concluido",
                "etapa": "revisar" if precisa_revisao else "concluido",
                "resultado": resultado,
                "motivos_revisao": motivos_revisao,
            }
            checkpoint["ultimo_erro"] = None
            evento = publicar_progresso(i, "revisar" if precisa_revisao else "concluido")
            log(f"   [{i}/{total}] Salvo: {nome_arquivo}")
            log(
                f"   Tempos: corte {formatar_tempo(tempo_corte)} | "
                f"falante {formatar_tempo(tempo_falante)} | "
                f"enquadramento {formatar_tempo(tempo_enquadramento)}"
            )
            log(
                f"   Progresso: {concluidos_total}/{total} ({percentual:.0f}%)"
                f" | estimativa restante: {formatar_tempo(evento['estimativa_segundos'] or 0)}"
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
    em_revisao = [r for r in resultados if r.get("revisar")]
    prontos = len(resultados) - len(em_revisao)
    log(f"Concluido! {prontos} clipe(s) prontos em: {pasta_saida}")
    if em_revisao:
        log(f"{len(em_revisao)} clipe(s) marcados para REVISAR (enquadramento):")
        for r in em_revisao:
            log(f"   - {os.path.basename(r['arquivo'])}: "
                f"{', '.join(r.get('motivos_revisao') or ['sem_modo_seguro'])}")
    return resultados


# ---------------------------------------------------------------------------
# ETAPA 4 â€” EFEITOS VIRAIS (legendas ASS + zoom dinÃ¢mico + SFX)
# ---------------------------------------------------------------------------

def _fatiar_palavras_transcricao(transcricao: dict, resultado: dict) -> list:
    """
    SLICING: fatia as palavras do clipe a partir da transcriÃ§Ã£o-mestre da
    etapa 2, em vez de re-transcrever o clipe com Whisper (conceito visto
    no ViralCutter open source: "transcreve 1x, corta N vezes").

    Mapeia os word timestamps ABSOLUTOS do vÃ­deo original para a timeline
    do CLIPE, incluindo o hook (cold open) quando aplicado:

        [hook h_ini..h_fim] + [corte inicio..fim]
        â†’ palavras do hook em [0 .. dur_hook]
        â†’ palavras do corte em [dur_hook .. dur_hook + (fim-inicio)]

    Retorna lista [{word, start, end}] ou None quando o slicing nÃ£o Ã©
    seguro (sem metadados, sem transcriÃ§Ã£o, ou pausas removidas â€” que
    mudam a timeline de forma nÃ£o mapeÃ¡vel).
    """
    if not transcricao or not transcricao.get("segments"):
        return None
    inicio = resultado.get("inicio")
    fim = resultado.get("fim")
    if inicio is None or fim is None:
        return None  # resultado antigo (checkpoint) sem metadados
    if resultado.get("pausas_removidas"):
        return None  # timeline interna mudou; sÃ³ o Whisper sabe onde

    todas = [
        {"word": w["word"].strip(), "start": float(w["start"]), "end": float(w["end"])}
        for seg in transcricao["segments"]
        for w in seg.get("words", [])
        if w.get("word", "").strip() and w.get("start") is not None
    ]
    if not todas:
        return None

    def _janela(t_ini, t_fim, offset):
        """Palavras dentro de [t_ini, t_fim], reancoradas em offset."""
        saida = []
        for w in todas:
            if w["start"] >= t_ini - 0.05 and w["end"] <= t_fim + 0.05:
                saida.append({
                    "word": w["word"],
                    "start": round(max(0.0, w["start"] - t_ini + offset), 3),
                    "end": round(max(0.0, w["end"] - t_ini + offset), 3),
                })
        return saida

    palavras = []
    hook = resultado.get("hook_aplicado")
    dur_hook = 0.0
    if hook:
        h_ini, h_fim = float(hook[0]), float(hook[1])
        dur_hook = h_fim - h_ini
        palavras += _janela(h_ini, h_fim, 0.0)

    palavras += _janela(float(inicio), float(fim), dur_hook)
    return palavras or None


def etapa4_efeitos_virais(
    resultados: list,
    modelo_whisper: str = "base",
    idioma: str = "pt",
    aplicar_legenda: bool = True,
    aplicar_zoom: bool = True,
    aplicar_sfx: bool = True,
    pasta_sfx: str = None,
    intensidade: str = "medio",   # "leve" | "medio" | "intenso"
    progresso_callback=None,
) -> list:
    """
    Recebe clipes jÃ¡ exportados e aplica em UM Ãºnico comando FFmpeg por clipe:
      1. TranscriÃ§Ã£o word-level (openai-whisper) â†’ Smart Chunking
      2. AnÃ¡lise de efeitos com IA contextual (CoreEngine / fallback heurÃ­stico)
      3. Legenda ASS (caixa alta, pop-up, karaokÃª) â€” gerada antes, queimada no passe Ãºnico
      4. Zoom dinÃ¢mico + legenda + SFX â€” todos no mesmo filter_complex/filter_graph
    Retorna resultados atualizados com 'arquivo_viral' quando bem-sucedido e
    'erro_viral' quando falhou, sem interromper os demais clipes.

    ParÃ¢metro intensidade:
      "leve"    â†’ zoom 1.08, silÃªncio_chunk 0.5s, poucas Ãªnfases
      "medio"   â†’ zoom 1.15, silÃªncio_chunk 0.3s (padrÃ£o)
      "intenso" â†’ zoom 1.22, silÃªncio_chunk 0.2s, mais SFX
    """
    import tempfile
    import traceback as _traceback

    # â”€â”€ Tabela de intensidade â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _INTENSIDADE = {
        "leve":    {"zoom_fator": 1.08, "zoom_dur": 0.3, "silencio_chunk": 0.5, "vol_sfx": 0.4},
        "medio":   {"zoom_fator": 1.15, "zoom_dur": 0.45, "silencio_chunk": 0.3, "vol_sfx": 0.6},
        "intenso": {"zoom_fator": 1.22, "zoom_dur": 0.6,  "silencio_chunk": 0.2, "vol_sfx": 0.8},
    }
    cfg = _INTENSIDADE.get(intensidade, _INTENSIDADE["medio"])

    def log(msg):
        try:
            print(msg)
        except UnicodeEncodeError:
            # Console Windows em cp1252 nÃ£o imprime emoji â€” degrada sem quebrar
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        if progresso_callback:
            progresso_callback(msg)

    # â”€â”€ DependÃªncias â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        import whisper as _whisper
    except ImportError:
        log("âŒ openai-whisper nÃ£o encontrado. Instale com: pip install openai-whisper")
        return resultados

    try:
        from CoreEngine import analyze_context_for_viral_effects, generate_subtitles_ass
    except ImportError as e:
        log(f"âŒ CoreEngine nÃ£o encontrado: {e}")
        return resultados

    # ── Localiza FFmpeg ──────────────────────────────────────────────────────────
    from ffmpeg_utils import localizar_ffmpeg
    _ffmpeg = localizar_ffmpeg()

    if pasta_sfx is None:
        pasta_sfx = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sfx")

    if not (aplicar_legenda or aplicar_zoom or aplicar_sfx):
        log("ðŸŽ¬ Etapa 4 â€” nenhum efeito selecionado. Clipes mantidos como estÃ£o.")
        return resultados

    efeitos_ativos = [
        nome for nome, ativo in
        [("legendas", aplicar_legenda), ("zoom", aplicar_zoom), ("SFX", aplicar_sfx)]
        if ativo
    ]
    log(f"\nðŸŽ¬ Etapa 4 â€” Efeitos Virais | intensidade={intensidade} | efeitos: {' + '.join(efeitos_ativos)}")
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
            log(f"   [{i}/{total}] âš ï¸ Arquivo nÃ£o encontrado, pulando: {caminho_clip}")
            resultados_atualizados.append(resultado)
            continue

        log(f"\n   [{i}/{total}] â–¶ '{titulo}'")

        try:
            # â”€â”€ 1. TranscriÃ§Ã£o word-level â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # carregar_modelo_whisper usa cache: o modelo Ã© carregado uma
            # Ãºnica vez e reutilizado em todos os clipes do loop (antes,
            # recarregava 500MB-3GB do disco A CADA clipe).
            log(f"   [{i}/{total}] ðŸŽ™ï¸ Transcrevendo...")
            # â”€â”€ SLICING: tenta fatiar da transcriÃ§Ã£o-mestre (etapa 2) â”€â”€â”€â”€â”€
            # Transcreve 1x, corta N vezes: elimina uma passada de Whisper
            # por clipe. Fallback: transcrever o clipe como antes.
            palavras = _fatiar_palavras_transcricao(_cache.get("transcricao"), resultado)

            if palavras is not None:
                log(f"   [{i}/{total}] âš¡ Legendas fatiadas da transcriÃ§Ã£o-mestre "
                    f"({len(palavras)} palavras, sem re-transcrever).")
            else:
                import torch as _torch
                from analise import carregar_modelo_whisper
                _dispositivo = "cuda" if _torch.cuda.is_available() else "cpu"
                modelo_wh = carregar_modelo_whisper(modelo_whisper, _dispositivo)
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

            # Smart Chunking com limiar de silÃªncio por intensidade
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
                log(f"   [{i}/{total}] âš ï¸ Sem palavras detectadas. Clipe mantido sem efeitos.")
                resultado_copia = dict(resultado)
                resultado_copia["erro_viral"] = "sem_palavras"
                resultados_atualizados.append(resultado_copia)
                n_falha += 1
                continue

            log(f"   [{i}/{total}] âœ… {len(cartoes)} cartÃµes")

            # â”€â”€ 2. AnÃ¡lise com IA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            log(f"   [{i}/{total}] ðŸ¤– Analisando com IA...")
            cartoes_enriquecidos = analyze_context_for_viral_effects(cartoes)

            # â”€â”€ 3. Gerar arquivo .ass (sÃ³ se legendas estiverem ativas) â”€â”€â”€â”€
            filtro_ass = None
            if aplicar_legenda:
                fd_ass, path_ass = tempfile.mkstemp(suffix=".ass")
                os.close(fd_ass)
                generate_subtitles_ass(cartoes_enriquecidos, path_ass)
                escaped_ass = path_ass.replace("\\", "/").replace(":", "\\:")
                filtro_ass = f"ass='{escaped_ass}'"

            # â”€â”€ 4. Montar filter_complex Ãºnico â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # VÃ­deo: zoom condicional â†’ legenda ASS condicional
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
                partes_video = [
                    f"scale=w='iw*({expr_zoom})':h='ih*({expr_zoom})':eval=frame",
                    "crop=1080:1920:(iw-1080)/2:(ih-1920)/2",
                ]
                if filtro_ass:
                    partes_video.append(filtro_ass)
                vf_video = "[0:v]" + ",".join(partes_video) + "[vout]"
            elif filtro_ass:
                vf_video = f"[0:v]{filtro_ass}[vout]"
            else:
                # Sem legenda e sem zoom neste clipe: vÃ­deo passa direto
                vf_video = "[0:v]null[vout]"

            # Ãudio: SFX com adelay â†’ amix com voz
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

            # Nada a aplicar neste clipe (ex.: sÃ³ zoom ativo, mas a IA nÃ£o
            # marcou nenhum momento de Ãªnfase) â†’ evita re-encode inÃºtil.
            if vf_video == "[0:v]null[vout]" and not sfx_filters:
                log(f"   [{i}/{total}] â­ï¸ Nenhum efeito aplicÃ¡vel a este clipe. Mantido original.")
                resultados_atualizados.append(dict(resultado))
                continue

            # â”€â”€ 5. Executar FFmpeg â€” Ãºnico passe, fallback robusto â”€â”€â”€â”€â”€â”€â”€â”€â”€
            _base_clip, _ext_clip = os.path.splitext(caminho_clip)
            caminho_viral = f"{_base_clip}_viral{_ext_clip or '.mp4'}"
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
                        encoding="utf-8",
                        errors="replace",
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
                        log(f"   [{i}/{total}] âš ï¸ NVENC indisponÃ­vel ({motivo}). Usando CPU...")
                        continue
                    raise RuntimeError(
                        f"FFmpeg falhou com ambos os encoders.\n{err.stderr[-800:]}"
                    )

            if path_ass and os.path.exists(path_ass):
                os.remove(path_ass)
                path_ass = None

            log(f"   [{i}/{total}] âœ… FFmpeg concluÃ­do [{encoder_usado}]")

            # â”€â”€ ValidaÃ§Ã£o FFprobe do arquivo viral â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Compara com a duraÃ§Ã£o REAL do clipe de entrada (que pode ter
            # hook e pausas removidas), nÃ£o com a duraÃ§Ã£o teÃ³rica do segmento.
            _dur_entrada = validar_midia_ffprobe(caminho_clip).get("duration") or 0
            _val_viral = validar_midia_ffprobe(
                caminho_viral,
                duracao_esperada=_dur_entrada if _dur_entrada > 0 else resultado.get("duracao"),
                audio_policy="optional",
            )
            if not _val_viral["valid"]:
                for _err in _val_viral["errors"]:
                    log(f"   [{i}/{total}] âŒ Viral invÃ¡lido: {_err}")
                _renomear_invalido(caminho_viral)
                log(f"   [{i}/{total}] âš ï¸ Arquivo viral invÃ¡lido â€” preservando clipe original.")
                resultado_copia = dict(resultado)
                # arquivo_viral aponta para o original como fallback
                resultado_copia["arquivo_viral"] = resultado.get("arquivo")
                resultado_copia["efeito_falhou"] = True
                resultado_copia["erro_viral"] = "validacao_ffprobe_falhou"
                resultados_atualizados.append(resultado_copia)
                n_falha += 1
            else:
                for _w in _val_viral["warnings"]:
                    log(f"   [{i}/{total}] âš ï¸ {_w}")
                log(
                    f"   [{i}/{total}] âœ… '{os.path.basename(caminho_viral)}' validado "
                    f"({_val_viral['duration']:.1f}s | {_val_viral['width']}x{_val_viral['height']})"
                )
                resultado_atualizado = dict(resultado)
                resultado_atualizado["arquivo_viral"] = caminho_viral
                resultados_atualizados.append(resultado_atualizado)
                n_sucesso += 1

        except Exception as e:
            log(f"   [{i}/{total}] âŒ Falha no clipe '{titulo}': {e}")
            log(f"   {_traceback.format_exc()}")
            resultado_copia = dict(resultado)
            resultado_copia["erro_viral"] = str(e)
            resultados_atualizados.append(resultado_copia)
            n_falha += 1
        finally:
            if path_ass and os.path.exists(path_ass):
                os.remove(path_ass)

    log(
        f"\nðŸŽ‰ Etapa 4 concluÃ­da â€” "
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


