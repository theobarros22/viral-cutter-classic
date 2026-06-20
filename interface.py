"""
interface.py — Viral Cutter v2
-------------------------------
Interface simples e focada:
1. Upload do vídeo
2. Preview dos rostos → escolhe quem priorizar
3. Configura e processa
4. Clipes prontos organizados por podcast
"""

import os
import sys
import time
import logging
from runtime import (
    configurar_ambiente,
    configurar_logs,
    escolher_porta,
    garantir_instancia_unica,
    pasta_dados,
    registrar_status,
)

INICIO_APP = time.perf_counter()

# Mantém caminhos de recursos e temporários previsíveis no .py e no .exe.
PASTA_BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
os.chdir(PASTA_BASE)
configurar_ambiente()
ARQUIVO_LOG = configurar_logs()
if not garantir_instancia_unica():
    raise SystemExit("O Viral Cutter já está aberto.")

# Força UTF-8 no console — sem isso o .exe quebra ao imprimir emoji (cp1252)
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

# ── Estado global ─────────────────────────────────────────────────────────────
_estado = {
    "caminho_video": None,
    "pessoas":       [],
    "segmentos":     [],
}

# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800;900&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
:root {
    --bg:#000; --surface:#080808; --surface2:#0d0d0d;
    --border:rgba(255,255,255,.12); --accent:#c63200;
    --accent-bright:#ff4b0a; --text:#f5f5f2; --muted:#777;
}
body, .gradio-container {
    background-color:var(--bg) !important;
    background-image:linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),
      linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px) !important;
    background-size:84px 84px !important;
    color:var(--text) !important; font-family:'Archivo',Arial,sans-serif !important;
}
.gradio-container { max-width:1180px !important; margin:0 auto !important; padding:26px 32px 64px !important; }
.contain,.wrap,.panel,.form,.block { border-radius:0 !important; }
.app-header { min-height:150px; display:grid; grid-template-columns:1fr auto; align-items:end;
    gap:32px; margin-bottom:26px; padding:24px 0 30px; border-bottom:1px solid var(--border); text-align:left; }
.app-brand { font:600 .68rem 'IBM Plex Mono',monospace; color:var(--accent-bright);
    letter-spacing:.26em; text-transform:uppercase; }
