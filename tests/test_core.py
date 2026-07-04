import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from checkpoint import carregar_checkpoint, resultado_valido, salvar_checkpoint
from cortes import (
    ajustar_cortes_com_silencio,
    calcular_intervalos_fala,
    refinar_limites_com_palavras,
    validar_hook,
)
from enquadramento import _agrupar_posicoes_cena, _calcular_x_crop
from ffmpeg_utils import argumentos_encoder
from pipeline import _fundir_intervalos, _validar_segmentos, sanitizar_nome
from rostos import (
    _caminho_modelo_facial,
    _fechar_detector,
    _inicializar_detector,
    _limpar_deteccoes,
    detectar_pessoas_no_video,
)
class TestCore(unittest.TestCase):
    def test_modelo_facial_tem_caminho_persistente(self):
        self.assertTrue(_caminho_modelo_facial().endswith("face_detector.tflite"))

    def test_detector_principal_inicializa(self):
        detector = _inicializar_detector()
        try:
            self.assertIsNotNone(detector)
            self.assertIsNotNone(detector.get("mediapipe") or detector.get("haar"))
        finally:
            _fechar_detector(detector)

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

    def test_refinamento_ajusta_para_limites_de_palavras(self):
        # Segmento com tempos "de frase" arredondados (10.0-20.0), mas as
        # palavras reais vão de 10.34 a 19.62 — o corte deve seguir as palavras.
        transcricao = {"segments": [{"words": [
            {"start": 10.34, "end": 10.80, "word": "ola"},
            {"start": 11.00, "end": 19.62, "word": "mundo"},
        ]}]}
        refinados = refinar_limites_com_palavras(
            [{"inicio": 10.0, "fim": 20.0}], transcricao,
            pad_inicio_s=0.2, pad_fim_s=0.3,
        )
        self.assertAlmostEqual(refinados[0]["inicio"], 10.14, places=2)
        self.assertAlmostEqual(refinados[0]["fim"], 19.92, places=2)

    def test_refinamento_sem_palavras_mantem_original(self):
        refinados = refinar_limites_com_palavras(
            [{"inicio": 5.0, "fim": 15.0}], {"segments": []}
        )
        self.assertEqual(refinados, [{"inicio": 5.0, "fim": 15.0}])

    def test_refinamento_nunca_gera_inicio_negativo(self):
        transcricao = {"segments": [{"words": [
            {"start": 0.05, "end": 0.5, "word": "oi"},
        ]}]}
        refinados = refinar_limites_com_palavras(
            [{"inicio": 0.0, "fim": 1.0}], transcricao, pad_inicio_s=0.2,
        )
        self.assertGreaterEqual(refinados[0]["inicio"], 0.0)

    def test_ajuste_escolhe_silencio_mais_proximo_nao_o_primeiro(self):
        # Dois silêncios na margem: meio em 9000ms (longe) e 10100ms (perto).
        # O corte em 10000ms deve ir para o mais próximo (10100), não o
        # primeiro da lista (9000).
        silencios = [(8800, 9200), (10000, 10200)]
        ajustados = ajustar_cortes_com_silencio(
            [{"inicio": 10.0, "fim": 30.0}], silencios, margem_ms=1200
        )
        self.assertAlmostEqual(ajustados[0]["inicio"], 10.1, places=2)

    def test_hook_valido_e_aceito(self):
        seg = {"inicio": 10.0, "fim": 70.0, "hook_inicio": 40.0, "hook_fim": 42.5}
        self.assertEqual(validar_hook(seg), (40.0, 42.5))

    def test_hook_no_comeco_do_clipe_e_rejeitado(self):
        # Frase forte já abre o clipe — cold open seria repetição imediata
        seg = {"inicio": 10.0, "fim": 70.0, "hook_inicio": 12.0, "hook_fim": 14.0}
        self.assertIsNone(validar_hook(seg))

    def test_hook_fora_do_clipe_e_rejeitado(self):
        seg = {"inicio": 10.0, "fim": 70.0, "hook_inicio": 80.0, "hook_fim": 82.0}
        self.assertIsNone(validar_hook(seg))

    def test_hook_ausente_ou_nulo_e_rejeitado(self):
        self.assertIsNone(validar_hook({"inicio": 10.0, "fim": 70.0}))
        self.assertIsNone(validar_hook(
            {"inicio": 10.0, "fim": 70.0, "hook_inicio": None, "hook_fim": None}
        ))

    def test_hook_longo_demais_e_rejeitado(self):
        seg = {"inicio": 10.0, "fim": 70.0, "hook_inicio": 30.0, "hook_fim": 45.0}
        self.assertIsNone(validar_hook(seg))

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

    # Resposta simulada da validação FFprobe (v2.3) para testes que usam
    # arquivos falsos — o ffprobe real reprovaria os bytes de mentira e o
    # retry do pipeline dobraria as chamadas de enquadramento.
    _VALIDACAO_OK = {
        "valid": True, "errors": [], "warnings": [],
        "duration": 10.0, "width": 608, "height": 1080, "video_codec": "h264",
    }

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
            "cortes": types.SimpleNamespace(
                cortar_clipe=cortar_clipe,
                cortar_clipe_com_hook=lambda *_a, **_k: False,
                validar_hook=validar_hook,
            ),
            "enquadramento": types.SimpleNamespace(aplicar_enquadramento=aplicar_enquadramento),
            "rostos": types.SimpleNamespace(detectar_quem_fala_por_frame=lambda *_a, **_k: []),
        }

        with tempfile.TemporaryDirectory() as pasta, patch.dict(sys.modules, modulos), \
                patch("pipeline.validar_midia_ffprobe", return_value=dict(self._VALIDACAO_OK)):
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
            "cortes": types.SimpleNamespace(
                cortar_clipe=cortar_clipe,
                cortar_clipe_com_hook=lambda *_a, **_k: False,
                validar_hook=validar_hook,
            ),
            "enquadramento": types.SimpleNamespace(aplicar_enquadramento=aplicar_enquadramento),
            "rostos": types.SimpleNamespace(detectar_quem_fala_por_frame=detectar_falante),
        }

        with tempfile.TemporaryDirectory() as pasta, patch.dict(sys.modules, modulos), \
                patch("pipeline.validar_midia_ffprobe", return_value=dict(self._VALIDACAO_OK)):
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
