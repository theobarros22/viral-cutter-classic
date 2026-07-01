"""Servidor local do Viralume Studio."""

import json
import os
import shutil
import subprocess
import tempfile
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from project import salvar_projeto
from voice_enhancer import filtro_voz


PORTA = 8766
PASTA_STUDIO = Path(__file__).resolve().parent
LIMITE_UPLOAD = 20 * 1024**3


def _pasta_dados():
    configurada = os.environ.get("VIRALUME_DATA_DIR")
    if configurada:
        return Path(configurada)
    principal = Path(r"D:\CORTE VIRAL\studio")
    if principal.drive and Path(f"{principal.drive}\\").exists():
        return principal
    local = os.environ.get("LOCALAPPDATA", tempfile.gettempdir())
    return Path(local) / "Viralume"


PASTA_DADOS = _pasta_dados()
PASTA_EXPORT = PASTA_DADOS / "exports"
PASTA_PROJETOS = PASTA_DADOS / "projects"
PASTA_AUDIO = PASTA_EXPORT / "audio_aprimorado"
INICIO_SERVIDOR = time.monotonic()


class ViralumeHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript; charset=utf-8",
        ".mjs": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        "": "application/octet-stream",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PASTA_STUDIO), **kwargs)

    def do_GET(self):
        if urlparse(self.path).path == "/api/health":
            ffmpeg = _localizar_ffmpeg()
            self._json({
                "ok": bool(ffmpeg),
                "status": "ready" if ffmpeg else "degraded",
                "ffmpeg": ffmpeg,
                "data_dir": str(PASTA_DADOS),
                "uptime_seconds": round(time.monotonic() - INICIO_SERVIDOR),
            }, status=200 if ffmpeg else 503)
            return
        super().do_GET()

    def do_POST(self):
        rota = urlparse(self.path).path
        if rota == "/api/project":
            self._salvar_projeto()
            return
        if rota == "/api/enhance-voice":
            self._aprimorar_voz()
            return
        if rota == "/api/transcribe":
            self._transcrever_video()
            return
        if rota == "/api/render":
            self._renderizar_projeto()
            return
        if rota != "/api/quick-cut":
            self.send_error(404)
            return

        try:
            tamanho = self._tamanho_upload()

            inicio = max(0.0, float(self.headers.get("X-Cut-Start", "0")))
            fim = float(self.headers.get("X-Cut-End", "0"))
            if fim <= inicio:
                raise ValueError("O ponto de saída deve ser maior que o de entrada.")

            nome = os.path.basename(self.headers.get("X-File-Name", "video.mp4"))
            base, extensao = os.path.splitext(nome)
            extensao = extensao if extensao.lower() in {".mp4", ".mov", ".mkv", ".webm"} else ".mp4"
            PASTA_EXPORT.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(delete=False, suffix=extensao) as temporario:
                restante = tamanho
                while restante:
                    bloco = self.rfile.read(min(1024 * 1024, restante))
                    if not bloco:
                        break
                    temporario.write(bloco)
                    restante -= len(bloco)
                caminho_entrada = temporario.name

            nome_saida = f"{_nome_seguro(base)}_{inicio:.2f}-{fim:.2f}{extensao}"
            caminho_saida = PASTA_EXPORT / nome_saida
            ffmpeg = _localizar_ffmpeg()
            if not ffmpeg:
                raise RuntimeError("FFmpeg nao foi encontrado.")
            comando = [
                ffmpeg, "-y", "-ss", f"{inicio:.3f}", "-i", caminho_entrada,
                "-t", f"{fim - inicio:.3f}", "-map", "0", "-c", "copy",
                "-avoid_negative_ts", "make_zero", str(caminho_saida),
            ]
            resultado = subprocess.run(comando, capture_output=True, text=True, timeout=3600)
            if resultado.returncode != 0:
                raise RuntimeError(resultado.stderr[-800:])

            self._json({
                "ok": True,
                "arquivo": str(caminho_saida),
                "modo": "lossless",
                "duracao": round(fim - inicio, 3),
                "aviso": "O modo lossless corta no keyframe mais próximo e pode incluir alguns frames extras.",
            })
        except Exception as erro:
            self._json({"ok": False, "erro": str(erro)}, status=400)
        finally:
            caminho = locals().get("caminho_entrada")
            if caminho and os.path.exists(caminho):
                os.remove(caminho)

    def _salvar_projeto(self):
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
            if tamanho <= 0 or tamanho > 10 * 1024 * 1024:
                raise ValueError("Tamanho de projeto invalido.")
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            arquivo, projeto = salvar_projeto(dados, PASTA_PROJETOS)
            self._json({
                "ok": True,
                "arquivo": str(arquivo),
                "legendas": len(projeto["captions"]),
                "insercoes": len(projeto["inserts"]),
            })
        except (ValueError, json.JSONDecodeError) as erro:
            self._json({"ok": False, "erro": str(erro)}, status=400)
        except Exception as erro:
            self._json({"ok": False, "erro": f"Falha ao salvar: {erro}"}, status=500)

    def _aprimorar_voz(self):
        caminho_entrada = None
        try:
            tamanho = self._tamanho_upload()
            preset = self.headers.get("X-Voice-Preset", "podcast")
            filtro = filtro_voz(preset)
            nome = os.path.basename(self.headers.get("X-File-Name", "video.mp4"))
            base, extensao = os.path.splitext(nome)
            extensao = extensao if extensao.lower() in {".mp4", ".mov", ".mkv", ".webm"} else ".mp4"
            with tempfile.NamedTemporaryFile(delete=False, suffix=extensao) as temporario:
                restante = tamanho
                while restante:
                    bloco = self.rfile.read(min(1024 * 1024, restante))
                    if not bloco:
                        break
                    temporario.write(bloco)
                    restante -= len(bloco)
                caminho_entrada = temporario.name
            PASTA_AUDIO.mkdir(parents=True, exist_ok=True)
            saida = PASTA_AUDIO / f"{_nome_seguro(base)}_voz_{preset}.mp4"
            ffmpeg = _localizar_ffmpeg()
            if not ffmpeg:
                raise RuntimeError("FFmpeg nao foi encontrado.")
            comando = [
                ffmpeg, "-y", "-i", caminho_entrada, "-map", "0:v?", "-map", "0:a:0",
                "-c:v", "copy", "-af", filtro, "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(saida),
            ]
            resultado = subprocess.run(comando, capture_output=True, text=True, timeout=7200)
            if resultado.returncode != 0:
                raise RuntimeError(resultado.stderr[-800:])
            self._json({"ok": True, "arquivo": str(saida), "preset": preset})
        except Exception as erro:
            self._json({"ok": False, "erro": str(erro)}, status=400)
        finally:
            if caminho_entrada and os.path.exists(caminho_entrada):
                os.remove(caminho_entrada)

    def _transcrever_video(self):
        caminho_entrada = None
        try:
            tamanho = self._tamanho_upload()
            nome = os.path.basename(self.headers.get("X-File-Name", "video.mp4"))
            base, extensao = os.path.splitext(nome)
            extensao = extensao if extensao.lower() in {".mp4", ".mov", ".mkv", ".webm"} else ".mp4"
            
            PASTA_TEMP_VIDEOS = PASTA_EXPORT / "temp_videos"
            PASTA_TEMP_VIDEOS.mkdir(parents=True, exist_ok=True)
            caminho_entrada = PASTA_TEMP_VIDEOS / f"{_nome_seguro(base)}{extensao}"
            
            with open(caminho_entrada, "wb") as f:
                restante = tamanho
                while restante:
                    bloco = self.rfile.read(min(1024 * 1024, restante))
                    if not bloco:
                        break
                    f.write(bloco)
                    restante -= len(bloco)
            
            import whisper
            import torch
            
            dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
            modelo = whisper.load_model("small", device=dispositivo)
            
            import sys
            sys.path.append(str(PASTA_STUDIO.parent))
            from legendas import extrair_palavras_do_whisper, agrupar_palavras
            
            resultado = modelo.transcribe(
                str(caminho_entrada),
                language="pt",
                verbose=False,
                fp16=(dispositivo == "cuda"),
                word_timestamps=True
            )
            
            duracao = float(resultado.get("segments", [{}])[-1].get("end", 10.0)) if resultado.get("segments") else 10.0
            
            palavras = extrair_palavras_do_whisper(resultado, 0, duracao)
            grupos = agrupar_palavras(palavras, max_palavras=3, max_duracao=2.0)
            
            captions = []
            for g in grupos:
                captions.append({
                    "start": g["inicio"],
                    "end": g["fim"],
                    "text": g["texto"].upper(),
                    "style": "standard",
                    "effect": "pop",
                    "highlight": False
                })
                
            self._json({
                "ok": True,
                "captions": captions
            })
        except Exception as erro:
            self._json({"ok": False, "erro": str(erro)}, status=400)

    def _renderizar_projeto(self):
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
            if tamanho <= 0 or tamanho > 10 * 1024 * 1024:
                raise ValueError("Tamanho de projeto invalido.")
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            
            video_info = dados.get("video", {})
            nome_video = video_info.get("name", "")
            if not nome_video:
                raise ValueError("Nome do video nao especificado no projeto.")
            
            base, extensao = os.path.splitext(nome_video)
            PASTA_TEMP_VIDEOS = PASTA_EXPORT / "temp_videos"
            caminho_video = PASTA_TEMP_VIDEOS / f"{_nome_seguro(base)}{extensao}"
            if not caminho_video.exists():
                caminho_video = PASTA_TEMP_VIDEOS / nome_video
                if not caminho_video.exists():
                    raise FileNotFoundError(f"Video original '{nome_video}' nao encontrado. Transcreva o video primeiro.")
            
            ffmpeg = _localizar_ffmpeg()
            if not ffmpeg:
                raise RuntimeError("FFmpeg nao foi encontrado.")
            
            effects = dados.get("effects", {})
            voice_enh = effects.get("voice_enhancement", {})
            af_str = None
            if voice_enh.get("enabled"):
                preset = voice_enh.get("preset", "podcast")
                af_str = filtro_voz(preset)
            
            filtro_v = []
            smart_layout_enabled = effects.get("smart_layout_enabled") is not False
            layout_name = effects.get("smart_layout", "solo")
            
            if smart_layout_enabled and layout_name != "solo":
                import sys
                sys.path.append(str(PASTA_STUDIO.parent))
                from smart_layouts import plano_layout, filtro_regiao
                plano = plano_layout(layout_name)
                if plano.get("regions"):
                    filtro_v.append(filtro_regiao(0, plano["regions"][0], "v_layout"))
                    rotulo_corrente = "[v_layout]"
                else:
                    rotulo_corrente = "[0:v]"
            else:
                rotulo_corrente = "[0:v]"
            
            events = effects.get("events", [])
            zoom_times = [float(ev["time"]) for ev in events if "zoom" in ev.get("type", "")]
            if zoom_times:
                import sys
                sys.path.append(str(PASTA_STUDIO.parent))
                from viral_effects import filtro_zoom_dinamico
                zoom_filt = filtro_zoom_dinamico(zoom_times, intensidade=1.15)
                filtro_v.append(f"{rotulo_corrente}{zoom_filt}[v_zoom]")
                rotulo_corrente = "[v_zoom]"
            
            duracao = float(video_info.get("duration", 10.0))
            color_hex = effects.get("progress_bar_color", "0xC63200").replace("#", "0x")
            import sys
            sys.path.append(str(PASTA_STUDIO.parent))
            from viral_effects import filtro_barra_progresso
            prog_filt = filtro_barra_progresso(duracao, cor=color_hex, altura=10)
            filtro_v.append(f"{rotulo_corrente}{prog_filt}[v_prog]")
            rotulo_corrente = "[v_prog]"
            
            PASTA_EXPORT.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4", dir=str(PASTA_EXPORT)) as temporario:
                caminho_filtros = temporario.name
            
            comando = [ffmpeg, "-y", "-i", str(caminho_video)]
            
            vf_args = []
            for f in filtro_v:
                if f.startswith("["):
                    vf_args.append(f)
                else:
                    vf_args.append(f"{rotulo_corrente}{f}[out_v]")
                    rotulo_corrente = "[out_v]"
            
            if vf_args:
                filter_graph = ";".join(vf_args)
                comando += ["-filter_complex", filter_graph, "-map", rotulo_corrente]
            else:
                comando += ["-map", "0:v?"]
            
            if af_str:
                comando += ["-af", af_str, "-c:a", "aac", "-b:a", "192k"]
            else:
                comando += ["-map", "0:a?", "-c:a", "copy"]
            
            comando += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", caminho_filtros]
            
            resultado = subprocess.run(comando, capture_output=True, text=True, timeout=7200)
            if resultado.returncode != 0:
                raise RuntimeError(f"FFmpeg filter error: {resultado.stderr[-500:]}")
            
            captions = dados.get("captions", [])
            nome_saida = f"{_nome_seguro(base)}_renderizado.mp4"
            caminho_saida = PASTA_EXPORT / nome_saida
            
            if captions:
                import sys
                sys.path.append(str(PASTA_STUDIO.parent))
                from legendas import aplicar_legendas
                
                palavras_render = []
                for cap in captions:
                    palavras_render.append({
                        "inicio": cap["start"],
                        "fim": cap["end"],
                        "texto": cap["text"]
                    })
                
                sucesso = aplicar_legendas(
                    caminho_filtros,
                    str(caminho_saida),
                    palavras_render,
                    template="palavra-vazada",
                    config={"posicao": "bottom"}
                )
                if not sucesso:
                    shutil.copy2(caminho_filtros, caminho_saida)
            else:
                shutil.copy2(caminho_filtros, caminho_saida)
            
            if os.path.exists(caminho_filtros):
                os.remove(caminho_filtros)
            
            self._json({
                "ok": True,
                "arquivo": str(caminho_saida)
            })
        except Exception as erro:
            self._json({"ok": False, "erro": str(erro)}, status=400)

    def _json(self, dados, status=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _tamanho_upload(self):
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
        except ValueError as erro:
            raise ValueError("Tamanho de upload invalido.") from erro
        if tamanho <= 0:
            raise ValueError("O arquivo enviado esta vazio.")
        if tamanho > LIMITE_UPLOAD:
            raise ValueError("Arquivo maior que o limite de 20 GB.")
        return tamanho


def _nome_seguro(nome):
    permitido = "".join(c if c.isalnum() or c in "-_" else "_" for c in nome)
    return permitido.strip("_")[:80] or "corte"


def _localizar_ffmpeg():
    candidatos = [
        shutil.which("ffmpeg"),
        str(PASTA_STUDIO.parent / "files" / "tools" / "ffmpeg.exe"),
        str(PASTA_STUDIO.parent / "tools" / "ffmpeg.exe"),
    ]
    return next((item for item in candidatos if item and Path(item).is_file()), None)


class ViralumeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    print(f"Viralume Studio: http://127.0.0.1:{PORTA}")
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    ViralumeServer(("127.0.0.1", PORTA), ViralumeHandler).serve_forever()