.app-header h1 { font-size:clamp(2.8rem,6vw,5.4rem); line-height:.84; font-weight:900;
    color:#fff; letter-spacing:-.065em; margin:18px 0 12px; }
.app-header h1 span { color:var(--accent); }
.app-header p { font:500 .7rem 'IBM Plex Mono',monospace; color:var(--muted);
    text-transform:uppercase; letter-spacing:.18em; margin:0; }
.app-version { border:1px solid var(--border); padding:12px 16px; color:#aaa;
    font:500 .65rem 'IBM Plex Mono',monospace; letter-spacing:.12em; text-transform:uppercase; }
.sec { font:500 .68rem 'IBM Plex Mono',monospace; text-transform:uppercase;
    letter-spacing:.24em; color:var(--accent-bright); margin:28px 0 12px;
    padding:12px 0; border-top:1px solid var(--border); border-bottom:1px solid var(--border); }
.sec strong { color:#fff; margin-right:12px; }
.workflow-card { background:rgba(8,8,8,.94) !important; border:1px solid var(--border) !important;
    padding:18px !important; box-shadow:inset 3px 0 var(--accent); }
.pessoa-card { background:var(--surface); border:1px solid var(--border); border-radius:0;
    padding:12px; text-align:center; cursor:pointer; transition:all .15s; }
.pessoa-card:hover,.pessoa-card.ativa { border-color:var(--accent); background:rgba(198,50,0,.14); }
.pessoa-card img { width:100%; border-radius:0; margin-bottom:8px; }
.btn-detectar button,.btn-analisar button,.btn-processar button {
    font-family:'Archivo',sans-serif !important; font-weight:800 !important;
    letter-spacing:.08em !important; text-transform:uppercase !important;
    border-radius:0 !important; width:100% !important; cursor:pointer !important;
}
.btn-detectar button { background:transparent !important; color:#fff !important;
    border:1px solid var(--accent) !important; padding:13px 24px !important; }
.btn-analisar button { background:var(--surface2) !important; color:var(--accent-bright) !important;
    border:1px solid var(--accent) !important; padding:13px 24px !important; }
.btn-processar button { background:var(--accent) !important; color:#fff !important;
    border:1px solid var(--accent) !important; padding:17px 32px !important; font-size:1rem !important; }
.btn-detectar button:hover,.btn-analisar button:hover,.btn-processar button:hover {
    background:var(--accent-bright) !important; color:#fff !important;
}
label,.label-wrap span { color:#d6d6d2 !important; font-weight:600 !important; }
input,textarea,select,[data-testid="dropdown"] { background:#070707 !important; color:#f4f4f0 !important;
    border-color:var(--border) !important; border-radius:0 !important; }
.output-log textarea { font:400 .76rem 'IBM Plex Mono',monospace !important;
    background:#030303 !important; color:#ddd !important; border:1px solid var(--border) !important;
    min-height:170px !important; }
.output-log { border-left:2px solid var(--accent) !important; }
.gallery { background:#050505 !important; border-color:var(--border) !important; border-radius:0 !important; }
.prose,.prose p,.info { color:#8b8b86 !important; }
input[type=checkbox],.gr-slider input[type=range] { accent-color:var(--accent) !important; }
footer { display:none !important; }
@media(max-width:760px) {
    .gradio-container { padding:16px !important; }
    .app-header { grid-template-columns:1fr; min-height:auto; }
    .app-header h1 { font-size:3.2rem; }
    .app-version { justify-self:start; }
}
"""

# ── Funções ───────────────────────────────────────────────────────────────────

def ao_detectar_pessoas(arquivo_video):
    """Detecta rostos e exibe previews para o usuário escolher."""
    if arquivo_video is None:
        return "❌ Envie um vídeo primeiro.", gr.update(visible=False), [], gr.update(choices=[], value=[])

    caminho = arquivo_video.name if hasattr(arquivo_video, 'name') else arquivo_video
    _estado["caminho_video"] = caminho

    log_lines = []
    def cb(msg): log_lines.append(msg)

    try:
        from pipeline import etapa1_detectar_pessoas
        pessoas = etapa1_detectar_pessoas(caminho, progresso_callback=cb)
        _estado["pessoas"] = pessoas

        if not pessoas:
            return "\n".join(log_lines) + "\n⚠️ Nenhuma pessoa detectada.", gr.update(visible=False), [], gr.update(choices=[], value=[])

        # Monta galeria de previews
        previews = [(p["preview_path"], p["nome"]) for p in pessoas if "preview_path" in p]
        opcoes   = [p["nome"] for p in pessoas]

        return (
            "\n".join(log_lines),
            gr.update(visible=True),
            previews,
            gr.update(choices=opcoes, value=opcoes)  # marca todas por padrão
        )

    except Exception as e:
        import traceback
        logging.getLogger("ViralCutter.interface").exception("Erro ao detectar pessoas")
        return f"❌ Erro:\n{str(e)}\n{traceback.format_exc()}", gr.update(visible=False), [], gr.update(choices=[], value=[])


def ao_analisar(idioma_label, modelo_label, nicho_label, duracao_min, duracao_max, modo_offline):
    """Transcreve e identifica segmentos."""
    if not _estado.get("caminho_video"):
        return "❌ Detecte as pessoas primeiro."

    idioma = IDIOMAS.get(idioma_label, "pt")
    modelo = MODELOS_WHISPER.get(modelo_label, "small")
    nicho  = NICHOS.get(nicho_label, "podcast")

    log_lines = []
    def cb(msg): log_lines.append(msg)

    try:
        from pipeline import etapa2_analisar
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
    pasta_saida, qualidade_label,
    perfil_label,
    pessoas_selecionadas,
    retomar_processamento,
    remover_pausas,
    min_silencio_ms,
    margem_silencio_ms,
    progresso_callback=None
):
    """Processa os clipes com enquadramento inteligente."""
    if not _estado.get("caminho_video"):
        return "❌ Detecte as pessoas primeiro.", "", []
    if not _estado.get("segmentos") and not retomar_processamento:
        return "❌ Analise o vídeo primeiro.", "", []
    if not pasta_saida.strip():
        return "❌ Informe a pasta de destino.", "", []

    qualidade = QUALIDADES.get(qualidade_label, "1080p")
    perfil = PERFIS_PROCESSAMENTO.get(perfil_label, "equilibrado")

    # Converte nomes selecionados para IDs
    ids_priorizados = []
    for pessoa in _estado.get("pessoas", []):
        if pessoa["nome"] in (pessoas_selecionadas or []):
            ids_priorizados.append(pessoa["id"])

    log_lines = []
    def cb(msg): log_lines.append(msg)

    try:
        from pipeline import etapa3_processar
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
            progresso_callback=cb
        )

        relatorio = f"\n{'═'*45}\n"
        relatorio += f"  ✅ {len(resultados)} CLIPES GERADOS\n"
        relatorio += f"  📁 {pasta_saida}\n"
        relatorio += f"{'═'*45}\n\n"
        for i, r in enumerate(resultados, 1):
            relatorio += f"  [{i}] {r['titulo']}\n"
            relatorio += f"      ⏱️ {r['duracao']}s  |  ⭐ {r['score_viral']}/10\n"
            relatorio += f"      💡 {r['resumo']}\n\n"

        videos = [r["arquivo"] for r in resultados if os.path.exists(r["arquivo"])]

        return "\n".join(log_lines), relatorio, videos

    except Exception as e:
        import traceback
        return f"❌ Erro:\n{str(e)}\n{traceback.format_exc()}", "", []


# ── Interface ─────────────────────────────────────────────────────────────────

def criar_interface():
    with gr.Blocks(css=CSS, title="Viral Cutter v2.3.1") as app:

        gr.HTML("""
        <div class="app-header">
          <div>
            <div class="app-brand">Vollare Intelligence · Video Studio</div>
            <h1>VIRAL <span>CUTTER</span></h1>
            <p>Corte automático · enquadramento inteligente · processamento local</p>
          </div>
          <div class="app-version">Release 2.3.1 · RTX Ready</div>
        </div>
        """)

        # ── 01: Upload ────────────────────────────────────────────────────
        gr.HTML('<p class="sec"><strong>01</strong> Upload do vídeo</p>')
        with gr.Group(elem_classes="workflow-card"):
            arquivo_video = gr.File(label="Vídeo longo", file_types=["video"])
            with gr.Row(elem_classes="btn-detectar"):
                btn_detectar = gr.Button("DETECTAR PESSOAS", scale=1)
            log_deteccao = gr.Textbox(label="", interactive=False, lines=4, elem_classes="output-log")

        # ── 02: Preview dos rostos ────────────────────────────────────────
        with gr.Group(visible=False) as painel_rostos:
            gr.HTML('<p class="sec"><strong>02</strong> Escolha quem priorizar</p>')
            gr.Markdown("*Selecione as pessoas que devem ser priorizadas no enquadramento. Se nenhuma for selecionada, todas são consideradas.*")

            galeria_rostos = gr.Gallery(
                label="Pessoas detectadas",
                show_label=False,
                columns=4,
                height=220,
                object_fit="cover",
            )

            pessoas_opcoes = gr.CheckboxGroup(
                choices=[],
                value=[],
                label="✅ Marque quem priorizar:",
            )

        # ── 03: Configurações ─────────────────────────────────────────────
        gr.HTML('<p class="sec"><strong>03</strong> Transcrição e análise</p>')
        with gr.Row():
            idioma  = gr.Dropdown(choices=list(IDIOMAS.keys()),         value="Português",             label="Idioma")
            modelo  = gr.Dropdown(
                choices=list(MODELOS_WHISPER.keys()),
                value="base   — Muito rápido",
                label="Modelo Whisper",
                info="Base é recomendado para análise rápida; Small melhora a precisão.",
            )
            nicho   = gr.Dropdown(choices=list(NICHOS.keys()),          value="🎙️ Podcast",             label="Nicho")

        modo_offline = gr.Checkbox(
            label="📴 Modo offline — sem API (não consome créditos, usa algoritmo local)",
            value=False
        )
        gr.HTML('''<p style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#777;margin-top:-8px;">
            Modo online usa Claude API para análise semântica precisa (recomendado).
            Modo offline usa só Whisper — gratuito, funciona sem internet.
        </p>''')

        with gr.Row():
            duracao_min = gr.Slider(minimum=15, maximum=120, value=30, step=5, label="Duração mínima (s)")
            duracao_max = gr.Slider(minimum=30, maximum=180, value=90, step=5, label="Duração máxima (s)")

        with gr.Row(elem_classes="btn-analisar"):
            btn_analisar = gr.Button("TRANSCREVER E ANALISAR", scale=1)

        log_analise = gr.Textbox(label="", interactive=False, lines=6, elem_classes="output-log")

        # ── 04: Export ────────────────────────────────────────────────────
        gr.HTML('<p class="sec"><strong>04</strong> Exportação inteligente</p>')
        with gr.Row():
            pasta_saida = gr.Textbox(
                label="Pasta principal de export",
                value=os.path.join(os.path.expanduser("~"), "Desktop", "viral-clipes"),
                scale=3
            )
            qualidade = gr.Dropdown(
                choices=list(QUALIDADES.keys()),
                value="1080p — Full HD ⭐",
                label="Qualidade",
                scale=1
            )
            perfil_processamento = gr.Dropdown(
                choices=list(PERFIS_PROCESSAMENTO.keys()),
                value="Equilibrado — recomendado ⭐",
                label="Velocidade",
                scale=1
            )

        retomar_processamento = gr.Checkbox(
            label="Retomar automaticamente de onde parou",
            value=True,
            info="Ao reabrir, carregue o mesmo video, detecte as pessoas e clique em processar.",
        )

        remover_pausas = gr.Checkbox(
            label="Remover automaticamente pausas e silêncios internos",
            value=False,
            info="Ideal para vídeos de 3 a 4 minutos. Mantém uma pequena respiração entre as falas.",
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

        gr.HTML('<div style="height:16px"></div>')
        with gr.Row(elem_classes="btn-processar"):
            btn_processar = gr.Button("PROCESSAR VÍDEO", scale=1)

        # ── 05: Resultado ─────────────────────────────────────────────────
        gr.HTML('<p class="sec" style="margin-top:28px"><strong>05</strong> Progresso e resultado</p>')
        log_processo   = gr.Textbox(label="Log",      interactive=False, lines=10, elem_classes="output-log")
        relatorio_out  = gr.Textbox(label="Relatório", interactive=False, lines=10, elem_classes="output-log")

        gr.HTML('<p class="sec"><strong>06</strong> Preview dos clipes</p>')
        preview_gallery = gr.Gallery(label="", show_label=False, columns=3, height=300, object_fit="contain")

        # ── Eventos ───────────────────────────────────────────────────────
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
                pessoas_opcoes, retomar_processamento,
                remover_pausas, min_silencio_ms, margem_silencio_ms
            ],
            outputs=[log_processo, relatorio_out, preview_gallery],
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
        ]
    )
