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
from enquadramento import (
    _agrupar_posicoes_cena,
    _calcular_x_crop,
    _filtrar_rostos_na_zona_de_cabeca,
    _gerar_plano,
)
from ffmpeg_utils import argumentos_encoder
from pipeline import _fundir_intervalos, _validar_segmentos, sanitizar_nome
from rostos import (
    _caminho_modelo_facial,
    _detectar_movimento_labial,
    _fechar_detector,
    _inicializar_detector,
    _limpar_deteccoes,
    detectar_pessoas_no_video,
    detectar_rostos_robusto,
)
import numpy as np
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

    def test_zona_cabeca_mata_tv_e_estatua_mantem_pessoas(self):
        # Cenário real do Papo Reto: pessoas em Y~0.43/0.57, TV em Y=0.13,
        # estátua em Y=0.25, objetos na mesa em Y=0.79-0.90. Só as duas
        # pessoas devem sobreviver ao filtro de zona.
        rostos = [
            {"x": 0.10, "y": 0.43, "w": 0.05},  # pessoa esquerda
            {"x": 0.94, "y": 0.57, "w": 0.07},  # pessoa direita
            {"x": 0.51, "y": 0.13, "w": 0.10},  # TV (grande mas alta)
            {"x": 0.33, "y": 0.25, "w": 0.07},  # estátua na estante
            {"x": 0.50, "y": 0.90, "w": 0.02},  # objeto na mesa
        ]
        xs, ys = _filtrar_rostos_na_zona_de_cabeca(rostos)
        self.assertEqual(sorted(round(x, 2) for x in xs), [0.10, 0.94])
        grupo = _agrupar_posicoes_cena(xs, ys)
        self.assertEqual(grupo["n_pessoas"], 2)
        self.assertAlmostEqual(grupo["lado_b"], 0.94, delta=0.02)

    def test_zona_cabeca_fallback_quando_ninguem_na_zona(self):
        # Se nenhum rosto está na zona (enquadramento atípico), não descarta
        # tudo — devolve todos como fallback.
        rostos = [
            {"x": 0.30, "y": 0.10, "w": 0.05},
            {"x": 0.70, "y": 0.12, "w": 0.05},
        ]
        xs, ys = _filtrar_rostos_na_zona_de_cabeca(rostos)
        self.assertEqual(len(xs), 2)

    def test_movimento_labial_ambiguo_retorna_none(self):
        # Dois rostos com boca ocluída (mic de mesa): frames quase idênticos,
        # sem movimento real. Antes caía sempre em rostos[0]["x"] — viés
        # sistemático para o mesmo lado. Agora deve retornar None.
        frame_anterior = np.full((200, 200, 3), 100, dtype=np.uint8)
        frame_atual = frame_anterior.copy()
        rostos = [
            {"x": 0.2, "y": 0.4, "w": 0.15, "h": 0.15},
            {"x": 0.8, "y": 0.4, "w": 0.15, "h": 0.15},
        ]
        resultado = _detectar_movimento_labial(frame_atual, frame_anterior, rostos, 200, 200)
        self.assertIsNone(resultado)

    def test_movimento_labial_detecta_lado_correto(self):
        frame_anterior = np.full((200, 200, 3), 100, dtype=np.uint8)
        frame_atual = frame_anterior.copy()
        # Boca do rosto da direita (x=0.8) muda bastante — é quem fala.
        frame_atual[80:140, 140:180] = 220
        rostos = [
            {"x": 0.2, "y": 0.4, "w": 0.15, "h": 0.15},
            {"x": 0.8, "y": 0.4, "w": 0.15, "h": 0.15},
        ]
        resultado = _detectar_movimento_labial(frame_atual, frame_anterior, rostos, 200, 200)
        self.assertEqual(resultado, 0.8)

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

    def test_rosto_esporadico_na_tv_nao_vira_lado(self):
        # Duas pessoas nas bordas aparecem em quase todas as amostras;
        # um rosto na TV central aparece uma vez só — não pode virar lado B.
        xs = [0.10, 0.11, 0.10, 0.12, 0.53, 0.88, 0.87, 0.89, 0.88]
        grupo = _agrupar_posicoes_cena(xs)
        self.assertEqual(grupo["n_pessoas"], 2)
        self.assertAlmostEqual(grupo["lado_a"], 0.11, delta=0.03)
        self.assertAlmostEqual(grupo["lado_b"], 0.88, delta=0.03)

    def test_solo_nao_trava_quando_so_um_lado_registra_fala(self):
        # Cena de 2 pessoas em que o detector de fala só enxerga o lado B
        # (rosto pequeno/perfil nunca registra) — o SOLO_B não pode durar
        # até o fim da cena: precisa voltar ao SPLIT periodicamente.
        fps = 30.0
        total = 900  # 30s
        cenas = [{
            "frame_ini": 0, "frame_fim": total, "n_pessoas": 2,
            "lado_a": 0.10, "lado_b": 0.60,
            "lado_a_y": 0.40, "lado_b_y": 0.40,
        }]
        posicoes = [0.60] * total  # toda fala atribuída ao lado B
        plano = _gerar_plano(cenas, posicoes, fps, total)
        modos = [p["modo"] for p in plano]
        self.assertIn("SOLO_B", modos)  # fala exclusiva leva ao solo
        # Depois do primeiro solo, o split volta em algum momento
        primeiro_solo = modos.index("SOLO_B")
        self.assertIn("SPLIT", modos[primeiro_solo:])
        # E nenhum trecho contínuo de SOLO passa do teto configurado
        max_seguidos = seguidos = 0
        for m in modos:
            seguidos = seguidos + 1 if m == "SOLO_B" else 0
            max_seguidos = max(max_seguidos, seguidos)
        import enquadramento
        teto = int(fps * enquadramento.TEMPO_MAXIMO_SOLO_EM_DUPLA) + int(fps)
        self.assertLessEqual(max_seguidos, teto)

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

    def test_robusto_nao_cai_no_haar_se_mediapipe_acha_na_tentativa_3(self):
        # Bug real (Papo Reto, plano aberto): MediaPipe falhava no frame
        # original, e o Haar embutido no detector "combinado" disparava já
        # na tentativa 1 antes de tentar o zoom 2x/3x — o Haar então
        # "achava" rosto numa estatueta do cenário. As 3 tentativas de
        # MediaPipe devem esgotar ANTES de qualquer chamada ao Haar.
        detector = {"tipo": "combinado", "mediapipe": {"tipo": "novo"}, "haar": object()}
        frame = np.zeros((20, 20, 3), dtype=np.uint8)

        # tentativa 1 (original) e 2 (2x) vazias; tentativa 3 varre as duas
        # metades e só acha rosto na esquerda — mesmo assim não deve cair
        # no Haar, já que a tentativa 3 inteira roda antes dessa decisão.
        respostas = [[], [], [{"x": 0.2, "y": 0.4, "w": 0.1, "h": 0.1}], []]
        with patch("rostos._detectar_rostos_frame", side_effect=respostas) as mock_mp, \
                patch("rostos._detectar_rostos_haar") as mock_haar:
            rostos = detectar_rostos_robusto(frame, detector)

        self.assertEqual(mock_mp.call_count, 4)  # original, 2x, metade-esq, metade-dir
        mock_haar.assert_not_called()
        self.assertEqual(len(rostos), 1)
        self.assertAlmostEqual(rostos[0]["x"], 0.1, delta=0.001)

    def test_robusto_cai_no_haar_so_apos_mediapipe_esgotar(self):
        detector = {"tipo": "combinado", "mediapipe": {"tipo": "novo"}, "haar": object()}
        frame = np.zeros((20, 20, 3), dtype=np.uint8)

        with patch("rostos._detectar_rostos_frame", return_value=[]) as mock_mp, \
                patch("rostos._detectar_rostos_haar", return_value=[{"x": 0.5, "y": 0.5, "w": 0.1, "h": 0.1}]) as mock_haar:
            rostos = detectar_rostos_robusto(frame, detector)

        self.assertEqual(mock_mp.call_count, 4)  # original, 2x, metade-esq, metade-dir
        mock_haar.assert_called_once()
        self.assertEqual(len(rostos), 1)

if __name__ == "__main__":
    unittest.main()
