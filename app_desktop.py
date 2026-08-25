"""
app_desktop.py
--------------
Ponto de entrada do Viral Cutter Classic como APLICATIVO DE JANELA.

O programa deixa de abrir numa aba do navegador. A interface Gradio continua
sendo a mesma (interface.py), mas agora e servida apenas em 127.0.0.1 e
exibida dentro de uma janela nativa do Windows (WebView2, via pywebview).

Por que envolver em vez de reescrever: a interface tem mais de 1300 linhas
testadas e em producao. Trocar a camada de exibicao nao mexe em nenhuma
regra de negocio — corte, enquadramento e retomada seguem identicos.

Se o WebView2 nao estiver disponivel na maquina, o app avisa e cai para o
navegador, em vez de simplesmente nao abrir.
"""

import os
import sys
import threading
import time

import runtime

TITULO_JANELA = "Viral Cutter Classic"
LARGURA_PADRAO = 1280
ALTURA_PADRAO = 800
# O usuario roda em notebook 1366x768: a janela precisa caber inteira nessa
# tela, senao os botoes do rodape ficam fora do alcance.
LARGURA_MINIMA = 1000
ALTURA_MINIMA = 620
TEMPO_LIMITE_SERVIDOR = 60.0


def _url_local(porta: int) -> str:
    return f"http://127.0.0.1:{porta}/"


def _esperar_servidor(porta: int, limite: float = TEMPO_LIMITE_SERVIDOR) -> bool:
    """Aguarda o Gradio aceitar conexao antes de abrir a janela.

    Sem isso a janela abre num erro de conexao enquanto o servidor ainda sobe
    (o Gradio leva alguns segundos para montar a interface).
    """
    import socket

    limite_final = time.monotonic() + limite
    while time.monotonic() < limite_final:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", porta)) == 0:
                return True
        time.sleep(0.2)
    return False


def _dimensoes_para_a_tela():
    """Nunca abre maior que a tela disponivel (notebooks 1366x768)."""
    largura, altura = LARGURA_PADRAO, ALTURA_PADRAO
    try:
        import ctypes

        usuario = ctypes.windll.user32
        usuario.SetProcessDPIAware()
        tela_w = usuario.GetSystemMetrics(0)
        tela_h = usuario.GetSystemMetrics(1)
        if tela_w and tela_h:
            largura = max(LARGURA_MINIMA, min(largura, tela_w - 40))
            altura = max(ALTURA_MINIMA, min(altura, tela_h - 80))
    except Exception:
        # Sem API de tela (outro SO, sessao remota): mantem o padrao.
        pass
    return largura, altura


def iniciar_servidor_gradio():
    """Sobe a interface Gradio local sem abrir navegador. Retorna a porta.

    O proprio `import interface` ja faz o bootstrap (PATH das ferramentas,
    logs e mutex de instancia unica). Repetir isso aqui faria o mutex existir
    duas vezes e o import abortaria com "o Viral Cutter ja esta aberto".
    """
    import interface
    from runtime import escolher_porta, registrar_status

    app = interface.criar_interface()
    app.queue(default_concurrency_limit=1, max_size=2)

    pasta_export = os.path.join(os.path.expanduser("~"), "Desktop", "viral-clipes")
    os.makedirs(pasta_export, exist_ok=True)
    porta = escolher_porta()
    registrar_status(porta, "iniciando")

    def servir():
        app.launch(
            server_name="127.0.0.1",
            server_port=porta,
            css=interface.CSS,
            head=interface.HEAD,
            inbrowser=False,          # a janela nativa e quem exibe
            share=False,
            quiet=True,
            prevent_thread_lock=True,
            allowed_paths=[
                pasta_export,
                interface.PASTA_BASE,
                runtime.pasta_dados(),
                os.path.expanduser("~"),
                "D:\\",
            ],
        )

    thread = threading.Thread(target=servir, daemon=True)
    thread.start()
    return porta, app


def abrir_no_navegador(porta: int) -> None:
    """Ultimo recurso quando nao ha WebView2 na maquina."""
    import webbrowser

    print(
        "   Janela nativa indisponivel (WebView2 ausente). "
        "Abrindo no navegador padrao."
    )
    webbrowser.open(_url_local(porta))
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass


def main() -> int:
    runtime.configurar_console_utf8()

    print(f"Iniciando {TITULO_JANELA}...")
    try:
        porta, _app = iniciar_servidor_gradio()
    except SystemExit as parada:
        # interface.py aborta assim quando o mutex de instancia unica ja existe.
        print(str(parada) or "O Viral Cutter ja esta aberto.")
        return 0

    if not _esperar_servidor(porta):
        print("A interface nao respondeu a tempo. Verifique o log e tente de novo.")
        return 1

    runtime.registrar_status(porta, "pronto")

    try:
        import webview
    except ImportError:
        abrir_no_navegador(porta)
        return 0

    largura, altura = _dimensoes_para_a_tela()
    webview.create_window(
        TITULO_JANELA,
        _url_local(porta),
        width=largura,
        height=altura,
        min_size=(LARGURA_MINIMA, ALTURA_MINIMA),
        background_color="#101014",
        text_select=True,
    )
    try:
        webview.start()
    except Exception as erro:
        print(f"   Falha ao abrir a janela nativa: {erro}")
        abrir_no_navegador(porta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
