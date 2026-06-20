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
import shutil
from runtime import pasta_dados


# Cache entre etapas
_cache = {}


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
