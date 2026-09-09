import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime

with patch.object(runtime, 'garantir_instancia_unica', return_value=True):
    import interface


class TestInterfaceDetection(unittest.TestCase):
    def test_face_panel_is_mounted_before_detection(self):
        conteudo = (Path(__file__).parents[1] / 'interface.py').read_text(encoding='utf-8')

        self.assertIn('with gr.Group() as painel_rostos:', conteudo)
        self.assertNotIn('with gr.Group(visible=False) as painel_rostos:', conteudo)
        self.assertNotIn('ao_revelar_painel_rostos', conteudo)

    def test_detection_returns_every_person_to_gallery_and_selection(self):
        pessoas = [
            {"id": 0, "nome": "Pessoa 1 (esquerda)", "preview_path": "esquerda.jpg"},
            {"id": 1, "nome": "Pessoa 2 (direita)", "preview_path": "direita.jpg"},
        ]
        anterior = interface._estado.copy()
        arquivo = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        arquivo.close()
        try:
            interface._estado["caminho_video"] = arquivo.name
            with patch("interface.etapa1_detectar_pessoas", return_value=pessoas):
                _, galeria, opcoes = interface.ao_detectar_pessoas(None)

            self.assertEqual(galeria, [
                ("esquerda.jpg", "Pessoa 1 (esquerda)"),
                ("direita.jpg", "Pessoa 2 (direita)"),
            ])
            self.assertEqual(opcoes["choices"], ["Pessoa 1 (esquerda)", "Pessoa 2 (direita)"])
            self.assertEqual(opcoes["value"], ["Pessoa 1 (esquerda)", "Pessoa 2 (direita)"])
        finally:
            interface._estado.clear()
            interface._estado.update(anterior)
            os.unlink(arquivo.name)


if __name__ == "__main__":
    unittest.main()
