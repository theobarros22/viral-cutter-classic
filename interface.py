"""
interface.py — Viral Cutter v2
-------------------------------
Duas abas:
  1. Corte Viral — pipeline completo de corte + enquadramento
  2. Legendas Animadas — importa qualquer vídeo e aplica legendas virais
"""

import os
import sys
import glob as glob_mod
import logging
import time

from runtime import (
    configurar_ambiente,
    configurar_logs,
    escolher_porta,
    garantir_instancia_unica,
    pasta_dados,
    registrar_status,
)

INICIO_APP = time.perf_counter()
PASTA_BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
os.chdir(PASTA_BASE)
configurar_ambiente()
ARQUIVO_LOG = configurar_logs()

if not garantir_instancia_unica():
    raise SystemExit("O Viral Cutter já está aberto.")

# Força UTF-8 no console
try:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    else:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import gradio as gr
from pipeline import etapa1_detectar_pessoas, etapa2_analisar, etapa3_processar, limpar_cancelamento
from legendas import (
    TEMPLATES as TEMPLATES_LEGENDA,
    FONTES as FONTES_LEGENDA,
    aplicar_legendas,
    extrair_palavras_do_whisper,
    agrupar_palavras,
    instalar_remotion,
    importar_srt,
    exportar_srt,
)

# ── Constantes ────────────────────────────────────────────────────────────────

IDIOMAS = {
    "Português": "pt", "Inglês": "en", "Espanhol": "es",
    "Francês": "fr",   "Italiano": "it", "Alemão": "de",
}
MODELOS_WHISPER = {
    "base   — Muito rápido":          "base",
    "small  — Rápido na GPU ⭐": "small",
    "medium — Mais preciso":     "medium",
    "large  — Máxima precisão":  "large",
}
NICHOS = {
    "🎙️ Podcast":   "podcast",
    "🎯 Geral":     "geral",
    "💒 Casamento": "casamento",
    "🔍 Crime":     "crime",
    "⚽ Esporte":   "esporte",
    "📚 Educação":  "educacao",
}
QUALIDADES = {
    "1080p — Full HD ⭐": "1080p",
    "720p  — Leve":       "720p",
    "4K    — Ultra HD":   "4k",
}
PERFIS_PROCESSAMENTO = {
    "Rápido — análise visual reduzida": "rapido",
    "Equilibrado — recomendado ⭐": "equilibrado",
    "Máxima qualidade — análise detalhada": "qualidade",
}

# Legendas
TEMPLATES_LEGENDA_KEYS = {v: k for k, v in TEMPLATES_LEGENDA.items()}

POSICOES_LEGENDA = {
    "Inferior (padrão)": "bottom",
    "Centro":            "center",
    "Superior":          "top",
}

# ── Estado global ─────────────────────────────────────────────────────────────
_estado = {
    "caminho_video": None,
    "pessoas":       [],
    "segmentos":     [],
}

# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Space+Mono:wght@400;700&display=swap');

:root {
    --bg: #080808; --surface: #111; --surface2: #181818;
    --border: #242424; --accent: #e8ff47; --cyan: #00cec9;
    --text: #f0f0f0; --muted: #555; --radius: 10px;
}

body, .gradio-container {
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Syne', sans-serif !important;
}
.gradio-container { max-width: 960px !important; margin: 0 auto !important; padding: 32px 24px !important; }

.app-header { text-align: center; margin-bottom: 40px; padding-bottom: 32px; border-bottom: 1px solid var(--border); }
.app-header h1 { font-size: 2.8rem; font-weight: 800; color: var(--accent); letter-spacing: -2px; margin-bottom: 6px; }
.app-header p  { font-family: 'Space Mono', monospace; font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 3px; }

.sec { font-family: 'Space Mono', monospace; font-size: 0.7rem; text-transform: uppercase;
       letter-spacing: 4px; color: var(--accent); margin: 20px 0 12px;
       padding-bottom: 8px; border-bottom: 1px solid var(--border); }

.pessoa-card { background: var(--surface); border: 2px solid var(--border); border-radius: 10px;
               padding: 12px; text-align: center; cursor: pointer; transition: all 0.15s; }
.pessoa-card:hover  { border-color: var(--accent); }
.pessoa-card.ativa  { border-color: var(--accent); background: rgba(232,255,71,0.08); }
.pessoa-card img    { width: 100%; border-radius: 6px; margin-bottom: 8px; }
.pessoa-card span   { font-size: 12px; color: var(--text); }

.btn-detectar button { background: var(--cyan) !important; color: #000 !important;
    font-family: 'Syne', sans-serif !important; font-weight: 700 !important;
    border: none !important; border-radius: var(--radius) !important;
    padding: 12px 24px !important; width: 100% !important; cursor: pointer !important; }

