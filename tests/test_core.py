import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from checkpoint import carregar_checkpoint, resultado_valido, salvar_checkpoint
from cortes import calcular_intervalos_fala
from enquadramento import _agrupar_posicoes_cena, _calcular_x_crop
from ffmpeg_utils import argumentos_encoder
from pipeline import _fundir_intervalos, _validar_segmentos, sanitizar_nome
from rostos import _limpar_deteccoes, detectar_pessoas_no_video
from studio.viral_effects import (
    expressao_zoom, filtro_barra_progresso, filtro_lut, filtros_sfx,
)
from studio.project import validar_projeto


class TestCore(unittest.TestCase):
    def test_projeto_descarta_legenda_invalida(self):
        projeto = validar_projeto({
            "name": "Teste",
            "captions": [
                {"start": 0, "end": 1.5, "text": "Legenda valida"},
                {"start": 2, "end": 1, "text": "Fim invalido"},
                {"start": 2, "end": 3, "text": ""},
            ],
        })
        self.assertEqual(len(projeto["captions"]), 1)
        self.assertEqual(projeto["captions"][0]["text"], "Legenda valida")

    def test_segmentos_invalidos_sao_descartados(self):
        segmentos = [
            {"inicio": 10, "fim": 20},
            {"inicio": 20, "fim": 10},
            {"inicio": "x", "fim": 30},
        ]
        self.assertEqual(_validar_segmentos(segmentos), [{"inicio": 10.0, "fim": 20.0}])

    def test_intervalos_sobrepostos_sao_fundidos(self):
        self.assertEqual(_fundir_intervalos([(10, 20), (15, 30), (40, 50)]), [(10, 30), (40, 50)])

    def test_silencios_viram_intervalos_de_fala_com_respiro(self):
        intervalos = calcular_intervalos_fala(
            10000, [(2000, 4000), (7000, 8000)], margem_ms=100
        )
        self.assertEqual(intervalos, [(0, 2100), (3900, 7100), (7900, 10000)])

    def test_zoom_dinamico_limita_intensidade(self):
        expressao = expressao_zoom([1.0, 3.5], intensidade=1.8)
        self.assertIn("1.300", expressao)
        self.assertIn("between(t,1.000,1.450)", expressao)

    def test_barra_progresso_usa_duracao(self):
        filtro = filtro_barra_progresso(10, altura=8)
        self.assertIn("t/10.000", filtro)
        self.assertIn("h=8", filtro)

    def test_lut_exige_cube(self):
        with self.assertRaises(ValueError):
            filtro_lut("visual.png")
        self.assertIn("lut3d", filtro_lut(r"D:\luts\cinema.cube"))

    def test_sfx_sao_atrasados_e_mixados(self):
        filtros, saida = filtros_sfx([{"tempo": 1.25, "volume": 0.8}])
        self.assertIn("adelay=1250|1250", filtros[0])
        self.assertIn("amix=inputs=2", filtros[-1])
        self.assertEqual(saida, "[aout]")

    def test_nome_vazio_tem_fallback(self):
        self.assertEqual(sanitizar_nome(""), "clipe")

    def test_crop_fica_dentro_do_frame(self):
        self.assertEqual(_calcular_x_crop(0.0, 1920, 608), 0)
        self.assertEqual(_calcular_x_crop(1.0, 1920, 608), 1312)

    def test_duas_pessoas_sao_separadas(self):
        grupo = _agrupar_posicoes_cena([0.2, 0.22, 0.78, 0.8])
        self.assertEqual(grupo["n_pessoas"], 2)

    def test_encoder_tem_codec_definido(self):
        argumentos = argumentos_encoder()
        self.assertIn("-c:v", argumentos)

    def test_deteccoes_duplicadas_sao_removidas(self):
        rostos = _limpar_deteccoes([
            {"x": 0.3, "y": 0.3, "w": 0.1, "h": 0.1},
            {"x": 0.31, "y": 0.31, "w": 0.1, "h": 0.1},
        ])
        self.assertEqual(len(rostos), 1)

    def test_deteccao_inicial_usa_cinco_minutos(self):
        import inspect
        assinatura = inspect.signature(detectar_pessoas_no_video)
        self.assertEqual(assinatura.parameters["limite_minutos"].default, 5.0)
        self.assertEqual(assinatura.parameters["max_amostras"].default, 30)

    def test_checkpoint_e_gravado_e_carregado(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "checkpoint.json")
            salvar_checkpoint(caminho, {"versao": 1, "clipes": {}})
            dados = carregar_checkpoint(caminho)
            self.assertEqual(dados["versao"], 1)

    def test_resultado_incompleto_nao_e_reaproveitado(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "clipe.mp4")
            with open(caminho, "wb") as arquivo:
                arquivo.write(b"incompleto")
            self.assertFalse(resultado_valido({"arquivo": caminho}))

    def test_processamento_reaproveita_clipe_concluido(self):
        chamadas = {"corte": 0, "enquadramento": 0}

        def cortar_clipe(_video, _inicio, _fim, destino):
            chamadas["corte"] += 1
            with open(destino, "wb") as arquivo:
                arquivo.write(b"temp")
            return True

        def aplicar_enquadramento(_origem, destino, *_args, **_kwargs):
            chamadas["enquadramento"] += 1
            with open(destino, "wb") as arquivo:
                arquivo.write(b"0" * 70000)
            return True

        modulos = {
            "cortes": types.SimpleNamespace(cortar_clipe=cortar_clipe),
            "enquadramento": types.SimpleNamespace(aplicar_enquadramento=aplicar_enquadramento),
            "rostos": types.SimpleNamespace(detectar_quem_fala_por_frame=lambda *_a, **_k: []),
        }

        with tempfile.TemporaryDirectory() as pasta, patch.dict(sys.modules, modulos):
            video = os.path.join(pasta, "video.mp4")
            with open(video, "wb") as arquivo:
                arquivo.write(b"video")
            segmentos = [{"inicio": 0, "fim": 10, "titulo": "Teste"}]

            from pipeline import etapa3_processar

            etapa3_processar(video, pasta, segmentos, qualidade="720p")
            with patch("checkpoint.resultado_valido", return_value=True):
                etapa3_processar(video, pasta, [], qualidade="720p", retomar=True)

            self.assertEqual(chamadas["corte"], 1)
            self.assertEqual(chamadas["enquadramento"], 1)
            pasta_trabalho = os.path.join(pasta, "video")
            logs = [
                os.path.join(pasta_trabalho, nome)
                for nome in os.listdir(pasta_trabalho)
                if nome.endswith(".log")
            ]
            self.assertEqual(len(logs), 1)
            with open(logs[0], "r", encoding="utf-8") as arquivo:
                self.assertIn("RETOMANDO", arquivo.read())

    def test_perfil_rapido_reduz_analise_visual(self):
        parametros = {}

        def cortar_clipe(_video, _inicio, _fim, destino):
            with open(destino, "wb") as arquivo:
                arquivo.write(b"temp")
            return True

        def detectar_falante(*_args, **kwargs):
            parametros["intervalo"] = kwargs["intervalo_frames"]
            parametros["audio"] = kwargs["analisar_audio"]
            return []

        def aplicar_enquadramento(_origem, destino, *_args, **kwargs):
            parametros["perfil"] = kwargs["perfil"]
            with open(destino, "wb") as arquivo:
                arquivo.write(b"0" * 70000)
            return True

        modulos = {
            "cortes": types.SimpleNamespace(cortar_clipe=cortar_clipe),
            "enquadramento": types.SimpleNamespace(aplicar_enquadramento=aplicar_enquadramento),
            "rostos": types.SimpleNamespace(detectar_quem_fala_por_frame=detectar_falante),
        }

        with tempfile.TemporaryDirectory() as pasta, patch.dict(sys.modules, modulos):
            video = os.path.join(pasta, "video.mp4")
            with open(video, "wb") as arquivo:
                arquivo.write(b"video")
            from pipeline import etapa3_processar
            etapa3_processar(
                video, pasta, [{"inicio": 0, "fim": 5, "titulo": "Rapido"}],
                qualidade="720p", perfil="rapido", retomar=False,
            )

        self.assertEqual(parametros["intervalo"], 30)
        self.assertFalse(parametros["audio"])
        self.assertEqual(parametros["perfil"], "rapido")

if __name__ == "__main__":
    unittest.main()
