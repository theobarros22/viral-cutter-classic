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
    "small  — Rápido na GPU (recomendado)": "small",
    "medium — Mais preciso":     "medium",
    "large  — Máxima precisão":  "large",
}
NICHOS = {
    "Podcast":   "podcast",
    "Geral":     "geral",
    "Casamento": "casamento",
    "Crime":     "crime",
    "Esporte":   "esporte",
    "Educação":  "educacao",
}
QUALIDADES = {
    "1080p — Full HD (recomendado)": "1080p",
    "720p  — Leve":       "720p",
    "4K    — Ultra HD":   "4k",
}
PERFIS_PROCESSAMENTO = {
    "Rápido — análise visual reduzida": "rapido",
    "Equilibrado — recomendado": "equilibrado",
    "Máxima qualidade — análise detalhada": "qualidade",
}
MODO_OFFLINE_PADRAO = not bool(os.environ.get("ANTHROPIC_API_KEY"))

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
:root {
    --primary-400: #edff86; --primary-500: #dfff3f; --primary-600: #c6e637;
    --primary-700: #a9c42c; --primary-800: #839820;
    --vc-bg: #07090c; --vc-surface: #0f1318; --vc-raised: #151a21;
    --vc-border: #252c36; --vc-border-strong: #394350;
    --vc-accent: #dfff3f; --vc-accent-hover: #edff86;
    --vc-cyan: #4de3d5; --vc-violet: #a78bfa;
    --vc-text: #f5f7fa; --vc-muted: #9aa5b3; --vc-subtle: #687383;
    --vc-radius: 14px; --vc-shadow: 0 18px 55px rgba(0, 0, 0, .28);
}

html { color-scheme: dark; background: var(--vc-bg); }
*, *::before, *::after { box-sizing: border-box; }
body, .gradio-container {
    background:
        radial-gradient(circle at 14% -8%, rgba(223,255,63,.09), transparent 30rem),
        radial-gradient(circle at 92% 18%, rgba(77,227,213,.055), transparent 26rem),
        var(--vc-bg) !important;
    color: var(--vc-text) !important;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif !important;
}
body { overflow-x: hidden; }
.gradio-container {
    width: 100% !important;
    min-width: 0 !important;
    max-width: 1180px !important;
    margin: 0 auto !important;
    padding: 32px clamp(16px, 3vw, 40px) 72px !important;
}

.app-header {
    position: relative; overflow: hidden; display: grid;
    grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: 32px;
    margin-bottom: 24px; padding: clamp(24px, 4vw, 44px);
    border: 1px solid var(--vc-border); border-radius: 22px;
    background: linear-gradient(135deg, rgba(21,26,33,.98), rgba(10,13,17,.96));
    box-shadow: var(--vc-shadow);
}
.app-header::after {
    content: ""; position: absolute; right: -80px; bottom: -110px;
    width: 290px; height: 290px; border: 1px solid rgba(223,255,63,.18);
    border-radius: 50%;
    box-shadow: 0 0 0 34px rgba(223,255,63,.025), 0 0 0 70px rgba(223,255,63,.018);
    pointer-events: none;
}
.brand-lockup { position: relative; z-index: 1; min-width: 0; max-width: 100%; }
.brand-kicker {
    display: flex; align-items: center; gap: 10px; margin: 0 0 16px;
    color: var(--vc-accent); font-size: .72rem; font-weight: 750;
    letter-spacing: .16em; text-transform: uppercase;
}
.brand-kicker::before {
    content: ""; width: 28px; height: 3px; border-radius: 999px;
    background: var(--vc-accent); box-shadow: 0 0 16px rgba(223,255,63,.35);
}
.app-header h1 {
    max-width: 760px; margin: 0; color: var(--vc-text);
    font-size: clamp(2.1rem, 5vw, 4.25rem); font-weight: 780;
    line-height: .96; letter-spacing: -.065em;
}
.app-header h1 span { color: var(--vc-accent); }
.app-header .hero-copy {
    max-width: 650px; margin: 18px 0 0; color: var(--vc-muted);
    font-size: clamp(.95rem, 1.8vw, 1.08rem); line-height: 1.65; overflow-wrap: anywhere;
}
.hero-meta {
    position: relative; z-index: 1; display: flex; flex-direction: column;
    align-items: flex-end; gap: 10px;
}
.status-pill {
    display: inline-flex; align-items: center; gap: 8px; min-height: 34px;
    padding: 7px 12px; border: 1px solid var(--vc-border); border-radius: 999px;
    background: rgba(7,9,12,.64); color: var(--vc-muted);
    font-size: .78rem; font-weight: 650; white-space: nowrap;
}
.status-pill::before {
    content: ""; width: 7px; height: 7px; border-radius: 50%;
    background: var(--vc-accent); box-shadow: 0 0 10px rgba(223,255,63,.6);
}