.btn-analisar button { background: var(--surface2) !important; color: var(--cyan) !important;
    font-family: 'Syne', sans-serif !important; font-weight: 700 !important;
    border: 1px solid var(--cyan) !important; border-radius: var(--radius) !important;
    padding: 12px 24px !important; width: 100% !important; cursor: pointer !important; }

.btn-processar button { background: var(--accent) !important; color: #000 !important;
    font-family: 'Syne', sans-serif !important; font-weight: 800 !important; font-size: 1rem !important;
    border: none !important; border-radius: var(--radius) !important;
    padding: 16px 32px !important; width: 100% !important; cursor: pointer !important; }
.btn-processar button:hover { background: #fff !important; }

.btn-legendar button { background: #9b59b6 !important; color: #fff !important;
    font-family: 'Syne', sans-serif !important; font-weight: 800 !important; font-size: 1rem !important;
    border: none !important; border-radius: var(--radius) !important;
    padding: 16px 32px !important; width: 100% !important; cursor: pointer !important; }
.btn-legendar button:hover { background: #8e44ad !important; }

.output-log textarea { font-family: 'Space Mono', monospace !important; font-size: 0.78rem !important;
    background: #050505 !important; color: #88ff88 !important;
    border: 1px solid #1a3a1a !important; min-height: 180px !important; }

input[type=checkbox] { accent-color: var(--accent) !important; }
.gr-slider input[type=range] { accent-color: var(--accent) !important; }
"""

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — CORTE VIRAL (funções)
# ══════════════════════════════════════════════════════════════════════════════

def ao_detectar_pessoas(arquivo_video):
    if arquivo_video is None:
        return "❌ Envie um vídeo primeiro.", gr.update(visible=False), [], gr.update(choices=[], value=[])

    caminho = arquivo_video.name if hasattr(arquivo_video, 'name') else arquivo_video
    _estado["caminho_video"] = caminho

    log_lines = []
    def cb(msg): log_lines.append(msg)

    try:
        pessoas = etapa1_detectar_pessoas(caminho, progresso_callback=cb)
        _estado["pessoas"] = pessoas

        if not pessoas:
            return "\n".join(log_lines) + "\n⚠️ Nenhuma pessoa detectada.", gr.update(visible=False), [], gr.update(choices=[], value=[])

        previews = [(p["preview_path"], p["nome"]) for p in pessoas if "preview_path" in p]
        opcoes   = [p["nome"] for p in pessoas]

        return (
            "\n".join(log_lines),
            gr.update(visible=True),
            previews,
            gr.update(choices=opcoes, value=opcoes)
        )

    except Exception as e:
        import traceback
        return f"❌ Erro:\n{str(e)}\n{traceback.format_exc()}", gr.update(visible=False), [], gr.update(choices=[], value=[])


def ao_analisar(idioma_label, modelo_label, nicho_label, duracao_min, duracao_max, modo_offline):
    if not _estado.get("caminho_video"):
        return "❌ Detecte as pessoas primeiro."

    idioma = IDIOMAS.get(idioma_label, "pt")
    modelo = MODELOS_WHISPER.get(modelo_label, "small")
    nicho  = NICHOS.get(nicho_label, "podcast")
    # Salva no estado para etapa 4 reutilizar sem pedir ao usuário novamente
    _estado["idioma_label"] = idioma_label
    _estado["modelo_whisper_label"] = modelo_label

    log_lines = []
    def cb(msg): log_lines.append(msg)

    try:
        segmentos = etapa2_analisar(
            _estado["caminho_video"],
            idioma, modelo, nicho,
            int(duracao_min), int(duracao_max),
            modo_offline=modo_offline,
            progresso_callback=cb
        )
        _estado["segmentos"] = segmentos

        log_lines.append("")
        log_lines.append("━" * 45)
        log_lines.append(f"✅ {len(segmentos)} segmentos identificados!")
        log_lines.append("⬇️  Configure as opções e clique em PROCESSAR.")
        log_lines.append("━" * 45)

        return "\n".join(log_lines)

    except Exception as e:
        import traceback
        return f"❌ Erro:\n{str(e)}\n{traceback.format_exc()}"


def ao_processar(
    pasta_saida, qualidade_label, perfil_label,
    retomar_processamento, remover_pausas,
    min_silencio_ms, margem_silencio_ms,
    pessoas_selecionadas, aplicar_legendas_auto,
    usar_efeitos_virais=False,
):
    if not _estado.get("caminho_video"):
        return "❌ Detecte as pessoas primeiro.", "", [], gr.update(visible=False, choices=[], value=None)
    if not _estado.get("segmentos") and not retomar_processamento:
        return "❌ Analise o vídeo primeiro.", "", [], gr.update(visible=False, choices=[], value=None)
    if not pasta_saida.strip():
        return "❌ Informe a pasta de destino.", "", [], gr.update(visible=False, choices=[], value=None)

    qualidade = QUALIDADES.get(qualidade_label, "1080p")
    perfil = PERFIS_PROCESSAMENTO.get(perfil_label, "equilibrado")

    ids_priorizados = []
    for pessoa in _estado.get("pessoas", []):
        if pessoa["nome"] in (pessoas_selecionadas or []):
            ids_priorizados.append(pessoa["id"])

    # Reseta o flag de cancelamento de uma execução anterior
    limpar_cancelamento()

    log_lines = []
    def cb(msg): log_lines.append(msg)

    try:
        resultados = etapa3_processar(
            caminho_video=_estado["caminho_video"],
            pasta_saida_base=pasta_saida,
            segmentos=_estado["segmentos"],
            pessoas_priorizadas_ids=ids_priorizados if ids_priorizados else None,
            qualidade=qualidade,
            perfil=perfil,
            retomar=retomar_processamento,
            remover_pausas=remover_pausas,
            min_silencio_ms=int(min_silencio_ms),
            margem_silencio_ms=int(margem_silencio_ms),
            progresso_callback=cb,
        )

        # ── Etapa 4: Efeitos Virais (legendas ASS + zoom + SFX) ──────────
        if usar_efeitos_virais and resultados:
            from pipeline import etapa4_efeitos_virais
            # Usa o mesmo modelo Whisper escolhido pelo usuário na etapa 2
            modelo_wh = MODELOS_WHISPER.get(
                _estado.get("modelo_whisper_label", "base   — Muito rápido"), "base"
            )
            idioma_wh = IDIOMAS.get(
                _estado.get("idioma_label", "Português"), "pt"
            )
            resultados = etapa4_efeitos_virais(
                resultados,
                modelo_whisper=modelo_wh,
                idioma=idioma_wh,
                progresso_callback=cb,
            )

        relatorio = f"\n{'═'*45}\n"
        relatorio += f"  ✅ {len(resultados)} CLIPES GERADOS\n"
        if usar_efeitos_virais:
            n_virais = sum(1 for r in resultados if r.get("arquivo_viral"))
            relatorio += f"  ⚡ {n_virais} clipe(s) com efeitos virais\n"
        relatorio += f"  📁 {pasta_saida}\n"
        relatorio += f"{'═'*45}\n\n"
        for i, r in enumerate(resultados, 1):
            relatorio += f"  [{i}] {r['titulo']}\n"
            relatorio += f"      ⏱️ {r['duracao']}s  |  ⭐ {r['score_viral']}/10\n"
            relatorio += f"      💡 {r['resumo']}\n"
            if r.get("arquivo_viral"):
                relatorio += f"      ⚡ {os.path.basename(r['arquivo_viral'])}\n"
            relatorio += "\n"

        # Mostra clipes virais na galeria se existirem, senão os originais
        videos = []
        for r in resultados:
            arq = r.get("arquivo_viral") or r.get("arquivo", "")
            if arq and os.path.exists(arq):
                videos.append(arq)

        return (
            "\n".join(log_lines),
            relatorio,
            videos,
            gr.update(visible=True, choices=videos, value=videos[0] if videos else None)
        )

    except Exception as e:
        import traceback
        return f"❌ Erro:\n{str(e)}\n{traceback.format_exc()}", "", [], gr.update(visible=False, choices=[], value=None)


def ao_cancelar_processo():
    from pipeline import solicitar_cancelamento
    solicitar_cancelamento()
    return "🛑 Solicitação de cancelamento enviada. O processamento será interrompido após o clipe atual."


def abrir_pasta_export(pasta):
    if os.path.exists(pasta):
        try:
            os.startfile(pasta)
            return f"✅ Pasta aberta: {pasta}"
        except Exception as e:
            return f"❌ Erro ao abrir pasta: {e}"
    return f"❌ Pasta não encontrada: {pasta}"


def abrir_logs():
    from runtime import pasta_dados
    pasta = os.path.join(pasta_dados(), "logs")
    if os.path.exists(pasta):
        try:
            os.startfile(pasta)
            return f"✅ Pasta de logs aberta: {pasta}"
        except Exception as e:
            return f"❌ Erro ao abrir pasta de logs: {e}"
    return f"❌ Pasta de logs não encontrada: {pasta}"



# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 — LEGENDAS ANIMADAS (funções)
# ══════════════════════════════════════════════════════════════════════════════

def ao_escanear_pasta(pasta):
    """Escaneia uma pasta e retorna lista de vídeos encontrados."""
    if not pasta or not pasta.strip():
        return gr.update(choices=[], value=None), "❌ Informe o caminho da pasta."

    pasta = pasta.strip()
    if not os.path.isdir(pasta):
        return gr.update(choices=[], value=None), f"❌ Pasta não encontrada: {pasta}"

    extensoes = (".mp4", ".mov", ".avi", ".mkv", ".webm")
    videos = []
    for f in sorted(os.listdir(pasta)):
        if f.lower().endswith(extensoes) and not f.startswith("_"):
            videos.append(os.path.join(pasta, f))

    if not videos:
        return gr.update(choices=[], value=None), f"⚠️ Nenhum vídeo encontrado em: {pasta}"

    nomes = [os.path.basename(v) for v in videos]
    return (
        gr.update(choices=videos, value=videos[0]),
        f"✅ {len(videos)} vídeo(s) encontrado(s):\n" + "\n".join(f"  • {n}" for n in nomes)
    )


def ao_obter_transcricao(
    arquivo_upload,
    video_selecionado,
    srt_upload,
    idioma_label,
    modelo_whisper_label,
):
    """Obtém ou carrega a transcrição para edição."""
    # Determina qual vídeo usar: upload tem prioridade sobre seleção de pasta
    caminho_video = None
    if arquivo_upload is not None:
        caminho_video = arquivo_upload.name if hasattr(arquivo_upload, 'name') else arquivo_upload
    elif video_selecionado:
        caminho_video = video_selecionado

    if not caminho_video:
        return "❌ Envie um vídeo ou selecione um da pasta.", gr.update(value=[], visible=False), gr.update(visible=False)

    if not os.path.exists(caminho_video):
        return f"❌ Arquivo não encontrado: {caminho_video}", gr.update(value=[], visible=False), gr.update(visible=False)

    log_lines = []
    def log(msg):
        print(msg)
        log_lines.append(msg)

    try:
        # Se enviou SRT, importa direto
        if srt_upload is not None:
            caminho_srt = srt_upload.name if hasattr(srt_upload, 'name') else srt_upload
            log(f"📄 Carregando legenda SRT externa: {os.path.basename(caminho_srt)}...")
            palavras = importar_srt(caminho_srt)
            log(f"✅ {len(palavras)} legendas importadas do SRT.")
        else:
            modelo_nome = MODELOS_WHISPER.get(modelo_whisper_label, "small")
            idioma = IDIOMAS.get(idioma_label, "pt")
            log(f"🎙️ Transcrevendo com Whisper '{modelo_nome}'...")

            import torch

            dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
            # Cache central: não recarrega o modelo se já está em memória
            from analise import carregar_modelo_whisper
            modelo = carregar_modelo_whisper(modelo_nome, dispositivo)

            from analise import _extrair_audio_wav, _obter_duracao_segundos
            import tempfile

            duracao = _obter_duracao_segundos(caminho_video)
            wav_temp = os.path.join(tempfile.gettempdir(), "_legendas_audio.wav")

            log("🔊 Extraindo áudio...")
            _extrair_audio_wav(caminho_video, wav_temp)

            log("📝 Transcrevendo... (pode demorar)")
            resultado = modelo.transcribe(
                wav_temp, language=idioma, verbose=False,
                fp16=(dispositivo == "cuda"),
                word_timestamps=True
            )

            if os.path.exists(wav_temp):
                os.remove(wav_temp)

            palavras = extrair_palavras_do_whisper(resultado, 0, duracao)
            log(f"✅ {len(palavras)} palavras detectadas com timestamps.")

        if not palavras:
            log("⚠️ Nenhuma palavra detectada.")
            return "\n".join(log_lines), gr.update(value=[], visible=False), gr.update(visible=False)

        dados_tabela = [[p["inicio"], p["fim"], p["texto"]] for p in palavras]
        return (
            "\n".join(log_lines),
            gr.update(value=dados_tabela, visible=True),
            gr.update(visible=True),
        )

    except Exception as e:
        import traceback
        return f"❌ Erro:\n{str(e)}\n{traceback.format_exc()}", gr.update(value=[], visible=False), gr.update(visible=False)


def ao_renderizar_legendas(
    arquivo_upload,
    video_selecionado,
    dados_tabela,
    template_label,
    cor_texto, cor_destaque, posicao_label,
    pasta_saida_leg,
    fonte_label="Padrão do template",
    tamanho_base=0,
):
    """Renderiza o vídeo com as legendas editadas."""
    caminho_video = None
    if arquivo_upload is not None:
        caminho_video = arquivo_upload.name if hasattr(arquivo_upload, 'name') else arquivo_upload
    elif video_selecionado:
        caminho_video = video_selecionado

    if not caminho_video:
        return "❌ Envie um vídeo ou selecione um da pasta.", []

    if not os.path.exists(caminho_video):
        return f"❌ Arquivo não encontrado: {caminho_video}", []

    if dados_tabela is None or len(dados_tabela) == 0:
        return "❌ Tabela de legendas vazia.", []

    # Pasta de saída
    if not pasta_saida_leg or not pasta_saida_leg.strip():
        pasta_saida_leg = os.path.dirname(caminho_video)

    os.makedirs(pasta_saida_leg, exist_ok=True)

    template_id = TEMPLATES_LEGENDA_KEYS.get(template_label, "palavra-vazada")
    posicao = POSICOES_LEGENDA.get(posicao_label, "bottom")

    config = {
        "corTexto": cor_texto or "#FFFFFF",
        "corDestaque": cor_destaque or "#e8ff47",
        "posicao": posicao,
    }

    if fonte_label and fonte_label != "Padrão do template":
        config["fonte"] = FONTES_LEGENDA.get(fonte_label, fonte_label)

    if tamanho_base and tamanho_base > 0:
        config["tamanhoBase"] = int(tamanho_base)

    palavras = []
    for row in dados_tabela:
        try:
            palavras.append({
                "inicio": float(row[0]),
                "fim": float(row[1]),
                "texto": str(row[2]).strip()
            })
        except Exception:
            continue

    log_lines = []
    def log(msg):
        print(msg)
        log_lines.append(msg)

    try:
        nome_base = os.path.splitext(os.path.basename(caminho_video))[0]
        nome_saida = f"{nome_base}_legendado.mp4"
        caminho_saida = os.path.join(pasta_saida_leg, nome_saida)

        sucesso = aplicar_legendas(
            caminho_video,
            caminho_saida,
            palavras,
            template=template_id,
            config=config,
            progresso_callback=log,
        )

        if sucesso and os.path.exists(caminho_saida):
            log(f"\n{'═'*45}")
            log(f"  ✅ VÍDEO LEGENDADO!")
            log(f"  📁 {caminho_saida}")
            log(f"{'═'*45}")
            return "\n".join(log_lines), [caminho_saida]

        return "\n".join(log_lines), []

    except Exception as e:
        import traceback
        return f"❌ Erro:\n{str(e)}\n{traceback.format_exc()}", []


def ao_exportar_legenda_srt(
    arquivo_upload,
    video_selecionado,
    dados_tabela,
    pasta_saida_leg,
):
    """Exporta as legendas atuais da tabela para SRT."""
    caminho_video = None
    if arquivo_upload is not None:
        caminho_video = arquivo_upload.name if hasattr(arquivo_upload, 'name') else arquivo_upload
    elif video_selecionado:
        caminho_video = video_selecionado

    if not caminho_video:
        return "❌ Envie um vídeo ou selecione um da pasta para exportar."

    if dados_tabela is None or len(dados_tabela) == 0:
        return "❌ Nenhuma legenda na tabela para exportar."

    if not pasta_saida_leg or not pasta_saida_leg.strip():
        pasta_saida_leg = os.path.dirname(caminho_video)

    os.makedirs(pasta_saida_leg, exist_ok=True)
    nome_base = os.path.splitext(os.path.basename(caminho_video))[0]
    caminho_srt = os.path.join(pasta_saida_leg, f"{nome_base}_legenda.srt")

    palavras = []
    for row in dados_tabela:
        try:
            palavras.append({
                "inicio": float(row[0]),
                "fim": float(row[1]),
                "texto": str(row[2]).strip()
            })
        except Exception:
            continue

    if exportar_srt(palavras, caminho_srt):
        return f"✅ Legenda SRT exportada com sucesso em:\n{caminho_srt}"
    return "❌ Erro ao exportar SRT."


# ══════════════════════════════════════════════════════════════════════════════
# INTERFACE PRINCIPAL (Tabs)
# ══════════════════════════════════════════════════════════════════════════════

def criar_interface():
    with gr.Blocks(css=CSS, title="Viral Cutter v2") as app:

        gr.HTML("""
        <div class="app-header">
            <h1>VIRAL CUTTER</h1>
            <p>Corte automático + Legendas animadas — v2</p>
        </div>
        """)

        with gr.Tabs() as tabs:

            # ══════════════════════════════════════════════════════════════
            # TAB 1 — CORTE VIRAL
            # ══════════════════════════════════════════════════════════════
            with gr.Tab("✂️  Corte Viral", id="tab_corte"):

                gr.HTML('<p class="sec">01 — Upload do Vídeo</p>')
                arquivo_video = gr.File(label="Vídeo longo", file_types=["video"])

                with gr.Row(elem_classes="btn-detectar"):
                    btn_detectar = gr.Button("🔍  DETECTAR PESSOAS", scale=1)

                log_deteccao = gr.Textbox(label="", interactive=False, lines=4, elem_classes="output-log")

                with gr.Group(visible=False) as painel_rostos:
                    gr.HTML('<p class="sec">02 — Escolha Quem Priorizar</p>')
                    gr.Markdown("*Selecione as pessoas que devem ser priorizadas no enquadramento.*")

                    galeria_rostos = gr.Gallery(
                        label="Pessoas detectadas", show_label=False,
                        columns=4, height=220, object_fit="cover",
                    )

                    pessoas_opcoes = gr.CheckboxGroup(
                        choices=[], value=[],
                        label="✅ Marque quem priorizar:",
                    )

                gr.HTML('<p class="sec">03 — Transcrição & Análise</p>')
                with gr.Row():
                    idioma  = gr.Dropdown(choices=list(IDIOMAS.keys()),         value="Português",             label="Idioma")
                    modelo  = gr.Dropdown(choices=list(MODELOS_WHISPER.keys()), value="small  — Rápido na GPU ⭐", label="Modelo Whisper")
                    nicho   = gr.Dropdown(choices=list(NICHOS.keys()),          value="🎙️ Podcast",             label="Nicho")

                modo_offline = gr.Checkbox(
                    label="📴 Modo offline — sem API (não consome créditos)",
                    value=False
                )

                with gr.Row():
                    duracao_min = gr.Slider(minimum=15, maximum=120, value=30, step=5, label="Duração mínima (s)")
                    duracao_max = gr.Slider(minimum=30, maximum=180, value=90, step=5, label="Duração máxima (s)")

                with gr.Row(elem_classes="btn-analisar"):
                    btn_analisar = gr.Button("🎙️  TRANSCREVER & ANALISAR", scale=1)

                log_analise = gr.Textbox(label="", interactive=False, lines=6, elem_classes="output-log")

                gr.HTML('<p class="sec">04 — Export & Processamento</p>')
                with gr.Row():
                    pasta_saida = gr.Textbox(
                        label="Pasta de export",
                        value=os.path.join(os.path.expanduser("~"), "Desktop", "viral-clipes"),
                        scale=2
                    )
                    qualidade = gr.Dropdown(
                        choices=list(QUALIDADES.keys()),
                        value="1080p — Full HD ⭐",
                        label="Qualidade", scale=1
                    )
                    perfil_processamento = gr.Dropdown(
                        choices=list(PERFIS_PROCESSAMENTO.keys()),
                        value="Equilibrado — recomendado ⭐",
                        label="Velocidade", scale=1
                    )

                with gr.Row():
                    retomar_processamento = gr.Checkbox(
                        label="Retomar automaticamente de onde parou",
                        value=True,
                        info="Ao reabrir, carregue o mesmo vídeo, escolha quem priorizar e processe.",
                    )
                    remover_pausas = gr.Checkbox(
                        label="Remover automaticamente pausas e silêncios internos",
                        value=False,
                        info="Ideal para vídeos falados. Preserva uma pequena respiração.",
                    )

                with gr.Row():
                    min_silencio_ms = gr.Slider(
                        minimum=300, maximum=2000, value=700, step=100,
                        label="Pausa mínima para remover (ms)",
                    )
                    margem_silencio_ms = gr.Slider(
                        minimum=0, maximum=300, value=120, step=20,
                        label="Respiração preservada (ms)",
                    )

                legendar_automaticamente = gr.Checkbox(
                    label="🎨 Aplicar legendas automáticas nos clipes gerados (Estilo: Palavra Vazada)",
                    value=False
                )

                aplicar_efeitos_virais = gr.Checkbox(
                    label="⚡ Aplicar efeitos virais após processamento (legendas ASS + zoom dinâmico + SFX)",
                    value=False,
                    info="Cada clipe recebe legenda palavra por palavra com pop-up e karaokê, zoom nos momentos de ênfase e efeitos sonoros automáticos.",
                )

                gr.HTML('<div style="height:16px"></div>')
                with gr.Row():
                    btn_processar = gr.Button("⚡  PROCESSAR VÍDEO", scale=3, variant="primary")
                    btn_cancelar = gr.Button("🛑 CANCELAR", scale=1, variant="stop")

                gr.HTML('<p class="sec" style="margin-top:28px">05 — Resultado</p>')
                with gr.Row():
                    btn_abrir_saida = gr.Button("📂 Abrir pasta de saída", scale=1)
                    btn_abrir_logs = gr.Button("📝 Abrir pasta de logs", scale=1)
                log_processo   = gr.Textbox(label="Log",      interactive=False, lines=10, elem_classes="output-log")
                relatorio_out  = gr.Textbox(label="Relatório", interactive=False, lines=10, elem_classes="output-log")

                gr.HTML('<p class="sec">06 — Preview</p>')
                preview_gallery = gr.Gallery(label="", show_label=False, columns=3, height=300, object_fit="contain")

                with gr.Row(visible=False, elem_classes="btn-detectar") as painel_enviar_legenda:
                    opcoes_clipes = gr.Dropdown(choices=[], label="Escolha um clipe gerado para legendar:", scale=3)
                    btn_enviar_legenda = gr.Button("🎨 ENVIAR CLIP PARA LEGENDAS", scale=2)

                # Eventos — Corte
                btn_detectar.click(
                    fn=ao_detectar_pessoas,
                    inputs=[arquivo_video],
                    outputs=[log_deteccao, painel_rostos, galeria_rostos, pessoas_opcoes],
                )
                btn_analisar.click(
                    fn=ao_analisar,
                    inputs=[idioma, modelo, nicho, duracao_min, duracao_max, modo_offline],
                    outputs=[log_analise],
                )
                btn_processar.click(
                    fn=ao_processar,
                    inputs=[
                        pasta_saida, qualidade, perfil_processamento,
                        retomar_processamento, remover_pausas,
                        min_silencio_ms, margem_silencio_ms,
                        pessoas_opcoes, legendar_automaticamente,
                        aplicar_efeitos_virais,
                    ],
                    outputs=[log_processo, relatorio_out, preview_gallery, painel_enviar_legenda],
                )
                btn_cancelar.click(
                    fn=ao_cancelar_processo,
                    outputs=[log_processo],
                )
                btn_abrir_saida.click(
                    fn=abrir_pasta_export,
                    inputs=[pasta_saida],
                    outputs=[log_processo],
                )
                btn_abrir_logs.click(
                    fn=abrir_logs,
                    outputs=[log_processo],
                )
                # Nota: btn_enviar_legenda.click é registrado DEPOIS da Tab 2,
                # pois leg_video_select é definido lá. Ver bloco ao final da Tab 2.

            # ══════════════════════════════════════════════════════════════
            # TAB 2 — LEGENDAS ANIMADAS
            # ══════════════════════════════════════════════════════════════
            with gr.Tab("🎨  Legendas Animadas", id="tab_legendas"):

                gr.HTML('<p class="sec">01 — Importar Vídeo</p>')
                gr.Markdown("*Envie qualquer vídeo ou aponte para uma pasta com vídeos já cortados.*")

                leg_arquivo = gr.File(label="Upload direto de vídeo", file_types=["video"])

                gr.HTML('<p style="font-family:Space Mono,monospace;font-size:11px;color:var(--muted);text-align:center;margin:8px 0;">— ou —</p>')

                with gr.Row():
                    leg_pasta = gr.Textbox(
                        label="Pasta com vídeos",
                        value=os.path.join(os.path.expanduser("~"), "Desktop", "viral-clipes"),
                        scale=3,
                    )
                    btn_escanear = gr.Button("📂  ESCANEAR", scale=1, elem_classes="btn-detectar")

                leg_scan_log = gr.Textbox(label="", interactive=False, lines=4, elem_classes="output-log")
                leg_video_select = gr.Dropdown(
                    choices=[], value=None,
                    label="Selecione o vídeo da pasta:",
                )

                gr.HTML('<p class="sec">02 — SRT (Opcional)</p>')
                leg_srt_upload = gr.File(label="Upload de legenda .srt (Opcional, pula o Whisper)", file_types=[".srt"])

                gr.HTML('<p class="sec">03 — Transcrição</p>')
                with gr.Row():
                    leg_idioma = gr.Dropdown(
                        choices=list(IDIOMAS.keys()), value="Português",
                        label="Idioma", scale=1,
                    )
                    leg_modelo = gr.Dropdown(
                        choices=list(MODELOS_WHISPER.keys()),
                        value="small  — Rápido na GPU ⭐",
                        label="Modelo Whisper", scale=1,
                    )

                with gr.Row(elem_classes="btn-detectar"):
                    btn_obter_transcricao = gr.Button("🎙️  1. GERAR / CARREGAR TRANSCRIÇÃO", scale=1)

                leg_trans_log = gr.Textbox(label="Log da Transcrição", interactive=False, lines=4, elem_classes="output-log")

                with gr.Group(visible=False) as painel_tabela_leg:
                    gr.HTML('<p class="sec">Edição Manual das Legendas</p>')
                    gr.Markdown("*Ajuste o texto ou os tempos se houver algum erro de transcrição antes de renderizar.*")
                    leg_tabela = gr.Dataframe(
                        headers=["Início (s)", "Fim (s)", "Texto"],
                        datatype=["number", "number", "str"],
                        type="array",
                        col_count=3,
                        interactive=True,
                    )
                    with gr.Row():
                        btn_exportar_srt = gr.Button("💾 Exportar SRT", scale=1)
                        export_srt_log = gr.Textbox(label="", interactive=False, scale=2)

                with gr.Group(visible=False) as painel_render_leg:
                    gr.HTML('<p class="sec">04 — Template & Estilo</p>')

                    leg_template = gr.Dropdown(
                        choices=list(TEMPLATES_LEGENDA.values()),
                        value=list(TEMPLATES_LEGENDA.values())[1],  # palavra-vazada
                        label="Template de legenda",
                    )

                    with gr.Row():
                        leg_fonte = gr.Dropdown(
                            choices=["Padrão do template"] + list(FONTES_LEGENDA.keys()),
                            value="Padrão do template",
                            label="Fonte", scale=1,
                        )
                        leg_tamanho = gr.Slider(
                            minimum=24, maximum=300, step=4, value=0,
                            label="Tamanho (0 = padrão do template)", scale=1,
                        )

                    with gr.Row():
                        leg_cor_texto = gr.Textbox(label="Cor do texto", value="#FFFFFF", max_lines=1, scale=1)
                        leg_cor_destaque = gr.Textbox(label="Cor de destaque", value="#e8ff47", max_lines=1, scale=1)
                        leg_posicao = gr.Dropdown(
                            choices=list(POSICOES_LEGENDA.keys()),
                            value="Inferior (padrão)",
                            label="Posição", scale=1,
                        )

                    gr.HTML('<p class="sec">05 — Export & Render</p>')
                    leg_pasta_saida = gr.Textbox(
                        label="Pasta de saída (deixe vazio = mesma pasta do vídeo)",
                        value="",
                    )

                    gr.HTML('<div style="height:16px"></div>')
                    with gr.Row(elem_classes="btn-legendar"):
                        btn_renderizar = gr.Button("🎨  2. APLICAR LEGENDAS (RENDERIZAR)", scale=1)

                    gr.HTML('<p class="sec" style="margin-top:28px">06 — Resultado</p>')
                    leg_log = gr.Textbox(label="Log do Processamento", interactive=False, lines=8, elem_classes="output-log")

                    gr.HTML('<p class="sec">07 — Preview</p>')
                    leg_preview = gr.Gallery(label="", show_label=False, columns=2, height=400, object_fit="contain")

                gr.HTML('''<p style="font-family:Space Mono,monospace;font-size:10px;color:#555;margin-top:12px;text-align:center;">
                    Requer Node.js instalado. Na primeira vez, instala o Remotion automaticamente (~30s).<br>
                    🎵 Módulo de música com sincronização de batida — em breve.
                </p>''')

                # Eventos — Legendas
                btn_escanear.click(
                    fn=ao_escanear_pasta,
                    inputs=[leg_pasta],
                    outputs=[leg_video_select, leg_scan_log],
                )

                btn_obter_transcricao.click(
                    fn=ao_obter_transcricao,
                    inputs=[
                        leg_arquivo, leg_video_select,
                        leg_srt_upload,
                        leg_idioma, leg_modelo,
                    ],
                    outputs=[leg_trans_log, leg_tabela, painel_tabela_leg],
                ).then(
                    fn=lambda: gr.update(visible=True),
                    outputs=[painel_render_leg]
                )

                btn_exportar_srt.click(
                    fn=ao_exportar_legenda_srt,
                    inputs=[leg_arquivo, leg_video_select, leg_tabela, leg_pasta_saida],
                    outputs=[export_srt_log],
                )

                btn_renderizar.click(
                    fn=ao_renderizar_legendas,
                    inputs=[
                        leg_arquivo, leg_video_select,
                        leg_tabela,
                        leg_template,
                        leg_cor_texto, leg_cor_destaque, leg_posicao,
                        leg_pasta_saida,
                        leg_fonte, leg_tamanho,
                    ],
                    outputs=[leg_log, leg_preview],
                )

        # Ajuste tardio do binding de enviar legenda para evitar referência circular no Gradio
        btn_enviar_legenda.click(
            fn=lambda clip: (gr.Tabs(selected="tab_legendas"), clip),
            inputs=[opcoes_clipes],
            outputs=[tabs, leg_video_select],
        )

    return app


if __name__ == "__main__":
    print("🚀 Iniciando Viral Cutter v2...")
    print("📡 Abrindo interface local...")
    app = criar_interface()
    app.queue(default_concurrency_limit=1, max_size=2)
    pasta_export = os.path.join(os.path.expanduser("~"), "Desktop", "viral-clipes")
    os.makedirs(pasta_export, exist_ok=True)
    porta = escolher_porta()
    registrar_status(porta, "iniciando")
    print(f"⚡ Interface preparada em {time.perf_counter() - INICIO_APP:.1f}s")
    print(f"📝 Log: {ARQUIVO_LOG}")
    app.launch(
        server_name="127.0.0.1",
        server_port=porta,
        inbrowser=os.environ.get("VIRAL_CUTTER_NO_BROWSER") != "1",
        share=False,
        allowed_paths=[
            pasta_export,
            PASTA_BASE,
            pasta_dados(),
            os.path.expanduser("~"),
            "D:\\",
        ]
    )
