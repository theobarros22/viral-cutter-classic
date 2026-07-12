"""
download_video.py
-----------------
Baixa vídeos de links da internet (YouTube, etc.) para dentro do pipeline,
usando yt-dlp — a ferramenta open source padrão para isso, atualizada com
frequência quando as plataformas mudam.

Instalação (uma vez):
    venv311\\Scripts\\pip install yt-dlp

AVISO DE USO: baixe apenas vídeos SEUS ou com direito de uso autorizado.
Baixar conteúdo de terceiros pode violar os termos da plataforma e
direitos autorais.
"""

import os


def pasta_downloads() -> str:
    """Pasta padrão onde os vídeos baixados ficam guardados."""
    from runtime import pasta_dados
    pasta = os.path.join(pasta_dados(), "downloads")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def baixar_video(url: str, pasta_destino: str = None, progresso_callback=None) -> str:
    """
    Baixa o vídeo do link e retorna o caminho do arquivo MP4 final.

    Parâmetros:
        url: link do vídeo (YouTube, Vimeo, etc.)
        pasta_destino: onde salvar (padrão: pasta de downloads do app)
        progresso_callback: função que recebe mensagens de progresso

    Levanta:
        ImportError se o yt-dlp não estiver instalado
        RuntimeError em falha de download
    """
    import yt_dlp  # ImportError aqui é tratado pela interface

    def log(msg):
        if progresso_callback:
            progresso_callback(msg)
        print(msg)

    pasta = pasta_destino or pasta_downloads()

    ultimo_pct = {"v": -10}

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            baixado = d.get("downloaded_bytes", 0)
            if total:
                pct = int(baixado * 100 / total)
                # Loga a cada 10% para não inundar a interface
                if pct >= ultimo_pct["v"] + 10:
                    ultimo_pct["v"] = pct
                    log(f"⬇️ Baixando... {pct}%")
        elif d.get("status") == "finished":
            log("📦 Download concluído. Juntando áudio e vídeo...")

    opcoes = {
        # MP4 H.264 até 1080p — formato que todo o pipeline já entende.
        # Vídeos 4K seriam mais lentos em tudo e o export final é 1080x1920.
        "format": "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(pasta, "%(title).80s.%(ext)s"),
        # Nomes de arquivo sem acentos/símbolos: menos surpresa no FFmpeg
        "restrictfilenames": True,
        "noplaylist": True,  # link de playlist baixa SÓ o vídeo apontado
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
    }

    log(f"🔗 Conectando: {url}")
    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"Download falhou: {e}") from e

    # Caminho final (após merge para .mp4)
    caminho = None
    solicitados = info.get("requested_downloads") or []
    if solicitados and solicitados[0].get("filepath"):
        caminho = solicitados[0]["filepath"]
    else:
        caminho = ydl.prepare_filename(info)
        base, _ = os.path.splitext(caminho)
        if os.path.exists(base + ".mp4"):
            caminho = base + ".mp4"

    if not caminho or not os.path.exists(caminho):
        raise RuntimeError("Download terminou mas o arquivo final não foi encontrado.")

    duracao = info.get("duration") or 0
    log(f"✅ Pronto: {os.path.basename(caminho)} ({duracao // 60}min{duracao % 60:02d}s)")
    return caminho