.gradio-container .tabs {
    overflow: hidden; border: 1px solid var(--vc-border) !important;
    border-radius: 18px !important; background: rgba(15,19,24,.82) !important;
    box-shadow: 0 14px 40px rgba(0,0,0,.2) !important;
}
.gradio-container .tab-container {
    gap: 8px !important; padding: 8px !important;
    border-bottom: 1px solid var(--vc-border) !important; background: #0b0e12 !important;
}
.gradio-container .tab-container button {
    min-height: 48px !important; padding: 0 20px !important;
    border: 1px solid transparent !important; border-radius: 10px !important;
    color: var(--vc-muted) !important; font-size: .9rem !important; font-weight: 700 !important;
    cursor: pointer !important;
    transition: color .18s ease, background .18s ease, border-color .18s ease !important;
}
.gradio-container .tab-container button:hover { color: var(--vc-text) !important; background: var(--vc-raised) !important; }
.gradio-container .tab-container button.selected,
.gradio-container .tab-container button[aria-selected="true"] {
    border-color: rgba(223,255,63,.28) !important;
    background: rgba(223,255,63,.1) !important; color: var(--vc-accent) !important;
}

.sec {
    display: flex; align-items: center; gap: 12px; margin: 36px 0 16px;
    color: var(--vc-text); font-size: .82rem; font-weight: 780;
    letter-spacing: .1em; text-transform: uppercase;
}
.sec::after {
    content: ""; flex: 1; height: 1px;
    background: linear-gradient(90deg, var(--vc-border-strong), transparent);
}
.gradio-container .block, .gradio-container .form, .gradio-container .panel {
    border-color: var(--vc-border) !important; border-radius: var(--vc-radius) !important;
}
.gradio-container .form, .gradio-container .panel { background: rgba(15,19,24,.72) !important; }
.gradio-container label, .gradio-container .label-wrap { color: var(--vc-text) !important; font-weight: 650 !important; }
.gradio-container input, .gradio-container textarea, .gradio-container select { color: var(--vc-text) !important; }
.gradio-container button {
    min-height: 44px; cursor: pointer !important;
    transition: transform .16s ease, background .18s ease, border-color .18s ease, color .18s ease !important;
}
.gradio-container button:active { transform: translateY(1px); }
.gradio-container button:focus-visible, .gradio-container input:focus-visible,
.gradio-container textarea:focus-visible, .gradio-container [role="tab"]:focus-visible {
    outline: 3px solid rgba(223,255,63,.34) !important; outline-offset: 2px !important;
}

.pessoa-card {
    padding: 12px; border: 1px solid var(--vc-border); border-radius: var(--vc-radius);
    background: var(--vc-surface); text-align: center; cursor: pointer;
    transition: border-color .18s ease, background .18s ease;
}
.pessoa-card:hover { border-color: var(--vc-accent); }
.pessoa-card.ativa { border-color: var(--vc-accent); background: rgba(223,255,63,.08); }
.pessoa-card img { width: 100%; margin-bottom: 8px; border-radius: 9px; }
.pessoa-card span { color: var(--vc-text); font-size: 12px; }

