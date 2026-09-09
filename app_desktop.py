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

Se o WebView2 nao estiver disponivel, o app diz o que falta e para. Cair para
o navegador entregaria um produto diferente sem avisar: sem a janela nativa o
arrastar-e-soltar perde o caminho real do arquivo.
"""

import json
import logging
import os
import sys
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

    # `prevent_thread_lock=True` ja faz o Gradio servir numa thread propria e
    # devolver o controle. Envolver isso numa thread nossa quebrava o start no
    # executavel: o launch comecava (telemetria no log) e morria em silencio.
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
            *runtime.discos_prontos(),
        ],
    )
    return porta, app


def _fechar_servidor_gradio(app) -> None:
    """Libera a porta e o mutex quando a janela nativa e fechada."""
    try:
        app.close()
    except Exception as erro:
        logging.getLogger("ViralCutter").warning(
            "Falha ao encerrar o servidor local: %s", erro
        )


MSG_SEM_JANELA = (
    "Nao foi possivel abrir a janela do Viral Cutter.\n\n"
    "Falta o WebView2 Runtime nesta maquina. Baixe em:\n"
    "https://developer.microsoft.com/microsoft-edge/webview2/\n\n"
    "O programa nao cai para o navegador de proposito: fora da janela nativa\n"
    "o arrastar-e-soltar perde o caminho real do arquivo, e um podcast de\n"
    "12 GB passaria a ser copiado por upload em vez de lido direto do disco."
)


def avisar_sem_janela(erro: str = "") -> None:
    """Informa por que o app nao abriu, em vez de degradar em silencio."""
    detalhe = f"\n\nDetalhe tecnico: {erro}" if erro else ""
    logging.getLogger("ViralCutter").error("%s%s", MSG_SEM_JANELA, detalhe)
    print(MSG_SEM_JANELA + detalhe)
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0, MSG_SEM_JANELA + detalhe, "Viral Cutter Classic", 0x10
        )
    except Exception:
        pass


def _atualizar_zona(janela, texto: str, classe: str) -> None:
    """Escreve o retorno do arraste na propria zona, sem passar pelo Gradio."""
    seguro = json.dumps(texto)
    janela.run_js(
        f"""
        var zona = document.querySelector('#vc-dropzone');
        if (zona) {{
            zona.className = {json.dumps(classe)};
            var alvo = zona.querySelector('.vc-dropzone-arquivo');
            if (alvo) alvo.textContent = {seguro};
        }}
        """
    )


def conectar_arrastar_soltar(janela) -> None:
    """Liga o arrastar-e-soltar nativo da janela.

    O WebView2 entrega o caminho real do arquivo solto (`pywebviewFullPath`), o
    que a File API do navegador esconde de proposito. Com ele o video e lido
    direto do disco: um podcast de 12 GB entra na hora, em vez de subir por
    upload e ser copiado duas vezes.
    """
    import interface
    from webview.dom import DOMEventHandler

    def ao_soltar(evento):
        arquivos = ((evento or {}).get("dataTransfer") or {}).get("files") or []
        for arquivo in arquivos:
            caminho = (arquivo or {}).get("pywebviewFullPath")
            if caminho and os.path.isfile(caminho):
                interface.registrar_video_arrastado(caminho)
                _atualizar_zona(janela, os.path.basename(caminho), "vc-carregado")
                return
        _atualizar_zona(janela, "Solte um arquivo de video.", "")

    def registrar(_=None):
        # A zona so existe depois que o Gradio monta a interface, o que acontece
        # bem depois do `loaded` da pagina. Por isso a espera ativa.
        limite = time.monotonic() + 30.0
        while time.monotonic() < limite:
            zona = janela.dom.get_element("#vc-dropzone")
            if zona is not None:
                # Sem cancelar o `dragover` o navegador recusa o drop. O
                # preventDefault roda em JS na hora; o debounce so evita que
                # cada pixel de arrasto vire uma chamada ao Python.
                zona.on("dragover", DOMEventHandler(lambda _e: None, prevent_default=True, debounce=250))
                zona.on("drop", DOMEventHandler(ao_soltar, prevent_default=True))
                return
            time.sleep(0.5)
        logging.getLogger("ViralCutter").warning(
            "Zona de arraste nao apareceu; o arrastar-e-soltar ficou desligado."
        )

    janela.events.loaded += registrar


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
    except ImportError as erro:
        avisar_sem_janela(str(erro))
        return 1

    largura, altura = _dimensoes_para_a_tela()
    janela = webview.create_window(
        TITULO_JANELA,
        _url_local(porta),
        width=largura,
        height=altura,
        min_size=(LARGURA_MINIMA, ALTURA_MINIMA),
        background_color="#101014",
        text_select=True,
    )
    conectar_arrastar_soltar(janela)
    try:
        webview.start()
    except Exception as erro:
        avisar_sem_janela(str(erro))
        return 1
    _fechar_servidor_gradio(_app)
    return 0


if __name__ == "__main__":
    # No executavel empacotado (console=False) nao existe stdout: sem este
    # registro, qualquer falha de inicializacao some sem deixar rastro.
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        logging.getLogger("ViralCutter").critical(
            "Falha ao iniciar a janela", exc_info=True
        )
        raise
