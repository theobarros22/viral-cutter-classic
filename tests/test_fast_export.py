"""
test_fast_export.py
-------------------
Testes para o motor de exportação acelerada e fallback seguro de enquadramento.
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import enquadramento
from enquadramento import (
    _agrupar_planos_em_segmentos,
    _calcular_filtros_shot,
    _construir_grafo_enquadramento,
    _renderizar_enquadramento_ffmpeg,
    _renderizar_enquadramento_pipe,
    aplicar_enquadramento,
)
from pipeline import validar_midia_ffprobe


class TestFastExportEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = "ffmpeg"
        tools_ffmpeg = ROOT / "tools" / "ffmpeg.exe"
        if tools_ffmpeg.is_file():
            cls.ffmpeg = str(tools_ffmpeg)

    def _gerar_video_teste(self, destino: Path, duracao_s: float = 3.0, largura: int = 640, altura: int = 360):
        cmd = [
            self.ffmpeg, "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={largura}x{altura}:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", str(duracao_s),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest", str(destino),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def test_agrupar_planos_em_segmentos(self):
        plano = (
            [{"modo": "SOLO_A", "xa": 0.3, "ya": 0.4, "ta": 0.1, "xb": 0.7, "yb": 0.4, "tb": 0.1}] * 30
            + [{"modo": "SOLO_B", "xa": 0.3, "ya": 0.4, "ta": 0.1, "xb": 0.7, "yb": 0.4, "tb": 0.1}] * 30
            + [{"modo": "SPLIT", "xa": 0.3, "ya": 0.4, "ta": 0.1, "xb": 0.7, "yb": 0.4, "tb": 0.1}] * 30
        )
        segs = _agrupar_planos_em_segmentos(plano, fps=30.0)
        self.assertEqual(len(segs), 3)
        self.assertEqual(segs[0]["plano"]["modo"], "SOLO_A")
        self.assertAlmostEqual(segs[0]["start_s"], 0.0)
        self.assertAlmostEqual(segs[0]["end_s"], 1.0)
        self.assertEqual(segs[1]["plano"]["modo"], "SOLO_B")
        self.assertAlmostEqual(segs[1]["start_s"], 1.0)
        self.assertAlmostEqual(segs[1]["end_s"], 2.0)
        self.assertEqual(segs[2]["plano"]["modo"], "SPLIT")
        self.assertAlmostEqual(segs[2]["start_s"], 2.0)
        self.assertAlmostEqual(segs[2]["end_s"], 3.0)

    def test_calcular_filtros_shot_modos(self):
        largura, altura = 1920, 1080
        saida_w, saida_h = 1080, 1920

        # SOLO_A
        shot_solo = _calcular_filtros_shot(
            {"modo": "SOLO_A", "xa": 0.3, "ya": 0.4, "ta": 0.1, "xb": 0.7, "yb": 0.4, "tb": 0.1},
            largura, altura, saida_w, saida_h
        )
        self.assertEqual(shot_solo["tipo"], "solo")
        self.assertEqual(shot_solo["scale"], (1080, 1920))
        x, y, w, h = shot_solo["crop"]
        self.assertTrue(0 <= x <= largura - w)
        self.assertTrue(0 <= y <= altura - h)

        # SPLIT
        shot_split = _calcular_filtros_shot(
            {"modo": "SPLIT", "xa": 0.3, "ya": 0.4, "ta": 0.1, "xb": 0.7, "yb": 0.4, "tb": 0.1},
            largura, altura, saida_w, saida_h
        )
        self.assertEqual(shot_split["tipo"], "split")
        self.assertEqual(shot_split["top_scale"], (1080, 960))
        self.assertEqual(shot_split["bot_scale"], (1080, 960))

        # GRUPO
        shot_grupo = _calcular_filtros_shot(
            {"modo": "GRUPO", "xa": 0.3, "ya": 0.4, "ta": 0.1, "xb": 0.7, "yb": 0.4, "tb": 0.1},
            largura, altura, saida_w, saida_h
        )
        self.assertEqual(shot_grupo["tipo"], "solo")

    def test_construir_grafo_enquadramento_sintaxe(self):
        largura, altura = 1920, 1080
        saida_w, saida_h = 1080, 1920
        segmentos = [
            {
                "plano": {"modo": "SOLO_A", "xa": 0.3, "ya": 0.4, "ta": 0.1, "xb": 0.7, "yb": 0.4, "tb": 0.1},
                "start_s": 0.0,
                "end_s": 1.5,
            },
            {
                "plano": {"modo": "SPLIT", "xa": 0.3, "ya": 0.4, "ta": 0.1, "xb": 0.7, "yb": 0.4, "tb": 0.1},
                "start_s": 1.5,
                "end_s": 3.0,
            },
        ]
        grafo = _construir_grafo_enquadramento(segmentos, largura, altura, saida_w, saida_h)
        self.assertIn("split=2[in0][in1]", grafo)
        self.assertIn("concat=n=2:v=1:a=0[vout]", grafo)
        self.assertIn("vstack", grafo)
        self.assertIn("setsar=1", grafo)

    def test_renderizacao_direta_e_pipe_equivalencia(self):
        with tempfile.TemporaryDirectory(prefix="viral_test_fast_") as tmpdir:
            tmp_path = Path(tmpdir)
            entrada = tmp_path / "entrada.mp4"
            saida_ffmpeg = tmp_path / "saida_ffmpeg.mp4"
            saida_pipe = tmp_path / "saida_pipe.mp4"

            self._gerar_video_teste(entrada, duracao_s=2.0, largura=640, altura=360)

            plano = (
                [{"modo": "SOLO_A", "xa": 0.3, "ya": 0.4, "ta": 0.1, "xb": 0.7, "yb": 0.4, "tb": 0.1}] * 30
                + [{"modo": "SPLIT", "xa": 0.3, "ya": 0.4, "ta": 0.1, "xb": 0.7, "yb": 0.4, "tb": 0.1}] * 30
            )

            # 1. Render Direto FFmpeg
            t0 = time.perf_counter()
            segmentos = _agrupar_planos_em_segmentos(plano, fps=30.0)
            sucesso_ffmpeg = _renderizar_enquadramento_ffmpeg(
                str(entrada), str(saida_ffmpeg), segmentos,
                640, 360, 406, 720, perfil="rapido"
            )
            t_ffmpeg = time.perf_counter() - t0

            self.assertTrue(sucesso_ffmpeg)
            self.assertTrue(saida_ffmpeg.is_file())

            # 2. Render Pipe Fallback
            t0 = time.perf_counter()
            sucesso_pipe = _renderizar_enquadramento_pipe(
                str(entrada), str(saida_pipe), plano,
                640, 360, 30.0, 406, 720, len(plano), perfil="rapido"
            )
            t_pipe = time.perf_counter() - t0

            self.assertTrue(sucesso_pipe)
            self.assertTrue(saida_pipe.is_file())

            # 3. Validação FFprobe de ambos
            val_ffmpeg = validar_midia_ffprobe(str(saida_ffmpeg), duracao_esperada=2.0, audio_policy="optional")
            self.assertTrue(val_ffmpeg["valid"], val_ffmpeg["errors"])
            self.assertEqual(val_ffmpeg["width"], 406)
            self.assertEqual(val_ffmpeg["height"], 720)

            val_pipe = validar_midia_ffprobe(str(saida_pipe), duracao_esperada=2.0, audio_policy="optional")
            self.assertTrue(val_pipe["valid"], val_pipe["errors"])
            self.assertEqual(val_pipe["width"], 406)
            self.assertEqual(val_pipe["height"], 720)

            # O motor nativo direto deve ser mais rápido
            print(f"\n   ⚡ Tempo FFmpeg nativo: {t_ffmpeg:.3f}s | Tempo Pipe: {t_pipe:.3f}s")

    def test_aplicar_enquadramento_completo(self):
        with tempfile.TemporaryDirectory(prefix="viral_test_enq_") as tmpdir:
            tmp_path = Path(tmpdir)
            entrada = tmp_path / "entrada.mp4"
            saida = tmp_path / "saida_final.mp4"

            self._gerar_video_teste(entrada, duracao_s=2.0, largura=640, altura=360)

            sucesso = aplicar_enquadramento(
                str(entrada), str(saida),
                posicoes_falante=[0.5] * 60,
                qualidade="720p",
                perfil="rapido",
            )
            self.assertTrue(sucesso)
            self.assertTrue(saida.is_file())
            val = validar_midia_ffprobe(str(saida), duracao_esperada=2.0, audio_policy="optional")
            self.assertTrue(val["valid"], val["errors"])
            self.assertEqual(val["width"], 406)
            self.assertEqual(val["height"], 720)


if __name__ == "__main__":
    unittest.main()
