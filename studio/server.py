"""Servidor local do Viralume Studio."""

import json
import os
import shutil
import subprocess
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from project import salvar_projeto
from voice_enhancer import filtro_voz


PORTA = 8766
PASTA_STUDIO = Path(__file__).resolve().parent
PASTA_EXPORT = Path(r"D:\CORTE VIRAL\studio\exports")
PASTA_PROJETOS = Path(r"D:\CORTE VIRAL\studio\projects")
PASTA_AUDIO = Path(r"D:\CORTE VIRAL\studio\exports\audio_aprimorado")


class ViralumeHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PASTA_STUDIO), **kwargs)

    def do_POST(self):
        rota = urlparse(self.path).path
        if rota == "/api/project":
            self._salvar_projeto()
            return
        if rota == "/api/enhance-voice":
            self._aprimorar_voz()
            return
        if rota != "/api/quick-cut":
            self.send_error(404)
            return

        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
            if tamanho <= 0:
                raise ValueError("O vídeo enviado está vazio.")

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
            ffmpeg = shutil.which("ffmpeg") or str(PASTA_STUDIO.parent / "tools" / "ffmpeg.exe")
            comando = [
                ffmpeg, "-y", "-ss", f"{inicio:.3f}", "-i", caminho_entrada,
                "-t", f"{fim - inicio:.3f}", "-map", "0", "-c", "copy",
                "-avoid_negative_ts", "make_zero", str(caminho_saida),
            ]
            resultado = subprocess.run(comando, capture_output=True, text=True)
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
            tamanho = int(self.headers.get("Content-Length", "0"))
            if tamanho <= 0:
                raise ValueError("O video enviado esta vazio.")
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
            ffmpeg = shutil.which("ffmpeg") or str(PASTA_STUDIO.parent / "tools" / "ffmpeg.exe")
            comando = [
                ffmpeg, "-y", "-i", caminho_entrada, "-map", "0:v?", "-map", "0:a:0",
                "-c:v", "copy", "-af", filtro, "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(saida),
            ]
            resultado = subprocess.run(comando, capture_output=True, text=True)
            if resultado.returncode != 0:
                raise RuntimeError(resultado.stderr[-800:])
            self._json({"ok": True, "arquivo": str(saida), "preset": preset})
        except Exception as erro:
            self._json({"ok": False, "erro": str(erro)}, status=400)
        finally:
            if caminho_entrada and os.path.exists(caminho_entrada):
                os.remove(caminho_entrada)

    def _json(self, dados, status=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


def _nome_seguro(nome):
    permitido = "".join(c if c.isalnum() or c in "-_" else "_" for c in nome)
    return permitido.strip("_")[:80] or "corte"


if __name__ == "__main__":
    print(f"Viralume Studio: http://127.0.0.1:{PORTA}")
    ThreadingHTTPServer(("127.0.0.1", PORTA), ViralumeHandler).serve_forever()
