"""A aplicacao abre em janela propria, nunca numa aba de navegador."""

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTE = open(os.path.join(RAIZ, "app_desktop.py"), encoding="utf-8").read()


def test_gradio_never_opens_a_browser_tab():
    assert "inbrowser=False" in FONTE
    assert "inbrowser=True" not in FONTE


def test_server_is_bound_to_localhost_only():
    assert '"127.0.0.1"' in FONTE
    assert "0.0.0.0" not in FONTE
    assert "share=False" in FONTE


def test_window_waits_for_the_server_before_opening():
    """Abrir a janela antes do Gradio subir mostra erro de conexao ao usuario."""
    arvore = ast.parse(FONTE)
    corpo = next(
        n for n in arvore.body
        if isinstance(n, ast.FunctionDef) and n.name == "main"
    )
    ordem = [
        n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
        for n in ast.walk(corpo) if isinstance(n, ast.Call)
    ]
    assert "_esperar_servidor" in ordem
    assert "create_window" in ordem
    fonte_main = ast.get_source_segment(FONTE, corpo)
    assert fonte_main.index("_esperar_servidor") < fonte_main.index("create_window")


def test_window_never_opens_larger_than_the_screen():
    import app_desktop

    largura, altura = app_desktop._dimensoes_para_a_tela()
    assert largura >= app_desktop.LARGURA_MINIMA
    assert altura >= app_desktop.ALTURA_MINIMA
    assert largura <= app_desktop.LARGURA_PADRAO
    assert altura <= app_desktop.ALTURA_PADRAO


def test_minimum_size_fits_a_1366x768_laptop():
    """Criterio de release do projeto: o app tem de caber em 1366x768."""
    import app_desktop

    assert app_desktop.LARGURA_MINIMA <= 1366
    assert app_desktop.ALTURA_MINIMA <= 768 - 60  # barra de titulo + taskbar


def test_falls_back_to_the_browser_instead_of_not_opening():
    """Sem WebView2 na maquina, avisa e abre no navegador — nunca fica mudo."""
    assert "abrir_no_navegador" in FONTE
    assert "except ImportError" in FONTE


def test_bootstrap_is_not_duplicated():
    """interface.py ja cria o mutex; repetir aqui aborta o proprio import."""
    assert "garantir_instancia_unica" not in FONTE
    assert "except SystemExit" in FONTE


def test_packaging_points_at_the_desktop_entry_point():
    spec = open(os.path.join(RAIZ, "viral_cutter.spec"), encoding="utf-8").read()
    assert '["app_desktop.py"]' in spec
    assert "webview.platforms.winforms" in spec
