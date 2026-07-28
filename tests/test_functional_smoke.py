import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import etapa3_processar, validar_midia_ffprobe


class TesteFuncionalPipeline(unittest.TestCase):
    def test_corte_e_enquadramento_real_com_acentos(self):
        ffmpeg = ROOT / "tools" / "ffmpeg.exe"
        if not ffmpeg.is_file():
            self.skipTest("FFmpeg empacotado nao encontrado.")

        with tempfile.TemporaryDirectory(prefix="viralume_funcional_") as pasta:
            pasta = Path(pasta)
            entrada = pasta / "entrada teste açúcar.mp4"
            saida = pasta / "saida com espacos"

            comando = [
                str(ffmpeg), "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-metadata", "title=Teste 🎬 açúcar",
                "-shortest", str(entrada),
            ]
            subprocess.run(comando, check=True, capture_output=True)

            pessoa_validada = {
                "id": 0, "nome": "Pessoa de teste", "posicao_x": 0.5,
                "posicao_y": 0.35, "tamanho": 0.2,
            }
            with patch.dict("pipeline._cache", {"pessoas": [pessoa_validada]}):
                resultados = etapa3_processar(
                    str(entrada),
                    str(saida),
                    [{"inicio": 0, "fim": 1.5, "titulo": "Teste funcional"}],
                    qualidade="720p",
                    perfil="rapido",
                    retomar=False,
                )

            self.assertEqual(len(resultados), 1)
            arquivo = resultados[0]["arquivo"]
            validacao = validar_midia_ffprobe(
                arquivo, duracao_esperada=1.5, audio_policy="optional"
            )
            self.assertTrue(validacao["valid"], validacao["errors"])
            self.assertFalse(
                any(nome.startswith("_temp_") for nome in os.listdir(Path(arquivo).parent))
            )


if __name__ == "__main__":
    unittest.main()
