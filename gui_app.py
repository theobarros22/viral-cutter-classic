"""
gui_app.py — Interface Webview para o Vollare Viral Cutter
---------------------------------------------------------
Este arquivo inicializa a janela nativa do Windows usando pywebview
e expõe a API do Python (BridgeAPI) para o frontend em React.
"""

import os
import sys
import threading
import webview

# Importa as etapas do pipeline existentes
from pipeline import etapa1_detectar_pessoas, etapa2_analisar, etapa3_processar, solicitar_cancelamento

class BridgeAPI:
    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def selecionar_video(self):
        """Abre uma caixa de diálogo nativa para selecionar um arquivo de vídeo."""
        if not self._window:
            return None
        
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=('Vídeos (*.mp4; *.mov; *.avi; *.mkv)', '*.mp4; *.mov; *.avi; *.mkv')
        )
        if result and len(result) > 0:
            return result[0]
        return None

    def selecionar_pasta(self):
        """Abre uma caixa de diálogo nativa para selecionar uma pasta de exportação."""
        if not self._window:
            return None
        
        result = self._window.create_file_dialog(
            webview.FOLDER_DIALOG
        )
        if result and len(result) > 0:
            return result[0]
        return None

    def detectar_pessoas(self, caminho_video):
        """Executa a Etapa 1: Detectar pessoas no vídeo."""
        try:
            # Executa a detecção
            pessoas = etapa1_detectar_pessoas(caminho_video)
            return {
                "sucesso": True,
                "pessoas": pessoas
            }
        except Exception as e:
            return {
                "sucesso": False,
                "erro": str(e)
            }

    def analisar_video(self, caminho_video, idioma, modelo, nicho, duracao_min, duracao_max, modo_offline):
        """Executa a Etapa 2: Transcrever e segmentar o vídeo."""
        try:
            segmentos = etapa2_analisar(
                caminho_video=caminho_video,
                idioma=idioma,
                modelo_whisper=modelo,
                nicho=nicho,
                duracao_min=int(duracao_min),
                duracao_max=int(duracao_max),
                modo_offline=modo_offline
            )
            return {
                "sucesso": True,
                "segmentos": segmentos
            }
        except Exception as e:
            return {
                "sucesso": False,
                "erro": str(e)
            }

    def processar_video(self, caminho_video, pasta_saida, segmentos, pessoas_priorizadas_ids, qualidade, perfil, retomar, remover_pausas, min_silencio_ms, margem_silencio_ms, aplicar_legendas_auto):
        """
        Executa a Etapa 3: Cortar e enquadrar os clipes em uma thread separada
        para não travar a interface gráfica. Envia eventos de progresso ao frontend.
        """
        def run():
            try:
                def progresso_callback(msg):
                    # Dispara evento no JavaScript da janela
                    if self._window:
                        self._window.evaluate_js(f"window.dispatchEvent(new CustomEvent('pipeline-progress', {{ detail: {repr(msg)} }}));")

                resultados = etapa3_processar(
                    caminho_video=caminho_video,
                    pasta_saida_base=pasta_saida,
                    segmentos=segmentos,
                    pessoas_priorizadas_ids=pessoas_priorizadas_ids,
                    qualidade=qualidade,
                    perfil=perfil,
                    retomar=retomar,
                    remover_pausas=remover_pausas,
                    min_silencio_ms=int(min_silencio_ms),
                    margem_silencio_ms=int(margem_silencio_ms),
                    aplicar_legendas_auto=aplicar_legendas_auto,
                    progresso_callback=progresso_callback
                )
                
                if self._window:
                    self._window.evaluate_js(f"window.dispatchEvent(new CustomEvent('pipeline-completed', {{ detail: {repr(resultados)} }}));")
            
            except Exception as e:
                import traceback
                erro_msg = f"{str(e)}\n{traceback.format_exc()}"
                if self._window:
                    self._window.evaluate_js(f"window.dispatchEvent(new CustomEvent('pipeline-error', {{ detail: {repr(erro_msg)} }}));")

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return {"sucesso": True, "mensagem": "Processamento iniciado em segundo plano."}

    def cancelar_processamento(self):
        """Solicita o cancelamento cooperativo do pipeline."""
        solicitar_cancelamento()
        return {"sucesso": True, "mensagem": "Cancelamento solicitado."}

    def abrir_pasta_sistema(self, pasta):
        """Abre uma pasta no Windows Explorer."""
        if os.path.exists(pasta):
            try:
                os.startfile(pasta)
                return {"sucesso": True}
            except Exception as e:
                return {"sucesso": False, "erro": str(e)}
        return {"sucesso": False, "erro": "Pasta não encontrada."}


def iniciar_aplicacao():
    # Cria a instância da API
    api = BridgeAPI()

    # Define o endereço da janela: servidor dev do Vite ou build estático
    # Modo de desenvolvimento se a variável de ambiente for configurada
    is_dev = os.environ.get("VIRAL_CUTTER_DEV", "0") == "1"
    
    url = "http://localhost:5173" if is_dev else os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist", "index.html")

    # Inicializa a janela do webview
    window = webview.create_window(
        title="Vollare Viral Cutter v2",
        url=url,
        js_api=api,
        width=1280,
        height=800,
        min_size=(1000, 650),
        background_color="#000000"
    )
    
    api.set_window(window)
    webview.start(debug=is_dev)

if __name__ == "__main__":
    iniciar_aplicacao()
