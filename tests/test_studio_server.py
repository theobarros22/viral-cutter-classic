import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


RAIZ = Path(__file__).resolve().parents[1]
PASTA_STUDIO = RAIZ / "studio"
if str(PASTA_STUDIO) not in sys.path:
    sys.path.insert(0, str(PASTA_STUDIO))

from studio import server


def criar_handler(corpo=b"", headers=None):
    handler = server.ViralumeHandler.__new__(server.ViralumeHandler)
    handler.headers = headers or {}
    handler.rfile = io.BytesIO(corpo)
    handler.wfile = io.BytesIO()
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    return handler


class TestStudioServer(unittest.TestCase):
    def test_salvar_projeto_persiste_json_sem_servidor_real(self):
        dados = {
            "name": "Projeto Teste",
            "captions": [{"start": 0, "end": 1.5, "text": "Legenda valida"}],
            "inserts": [],
        }
        corpo = json.dumps(dados).encode("utf-8")
        handler = criar_handler(corpo, {"Content-Length": str(len(corpo))})

        with tempfile.TemporaryDirectory() as pasta:
            with patch.object(server, "PASTA_PROJETOS", Path(pasta)):
                handler._salvar_projeto()

            resposta = json.loads(handler.wfile.getvalue().decode("utf-8"))
            arquivo = Path(resposta["arquivo"])

            self.assertTrue(resposta["ok"])
            self.assertEqual(resposta["legendas"], 1)
            self.assertTrue(arquivo.exists())
            self.assertEqual(
                json.loads(arquivo.read_text(encoding="utf-8"))["name"],
                "Projeto Teste",
            )
            handler.send_response.assert_called_once_with(200)

    def test_preset_de_voz_invalido_nao_executa_ffmpeg(self):
        handler = criar_handler(
            b"video",
            {
                "Content-Length": "5",
                "X-File-Name": "teste.mp4",
                "X-Voice-Preset": "radio-magico",
            },
        )

        with patch.object(server.subprocess, "run") as executar:
            handler._aprimorar_voz()

        resposta = json.loads(handler.wfile.getvalue().decode("utf-8"))
        self.assertFalse(resposta["ok"])
        self.assertIn("Preset de voz invalido", resposta["erro"])
        handler.send_response.assert_called_once_with(400)
        executar.assert_not_called()

    def test_nome_seguro_normaliza_caracteres_e_limita_tamanho(self):
        nome = server._nome_seguro("  Corte viral: edição 01! " + "x" * 100)

        self.assertNotIn(" ", nome)
        self.assertNotIn(":", nome)
        self.assertLessEqual(len(nome), 80)
        self.assertEqual(server._nome_seguro("!!!"), "corte")

    def test_json_escreve_status_cabecalhos_e_corpo_utf8(self):
        handler = criar_handler()

        handler._json({"ok": False, "erro": "áudio inválido"}, status=422)

        corpo = handler.wfile.getvalue()
        handler.send_response.assert_called_once_with(422)
        handler.send_header.assert_any_call(
            "Content-Type", "application/json; charset=utf-8"
        )
        handler.send_header.assert_any_call("Content-Length", str(len(corpo)))
        handler.end_headers.assert_called_once_with()
        self.assertEqual(json.loads(corpo.decode("utf-8"))["erro"], "áudio inválido")


if __name__ == "__main__":
    unittest.main()
