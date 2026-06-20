"""
main.py
-------
Pipeline dividido em duas etapas:
1. analisar_video() → transcreve + IA sugere cortes + sugere modo de enquadramento
2. processar_segmentos() → processa os clipes aprovados pelo usuário
"""

import os
import re
import json
from analise import transcrever_video, segmentar_por_assunto
from cortes import detectar_silencio, ajustar_cortes_com_silencio, cortar_clipe
from reframe import aplicar_reframe
from legendas import gerar_arquivo_ass, queimar_legendas
from historico import salvar_projeto

_transcricao_cache = {}


def sanitizar_nome(texto: str) -> str:
    texto = re.sub(r'[<>:"/\\|?*]', '', texto)
    texto = texto.replace(' ', '_')
    return texto[:50]


def filtrar_segmentos_por_tempo(segmentos_transcricao: list, inicio: float, fim: float) -> list:
    resultado = []
    for seg in segmentos_transcricao:
        if seg["end"] <= inicio or seg["start"] >= fim:
            continue
        resultado.append({
            "start": max(0, seg["start"] - inicio),
            "end":   min(fim - inicio, seg["end"] - inicio),
            "text":  seg["text"]
        })
    return resultado


def analisar_video(
    caminho_video: str,
    idioma: str = "pt",
    modelo_whisper: str = "small",
    nicho: str = "geral",
    duracao_min: int = 30,
    duracao_max: int = 90,
    cortar_silencio: bool = True,
    sensibilidade_silencio: int = 500,
    detectar_modo_auto: bool = True,
    progresso_callback=None
) -> tuple:
    """
    ETAPA 1: Transcreve + sugere cortes + sugere modo de enquadramento.

    Retorna:
        (segmentos, sugestao_modo)
        sugestao_modo = {"modo": "smart_cut", "motivo": "...", "n_pessoas": 2}
    """
    def atualizar(msg: str):
        print(msg)
        if progresso_callback:
            progresso_callback(msg)

    atualizar(f"📝 Transcrevendo com Whisper '{modelo_whisper}'...")
    transcricao = transcrever_video(caminho_video, idioma, modelo_whisper)

    atualizar(f"🤖 Analisando conteúdo com IA (nicho: {nicho})...")
    segmentos = segmentar_por_assunto(transcricao, duracao_min, duracao_max, nicho)

    if cortar_silencio:
        atualizar("🔇 Detectando silêncios...")
        silencias = detectar_silencio(caminho_video, min_silencio_ms=sensibilidade_silencio)
        segmentos = ajustar_cortes_com_silencio(segmentos, silencias)
    else:
        atualizar("⏭️ Corte em silêncios desativado.")

    _transcricao_cache[caminho_video] = transcricao

    # Detecta modo de enquadramento ideal
    sugestao_modo = {"modo": "tracking", "motivo": "padrão", "n_pessoas": 1}
    if detectar_modo_auto:
        try:
            atualizar("🧠 Detectando número de pessoas no vídeo...")
            from smart_cut import sugerir_modo_enquadramento
            sugestao_modo = sugerir_modo_enquadramento(caminho_video)
            atualizar(f"💡 Modo sugerido: {sugestao_modo['modo']} — {sugestao_modo['motivo']}")
        except Exception as e:
            atualizar(f"⚠️ Detecção automática falhou: {e}. Usando tracking.")

    atualizar(f"✅ {len(segmentos)} segmentos identificados!")
    return segmentos, sugestao_modo