.btn-detectar button, .btn-analisar button, .btn-processar button, .btn-legendar button {
    width: 100% !important; min-height: 50px !important; padding: 12px 24px !important;
    border-radius: 12px !important; font-family: inherit !important;
    font-weight: 780 !important; letter-spacing: .025em !important;
}
.btn-detectar button {
    border: 1px solid rgba(77,227,213,.35) !important;
    background: rgba(77,227,213,.1) !important; color: var(--vc-cyan) !important;
}
.btn-detectar button:hover { background: rgba(77,227,213,.17) !important; }
.btn-analisar button {
    border: 1px solid rgba(167,139,250,.38) !important;
    background: rgba(167,139,250,.1) !important; color: #c4b5fd !important;
}
.btn-analisar button:hover { background: rgba(167,139,250,.18) !important; }
.btn-processar button {
    border: 1px solid var(--vc-accent) !important; background: var(--vc-accent) !important;
    color: #111600 !important; box-shadow: 0 10px 30px rgba(223,255,63,.13) !important;
}
.btn-processar button:hover { background: var(--vc-accent-hover) !important; }
.btn-legendar button {
    border: 1px solid rgba(167,139,250,.5) !important;
    background: #7c5ce0 !important; color: #fff !important;
}
.btn-legendar button:hover { background: #8b6bea !important; }

.output-log textarea {
    min-height: 150px !important; border: 1px solid #22352b !important;
    background: #080c0a !important; color: #9bf5b5 !important;
    font-family: "Cascadia Code", "SFMono-Regular", Consolas, monospace !important;
    font-size: .78rem !important; line-height: 1.6 !important;
}
input[type=checkbox] { accent-color: var(--vc-accent) !important; }
.gr-slider input[type=range] { accent-color: var(--vc-accent) !important; }
.helper-note { margin: 18px 0 0; color: var(--vc-subtle); font-size: .78rem; line-height: 1.55; text-align: center; }
/* Classic 2.3.2: desktop workspace constrained to the viewport. */
html, body { width: 100%; height: 100%; overflow: hidden; }
body { margin: 0 !important; }
.gradio-container {
    width: 100% !important; height: 100dvh !important; max-width: none !important;
    margin: 0 !important; padding: 0 12px 10px !important; overflow: hidden !important;
}
.classic-topbar {
    height: 50px; display: flex; align-items: center; justify-content: space-between;
    gap: 16px; padding: 0 14px; border-bottom: 1px solid var(--vc-border);
    background: rgba(10,13,17,.96); color: var(--vc-text);
}
.classic-brand { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.classic-brand strong { color: var(--vc-accent); font-size: 1rem; }
.classic-brand span, .classic-status { color: var(--vc-muted); font-size: .75rem; white-space: nowrap; }
.classic-status { display: inline-flex; align-items: center; gap: 7px; }
.classic-status::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--vc-accent); }
.gradio-container .tabs {
    height: calc(100dvh - 60px) !important; min-height: 0 !important;
    display: flex !important; flex-direction: column !important; border-radius: 12px !important;
}
.gradio-container .tab-container { flex: 0 0 44px; padding: 4px 8px !important; }
.gradio-container .tab-container button { min-height: 34px !important; padding: 0 14px !important; }
.gradio-container .tabitem { flex: 1 1 auto !important; min-height: 0 !important; overflow: auto !important; }
.classic-shell {
    display: grid !important;
    grid-template-columns: minmax(170px, .72fr) minmax(520px, 3.1fr) minmax(290px, 1.35fr) !important;
    gap: 10px !important;
    height: calc(100dvh - 196px); max-height: calc(100dvh - 196px);
    min-height: 360px; padding: 10px !important; overflow: hidden !important;
}
.classic-shell > .workflow-panel, .classic-shell > .workspace-panel, .classic-shell > .inspector-panel {
    min-width: 0 !important; min-height: 0 !important; margin: 0 !important;
    border: 1px solid var(--vc-border); border-radius: 12px; background: rgba(15,19,24,.72);
}
.workflow-panel { overflow: hidden !important; padding: 12px !important; }
.workspace-panel {
    overflow-y: auto !important; overflow-x: hidden !important; padding: 0 12px 14px !important;
    scrollbar-gutter: stable; overscroll-behavior: contain; scrollbar-width: auto;
    scrollbar-color: var(--vc-border-strong) var(--vc-surface);
}
.inspector-panel { display: flex !important; flex-direction: column !important; overflow: hidden !important; padding: 0 !important; }
.inspector-scroll {
    flex: 1 1 auto !important; min-height: 0 !important; overflow-y: auto !important; padding: 0 12px 12px !important;
    scrollbar-gutter: stable; overscroll-behavior: contain; scrollbar-width: auto;
    scrollbar-color: var(--vc-border-strong) var(--vc-surface);
}
.workspace-panel::-webkit-scrollbar, .inspector-scroll::-webkit-scrollbar { width: 12px; }
.workspace-panel::-webkit-scrollbar-track, .inspector-scroll::-webkit-scrollbar-track {
    background: var(--vc-surface); border-radius: 999px;
}
.workspace-panel::-webkit-scrollbar-thumb, .inspector-scroll::-webkit-scrollbar-thumb {
    min-height: 44px; border: 3px solid var(--vc-surface); border-radius: 999px;
    background: var(--vc-border-strong);
}
.workspace-panel::-webkit-scrollbar-thumb:hover, .inspector-scroll::-webkit-scrollbar-thumb:hover {
    background: var(--vc-muted);
}
.process-actions {
    flex: 0 0 auto !important; margin: 0 !important; padding: 10px !important;
    border-top: 1px solid var(--vc-border); background: #0b0e12; z-index: 3;
}
.workflow-title { margin: 2px 0 14px; color: var(--vc-muted); font-size: .68rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
.workflow-step { display: grid; grid-template-columns: 24px 1fr; gap: 8px; align-items: center; padding: 8px 0; color: var(--vc-muted); font-size: .76rem; border-bottom: 1px solid rgba(57,67,80,.45); }
.workflow-step b { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 7px; background: rgba(223,255,63,.09); color: var(--vc-accent); font-size: .66rem; }
.classic-shell .sec { margin: 16px 0 10px; font-size: .72rem; }
.classic-shell .output-log textarea { min-height: 92px !important; max-height: 150px !important; overflow-y: auto !important; }
.classic-shell .btn-processar button { min-height: 48px !important; }

@media (max-width: 1200px) {
    .classic-shell { grid-template-columns: 92px minmax(340px, 1fr) minmax(240px, 300px) !important; gap: 8px !important; }
    .workflow-panel { padding: 8px !important; }
    .workflow-title { font-size: .6rem; }
    .workflow-step { grid-template-columns: 22px 1fr; gap: 5px; font-size: .66rem; }
}

@media (max-width: 760px) {
    .gradio-container { padding: 0 8px 8px !important; }
    .gradio-container .main, .gradio-container .wrap, .gradio-container .contain { min-width: 0 !important; }
    .app-header { grid-template-columns: 1fr; gap: 22px; padding: 24px 20px; border-radius: 16px; }
    .app-header h1 { font-size: clamp(2.25rem, 14vw, 3.35rem); }
    .hero-meta { align-items: flex-start; flex-direction: row; flex-wrap: wrap; }
    .gradio-container .tabs { border-radius: 14px !important; }
    .gradio-container .tab-container { overflow-x: auto !important; }
    .gradio-container .tab-container button { min-width: max-content; }
    .sec { margin-top: 28px; font-size: .76rem; letter-spacing: .06em; }
}
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important;
    }
}
"""

# O CSS injetado pelo Gradio é escopado dentro de ``.contain`` e não alcança
# o contêiner externo ``.main``. Esta regra precisa ficar no <head> global.
HEAD = """
<style>
@media (max-width: 760px) {
    .gradio-container .main {
        padding-left: 0 !important;
        padding-right: 0 !important;
    }
}
</style>
"""

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — CORTE VIRAL (funções)
# ══════════════════════════════════════════════════════════════════════════════

def ao_baixar_link(url):
    """Baixa vídeo de um link (YouTube etc.) e coloca no campo de upload."""
    if not url or not str(url).strip():
        return "❌ Cole um link primeiro.", gr.update()

    logs = []
    def cb(msg):
        logs.append(msg)

    try:
        from download_video import baixar_video
        caminho = baixar_video(str(url).strip(), progresso_callback=cb)
        logs.append("👉 Agora clique em DETECTAR PESSOAS.")
        return "\n".join(logs), gr.update(value=caminho)
    except ImportError:
        return (
            "❌ yt-dlp não instalado. No CMD:\n"
            "   venv311\\Scripts\\pip install yt-dlp",
            gr.update(),
        )
    except Exception as e:
        return "\n".join(logs) + f"\n❌ Erro no download: {e}", gr.update()


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
    efeito_legenda=False, efeito_zoom=False, efeito_sfx=False,
    aplicar_hook=False,
):
    # O checkbox "legendas automáticas" ativa o mesmo efeito de legendas
    # da etapa 4 (antes ele não estava ligado a nada e não fazia nada).
    efeito_legenda = bool(efeito_legenda or aplicar_legendas_auto)
    # Etapa 4 roda se qualquer um dos três efeitos estiver marcado
    usar_efeitos_virais = bool(efeito_legenda or efeito_zoom or efeito_sfx)

    # Retorno de erro precisa ter a MESMA aridade dos outputs (5 valores):
    # log, relatório, galeria, painel (só visibilidade) e dropdown de clipes.
    def _erro(msg):
        return msg, "", [], gr.update(visible=False), gr.update(choices=[], value=None)

    if not _estado.get("caminho_video"):
        return _erro("❌ Detecte as pessoas primeiro.")
    if not _estado.get("segmentos") and not retomar_processamento:
        return _erro("❌ Analise o vídeo primeiro.")
    if not pasta_saida or not pasta_saida.strip():
        return _erro("❌ Informe a pasta de destino.")

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
            aplicar_hook=aplicar_hook,
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
                aplicar_legenda=bool(efeito_legenda),
                aplicar_zoom=bool(efeito_zoom),
                aplicar_sfx=bool(efeito_sfx),
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
            # Row (painel) só aceita visibilidade; as opções vão no Dropdown
            gr.update(visible=True),
            gr.update(choices=videos, value=videos[0] if videos else None),
        )

    except Exception as e:
        import traceback
        return (
            f"❌ Erro:\n{str(e)}\n{traceback.format_exc()}",
            "", [],
            gr.update(visible=False),
            gr.update(choices=[], value=None),
        )


def ao_processar_automatico(
    producao_auto,
    pasta_saida, qualidade_label, perfil_label,
    retomar_processamento, remover_pausas,
    min_silencio_ms, margem_silencio_ms,
    pessoas_selecionadas, aplicar_legendas_auto,
    efeito_legenda=False, efeito_zoom=False, efeito_sfx=False,
    aplicar_hook=False,
):
    """
    PRODUÇÃO AUTOMÁTICA: encadeada após TRANSCREVER E ANALISAR.
    Com o modo automático LIGADO e a análise bem-sucedida, dispara o
    processamento completo sem o usuário clicar em PROCESSAR VÍDEO.
    Com o modo DESLIGADO (ou análise sem segmentos), não faz nada —
    devolve updates vazios para não mexer na tela.
    """
    sem_acao = (gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
    if not producao_auto:
        return sem_acao
    if not _estado.get("segmentos"):
        # Análise falhou ou não gerou segmentos — não inicia produção
        return sem_acao
    return ao_processar(
        pasta_saida, qualidade_label, perfil_label,
        retomar_processamento, remover_pausas,
        min_silencio_ms, margem_silencio_ms,
        pessoas_selecionadas, aplicar_legendas_auto,
        efeito_legenda, efeito_zoom, efeito_sfx,
        aplicar_hook,
    )


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
            # Se a extração falhar, transcreve o vídeo direto em vez de
            # tentar abrir um WAV que não existe (erro confuso pro usuário).
            alvo_transcricao = (
                wav_temp if _extrair_audio_wav(caminho_video, wav_temp)
                else caminho_video
            )
            if alvo_transcricao == caminho_video:
                log("⚠️ Falha ao extrair áudio — transcrevendo o vídeo diretamente.")

            log("📝 Transcrevendo... (pode demorar)")
            resultado = modelo.transcribe(
                alvo_transcricao, language=idioma, verbose=False,
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
    with gr.Blocks(title="Viral Cutter v2") as app:

        gr.HTML("""
        <div class="classic-topbar">
            <div class="classic-brand">
                <strong>Viral Cutter Classic</strong>
                <span>2.3.2</span>
            </div>
            <span class="classic-status">Processamento local</span>
        </div>
        """)

        with gr.Tabs() as tabs:

            # ══════════════════════════════════════════════════════════════
            # TAB 1 — CORTE VIRAL
            # ══════════════════════════════════════════════════════════════
            with gr.Tab("Corte Viral", id="tab_corte"):
                with gr.Row(elem_classes="classic-shell"):
                    with gr.Column(scale=1, min_width=112, elem_classes="workflow-panel"):
                        gr.HTML("""
                        <nav aria-label="Etapas do fluxo">
                            <p class="workflow-title">Fluxo de produção</p>
                            <div class="workflow-step"><b>01</b><span>Importar vídeo</span></div>
                            <div class="workflow-step"><b>02</b><span>Detectar pessoas</span></div>
                            <div class="workflow-step"><b>03</b><span>Analisar conteúdo</span></div>
                            <div class="workflow-step"><b>04</b><span>Configurar export</span></div>
                            <div class="workflow-step"><b>05</b><span>Processar cortes</span></div>
                            <div class="workflow-step"><b>06</b><span>Revisar resultado</span></div>
                        </nav>
                        """)

                    with gr.Column(scale=4, min_width=470, elem_classes="workspace-panel"):
                        gr.HTML('<p class="sec">01 — Upload do Vídeo</p>')
                        arquivo_video = gr.File(label="Vídeo longo", file_types=["video"])
                        gr.HTML('<p style="font-size:11px;color:var(--vc-muted);text-align:center;margin:5px 0;">— ou —</p>')
                        with gr.Row():
                            url_video = gr.Textbox(
                                label="Link do vídeo (YouTube etc.)",
                                placeholder="https://www.youtube.com/watch?v=...",
                                scale=4,
                            )
                            btn_baixar = gr.Button("⬇️ BAIXAR", scale=1)
                        gr.Markdown("*Baixe apenas vídeos seus ou com direito de uso. Requer yt-dlp instalado.*")
                        with gr.Row(elem_classes="btn-detectar"):
                            btn_detectar = gr.Button("DETECTAR PESSOAS", scale=1)
                        log_deteccao = gr.Textbox(label="", interactive=False, lines=3, elem_classes="output-log")

                        with gr.Group(visible=False) as painel_rostos:
                            gr.HTML('<p class="sec">02 — Escolha Quem Priorizar</p>')
                            gr.Markdown("*Selecione as pessoas que devem ser priorizadas no enquadramento.*")
                            galeria_rostos = gr.Gallery(
                                label="Pessoas detectadas", show_label=False,
                                columns=4, height=180, object_fit="cover",
                            )
                            pessoas_opcoes = gr.CheckboxGroup(
                                choices=[], value=[], label="✅ Marque quem priorizar:",
                            )

                        gr.HTML('<p class="sec">03 — Transcrição & Análise</p>')
                        with gr.Row():
                            idioma = gr.Dropdown(choices=list(IDIOMAS.keys()), value="Português", label="Idioma")
                            modelo = gr.Dropdown(
                                choices=list(MODELOS_WHISPER.keys()),
                                value="small  — Rápido na GPU (recomendado)",
                                label="Modelo Whisper",
                            )
                            nicho = gr.Dropdown(choices=list(NICHOS.keys()), value="Podcast", label="Nicho")
                        modo_offline = gr.Checkbox(
                            label="Modo offline — sem API (não consome créditos)",
                            value=MODO_OFFLINE_PADRAO,
                            info="Ativado automaticamente quando a chave da API não está configurada.",
                        )
                        producao_automatica = gr.Checkbox(
                            label="🚀 Produção automática — processar direto após a análise",
                            value=False,
                            info="Ao terminar a análise, inicia o processamento com as opções do inspector.",
                        )
                        with gr.Row():
                            duracao_min = gr.Slider(minimum=15, maximum=120, value=30, step=5, label="Duração mínima (s)")
                            duracao_max = gr.Slider(minimum=30, maximum=180, value=90, step=5, label="Duração máxima (s)")
                        with gr.Row(elem_classes="btn-analisar"):
                            btn_analisar = gr.Button("TRANSCREVER E ANALISAR", scale=1)
                        log_analise = gr.Textbox(label="", interactive=False, lines=4, elem_classes="output-log")

                        gr.HTML('<p class="sec">05 — Resultado & Preview</p>')
                        with gr.Row():
                            btn_abrir_saida = gr.Button("Abrir pasta de saída", scale=1)
                            btn_abrir_logs = gr.Button("Abrir pasta de logs", scale=1)
                        log_processo = gr.Textbox(label="Log", interactive=False, lines=5, elem_classes="output-log")
                        relatorio_out = gr.Textbox(label="Relatório", interactive=False, lines=5, elem_classes="output-log")
                        preview_gallery = gr.Gallery(label="", show_label=False, columns=3, height=250, object_fit="contain")
                        with gr.Row(visible=False, elem_classes="btn-detectar") as painel_enviar_legenda:
                            opcoes_clipes = gr.Dropdown(
                                choices=[], label="Escolha um clipe gerado para legendar:", scale=3,
                            )
                            btn_enviar_legenda = gr.Button("ENVIAR CLIPE PARA LEGENDAS", scale=2)

                    with gr.Column(scale=2, min_width=270, elem_classes="inspector-panel"):
                        with gr.Group(elem_classes="inspector-scroll"):
                            gr.HTML('<p class="sec">04 — Configurações</p>')
                            pasta_saida = gr.Textbox(
                                label="Pasta de export",
                                value=os.path.join(os.path.expanduser("~"), "Desktop", "viral-clipes"),
                            )
                            qualidade = gr.Dropdown(
                                choices=list(QUALIDADES.keys()),
                                value="1080p — Full HD (recomendado)",
                                label="Qualidade",
                            )
                            perfil_processamento = gr.Dropdown(
                                choices=list(PERFIS_PROCESSAMENTO.keys()),
                                value="Equilibrado — recomendado",
                                label="Velocidade",
                            )
                            retomar_processamento = gr.Checkbox(
                                label="Retomar automaticamente de onde parou",
                                value=True,
                                info="Ao reabrir, carregue o mesmo vídeo, escolha quem priorizar e processe.",
                            )
                            remover_pausas = gr.Checkbox(
                                label="Remover pausas e silêncios internos",
                                value=False,
                                info="Ideal para vídeos falados. Preserva uma pequena respiração.",
                            )
                            hook_automatico = gr.Checkbox(
                                label="Hook automático (cold open)",
                                value=False,
                                info="Abre o clipe com a frase de maior impacto. Requer análise com IA.",
                            )
                            min_silencio_ms = gr.Slider(
                                minimum=300, maximum=2000, value=700, step=100,
                                label="Pausa mínima para remover (ms)",
                            )
                            margem_silencio_ms = gr.Slider(
                                minimum=0, maximum=300, value=120, step=20,
                                label="Respiração preservada (ms)",
                            )
                            legendar_automaticamente = gr.Checkbox(
                                label="Aplicar legendas automáticas",
                                value=False,
                                info="Equivale a marcar Legendas ASS.",
                            )
                            gr.HTML('<p class="sec" style="margin-bottom:4px">Efeitos virais</p>')
                            efeito_legenda = gr.Checkbox(
                                label="Legendas ASS", value=False,
                                info="Palavra por palavra, pop-up e karaokê.",
                            )
                            efeito_zoom = gr.Checkbox(
                                label="Zoom dinâmico", value=False,
                                info="Zoom nos momentos de ênfase.",
                            )
                            efeito_sfx = gr.Checkbox(
                                label="Efeitos sonoros (SFX)", value=False,
                                info="Efeitos sonoros automáticos.",
                            )

                        with gr.Row(elem_classes="process-actions"):
                            btn_processar = gr.Button(
                                "PROCESSAR VÍDEO", scale=3, variant="primary", elem_classes="btn-processar",
                            )
                            btn_cancelar = gr.Button("CANCELAR", scale=1, variant="stop")
                # Eventos — Corte
                btn_baixar.click(
                    fn=ao_baixar_link,
                    inputs=[url_video],
                    outputs=[log_deteccao, arquivo_video],
                )
                btn_detectar.click(
                    fn=ao_detectar_pessoas,
                    inputs=[arquivo_video],
                    outputs=[log_deteccao, painel_rostos, galeria_rostos, pessoas_opcoes],
                )
                btn_analisar.click(
                    fn=ao_analisar,
                    inputs=[idioma, modelo, nicho, duracao_min, duracao_max, modo_offline],
                    outputs=[log_analise],
                ).then(
                    # PRODUÇÃO AUTOMÁTICA: encadeia o processamento logo após
                    # a análise quando o checkbox está marcado. Com ele
                    # desmarcado, a função devolve updates vazios (no-op).
                    fn=ao_processar_automatico,
                    inputs=[
                        producao_automatica,
                        pasta_saida, qualidade, perfil_processamento,
                        retomar_processamento, remover_pausas,
                        min_silencio_ms, margem_silencio_ms,
                        pessoas_opcoes, legendar_automaticamente,
                        efeito_legenda, efeito_zoom, efeito_sfx, hook_automatico,
                    ],
                    outputs=[log_processo, relatorio_out, preview_gallery, painel_enviar_legenda, opcoes_clipes],
                )
                btn_processar.click(
                    fn=ao_processar,
                    inputs=[
                        pasta_saida, qualidade, perfil_processamento,
                        retomar_processamento, remover_pausas,
                        min_silencio_ms, margem_silencio_ms,
                        pessoas_opcoes, legendar_automaticamente,
                        efeito_legenda, efeito_zoom, efeito_sfx, hook_automatico,
                    ],
                    outputs=[log_processo, relatorio_out, preview_gallery, painel_enviar_legenda, opcoes_clipes],
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
            with gr.Tab("Legendas Animadas", id="tab_legendas"):

                gr.HTML('<p class="sec">01 — Importar Vídeo</p>')
                gr.Markdown("*Envie qualquer vídeo ou aponte para uma pasta com vídeos já cortados.*")

                leg_arquivo = gr.File(label="Upload direto de vídeo", file_types=["video"])

                gr.HTML('<p style="font-family:Space Mono,monospace;font-size:11px;color:var(--vc-muted);text-align:center;margin:8px 0;">— ou —</p>')

                with gr.Row():
                    leg_pasta = gr.Textbox(
                        label="Pasta com vídeos",
                        value=os.path.join(os.path.expanduser("~"), "Desktop", "viral-clipes"),
                        scale=3,
                    )
                    btn_escanear = gr.Button("ESCANEAR", scale=1, elem_classes="btn-detectar")

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
                        value="small  — Rápido na GPU (recomendado)",
                        label="Modelo Whisper", scale=1,
                    )

                with gr.Row(elem_classes="btn-detectar"):
                    btn_obter_transcricao = gr.Button("1. GERAR OU CARREGAR TRANSCRIÇÃO", scale=1)

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
                        btn_exportar_srt = gr.Button("Exportar SRT", scale=1)
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
                        btn_renderizar = gr.Button("2. APLICAR LEGENDAS E RENDERIZAR", scale=1)

                    gr.HTML('<p class="sec" style="margin-top:28px">06 — Resultado</p>')
                    leg_log = gr.Textbox(label="Log do Processamento", interactive=False, lines=8, elem_classes="output-log")

                    gr.HTML('<p class="sec">07 — Preview</p>')
                    leg_preview = gr.Gallery(label="", show_label=False, columns=2, height=400, object_fit="contain")

                gr.HTML('''<p class="helper-note">
                    Requer Node.js instalado. Na primeira vez, instala o Remotion automaticamente (~30s).<br>
                    Módulo de música com sincronização de batida — em breve.
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
        css=CSS,
        head=HEAD,
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
