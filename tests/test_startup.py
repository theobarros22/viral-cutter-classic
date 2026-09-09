import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime


class TestStartup(unittest.TestCase):
    def test_runtime_forces_gradio_temp_into_local_app_data(self):
        with tempfile.TemporaryDirectory() as local_app_data:
            with patch.dict(
                os.environ,
                {
                    "LOCALAPPDATA": local_app_data,
                    "GRADIO_TEMP_DIR": r"D:\ViralCutter\gradio_temp",
                },
                clear=False,
            ):
                runtime.configurar_ambiente()

                esperado = os.path.join(
                    local_app_data, "ViralCutter", "gradio_temp"
                )
                self.assertEqual(os.environ["GRADIO_TEMP_DIR"], esperado)
                self.assertTrue(os.path.isdir(esperado))

    def test_lancador_batch_nao_dependente_de_unidade_d(self):
        conteudo = (Path(__file__).parents[1] / "iniciar.bat").read_text(
            encoding="utf-8"
        )

        self.assertNotIn(r"D:\ViralCutter", conteudo)
        self.assertIn(r"%LOCALAPPDATA%\ViralCutter\gradio_temp", conteudo)

    def test_falha_da_janela_nativa_nao_abre_navegador(self):
        conteudo = (Path(__file__).parents[1] / "app_desktop.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("webbrowser.open(", conteudo)


if __name__ == "__main__":
    unittest.main()