def processar_segmentos(
    caminho_video: str,
    pasta_saida: str,
    segmentos: list,
    formato_saida: str = "9:16",
    qualidade: str = "1080p",
    modo_enquadramento: str = "tracking",
    suavizacao_tracking: int = 30,
    usar_legenda: bool = False,
    tipo_legenda: str = "caixa",
    fonte_legenda: str = "Arial",
    tamanho_legenda: int = 60,
    cor_texto: str = "#FFFFFF",
    cor_fundo: str = "#000000",
    opacidade_fundo: int = 60,
    posicao_legenda: str = "baixo-centro",
    progresso_callback=None
) -> list:
    """ETAPA 2: Processa os clipes aprovados."""

    def atualizar(msg: str):
        print(msg)
        if progresso_callback:
            progresso_callback(msg)

    os.makedirs(pasta_saida, exist_ok=True)
    resultados = []
    transcricao = _transcricao_cache.get(caminho_video, {"segments": []})

    total = len(segmentos)
    atualizar(f"✂️ Processando {total} clipes (modo: {modo_enquadramento}, {qualidade})...")

    for i, seg in enumerate(segmentos, 1):
        # Cada segmento pode ter seu próprio modo
        modo_seg = seg.get("modo_enquadramento", modo_enquadramento)

        nome_seguro  = sanitizar_nome(seg.get("titulo", f"clipe_{i:02d}"))
        score        = seg.get("score_viral", 0)
        nome_arquivo = f"{i:02d}_score{score}_{nome_seguro}"

        caminho_temp1 = os.path.join(pasta_saida, f"_temp1_{nome_arquivo}.mp4")
        caminho_temp2 = os.path.join(pasta_saida, f"_temp2_{nome_arquivo}.mp4")
        caminho_ass   = os.path.join(pasta_saida, f"_leg_{nome_arquivo}.ass")
        caminho_final = os.path.join(pasta_saida, f"{nome_arquivo}.mp4")

        atualizar(f"   ✂️  [{i}/{total}] {seg.get('titulo','Clipe')} ({seg['inicio']}s→{seg['fim']}s) [{modo_seg}]")

        sucesso = cortar_clipe(caminho_video, seg["inicio"], seg["fim"], caminho_temp1)
        if not sucesso:
            atualizar(f"   ⚠️ Erro ao cortar clipe {i}. Pulando...")
            continue

        # Modo dinâmico: detecta o melhor modo para ESTE clipe específico
        if modo_seg == "dinamico":
            try:
                from smart_cut import detectar_modo_para_clipe
                atualizar(f"   🧠 [{i}/{total}] Detectando pessoas no clipe...")
                modo_seg = detectar_modo_para_clipe(caminho_temp1)
                atualizar(f"   💡 [{i}/{total}] Modo detectado: {modo_seg}")
            except Exception as e:
                atualizar(f"   ⚠️ Detecção falhou: {e}. Usando tracking.")
                modo_seg = "tracking"

        atualizar(f"   🎬 [{i}/{total}] Reframe {formato_saida} {qualidade} [{modo_seg}]...")

        destino_reframe = caminho_temp2 if usar_legenda else caminho_final
        sucesso = aplicar_reframe(
            caminho_temp1, destino_reframe,
            formato=formato_saida,
            qualidade=qualidade,
            modo_enquadramento=modo_seg,
            suavizacao=suavizacao_tracking
        )

        if os.path.exists(caminho_temp1):
            os.remove(caminho_temp1)

        if not sucesso:
            atualizar(f"   ⚠️ Erro no reframe do clipe {i}. Pulando...")
            continue

        if usar_legenda:
            atualizar(f"   💬 [{i}/{total}] Gerando legendas...")
            segs_clipe = filtrar_segmentos_por_tempo(
                transcricao["segments"], seg["inicio"], seg["fim"]
            )
            gerar_arquivo_ass(
                segmentos_transcricao=segs_clipe,
                caminho_saida=caminho_ass,
                fonte=fonte_legenda, tamanho=tamanho_legenda,
                cor_texto=cor_texto, cor_fundo=cor_fundo,
                opacidade_fundo=opacidade_fundo,
                posicao=posicao_legenda, tipo=tipo_legenda,
            )
            atualizar(f"   🔥 [{i}/{total}] Queimando legendas...")
            sucesso = queimar_legendas(caminho_temp2, caminho_ass, caminho_final)
            for f_temp in [caminho_temp2, caminho_ass]:
                if os.path.exists(f_temp):
                    os.remove(f_temp)
            if not sucesso:
                atualizar(f"   ⚠️ Erro ao queimar legenda no clipe {i}.")
                continue

        if os.path.exists(caminho_final):
            resultados.append({
                "titulo":             seg.get("titulo"),
                "arquivo":            caminho_final,
                "score_viral":        score,
                "resumo":             seg.get("resumo", ""),
                "inicio":             seg["inicio"],
                "fim":                seg["fim"],
                "duracao":            round(seg["fim"] - seg["inicio"], 1),
                "com_legenda":        usar_legenda,
                "modo_enquadramento": modo_seg,
            })
            atualizar(f"   ✅ Clipe {i} salvo: {nome_arquivo}.mp4")

    if resultados:
        try:
            salvar_projeto(caminho_video, pasta_saida, resultados)
            atualizar("📚 Projeto salvo no histórico.")
        except Exception as e:
            atualizar(f"⚠️ Histórico: {e}")

    atualizar(f"\n🎉 Concluído! {len(resultados)} clipes gerados em: {pasta_saida}")
    return resultados


# Compatibilidade com código antigo
def processar_video(caminho_video, pasta_saida, idioma="pt", modelo_whisper="small",
    nicho="geral", duracao_min=30, duracao_max=90, formato_saida="9:16",
    qualidade="1080p", cortar_silencio=True, sensibilidade_silencio=500,
    usar_tracking=True, suavizacao_tracking=30, usar_legenda=False,
    tipo_legenda="caixa", fonte_legenda="Arial", tamanho_legenda=60,
    cor_texto="#FFFFFF", cor_fundo="#000000", opacidade_fundo=60,
    posicao_legenda="baixo-centro", progresso_callback=None) -> list:

    modo = "tracking" if usar_tracking else "fixo"
    segmentos, _ = analisar_video(
        caminho_video, idioma, modelo_whisper, nicho,
        duracao_min, duracao_max, cortar_silencio,
        sensibilidade_silencio, False, progresso_callback
    )
    return processar_segmentos(
        caminho_video, pasta_saida, segmentos, formato_saida, qualidade,
        modo, suavizacao_tracking, usar_legenda, tipo_legenda,
        fonte_legenda, tamanho_legenda, cor_texto, cor_fundo, opacidade_fundo,
        posicao_legenda, progresso_callback
    )
