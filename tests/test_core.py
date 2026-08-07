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
    _calcular_crop_seguro,
    _classificar_modos_fala,
    _compor_frame_seguro,
    _filtrar_rostos_na_zona_de_cabeca,
    _gerar_plano,
)
from ffmpeg_utils import argumentos_encoder
from pipeline import _fundir_intervalos, _validar_segmentos, sanitizar_nome
from rostos import (
    NOME_MODELO_SFACE,
    URL_MODELO_SFACE,
    _caminho_modelo_facial,
    _detectar_movimento_labial,
    _fechar_detector,
    _filtrar_candidatos_pessoas,
    _agrupar_por_identidade,
    _caminho_modelo_reconhecimento,
    _inicializar_detector,
    _escolher_fallback_humano,
    _limpar_deteccoes,
    detectar_pessoas_no_video,
    detectar_rostos_robusto,
)
import numpy as np
import rostos
class TestCore(unittest.TestCase):
    def test_modelo_sface_compativel_com_extracao_de_embeddings(self):
        self.assertEqual(NOME_MODELO_SFACE, "face_recognition_sface_2021dec.onnx")
        self.assertNotIn("int8", URL_MODELO_SFACE.lower())

    def test_rodadas_adaptativas_chegam_depois_de_introducao_longa(self):
        rodadas = rostos._planejar_rodadas_amostragem(30 * 60 * 60, 30.0, 30, 5.0)
        self.assertLess(max(rodadas[0]), 5 * 60 * 30)
        self.assertGreater(max(max(r) for r in rodadas), 45 * 60 * 30)
        self.assertEqual(len({f for r in rodadas for f in r}), sum(map(len, rodadas)))

    def test_busca_estavel_exige_identidades_repetidas(self):
        self.assertFalse(rostos._busca_esta_estavel([(), (), (), ()], 3))
        self.assertTrue(rostos._busca_esta_estavel([("a", "b")] * 3, 3))
        self.assertFalse(rostos._busca_esta_estavel([("a",), ("a",), ("a", "b"), ("a", "b")], 3))

    def test_assinaturas_preservam_duas_pessoas_do_mesmo_lado(self):
        pessoas = [{"id": 0, "lado": "esquerda"}, {"id": 1, "lado": "esquerda"}]
        self.assertEqual(len(rostos._assinaturas_pessoas(pessoas)), 2)

    def test_assinatura_de_identidade_ignora_troca_de_lado(self):
        esquerda = [{"id": 0, "lado": "esquerda"}, {"id": 1, "lado": "direita"}]
        centro = [{"id": 0, "lado": "centro"}, {"id": 1, "lado": "esquerda"}]
        self.assertEqual(rostos._assinaturas_pessoas(esquerda), rostos._assinaturas_pessoas(centro))

    def test_recorte_facial_vazio_nao_vira_preview(self):
        deteccoes = [{"recorte_identidade": np.empty((0, 0, 3), np.uint8)}]
        self.assertEqual(rostos._remover_identidades_sem_rosto_valido(deteccoes), [])

    def test_modelo_facial_tem_caminho_persistente(self):
        self.assertTrue(_caminho_modelo_facial().endswith("face_detector.tflite"))

    def test_modelo_de_identidade_tem_caminho_persistente(self):
        self.assertTrue(_caminho_modelo_reconhecimento().endswith(".onnx"))

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
        # CenÃ¡rio real do Papo Reto: pessoas em Y~0.43/0.57, TV em Y=0.13,
        # estÃ¡tua em Y=0.25, objetos na mesa em Y=0.79-0.90. SÃ³ as duas
        # pessoas devem sobreviver ao filtro de zona.
        rostos = [
            {"x": 0.10, "y": 0.43, "w": 0.05},  # pessoa esquerda
            {"x": 0.94, "y": 0.57, "w": 0.07},  # pessoa direita
            {"x": 0.51, "y": 0.13, "w": 0.10},  # TV (grande mas alta)
            {"x": 0.33, "y": 0.25, "w": 0.07},  # estÃ¡tua na estante
            {"x": 0.50, "y": 0.90, "w": 0.02},  # objeto na mesa
        ]
        xs, ys, ws = _filtrar_rostos_na_zona_de_cabeca(rostos)
        self.assertEqual(sorted(round(x, 2) for x in xs), [0.10, 0.94])
        grupo = _agrupar_posicoes_cena(xs, ys, ws)
        self.assertEqual(grupo["n_pessoas"], 2)
        self.assertAlmostEqual(grupo["lado_b"], 0.94, delta=0.02)

    def test_zona_cabeca_fallback_quando_ninguem_na_zona(self):
        # Se nenhum rosto estÃ¡ na zona (enquadramento atÃ­pico), nÃ£o descarta
        # tudo â€” devolve todos como fallback.
        rostos = [
            {"x": 0.30, "y": 0.10, "w": 0.05},
            {"x": 0.70, "y": 0.12, "w": 0.05},
        ]
        xs, ys, ws = _filtrar_rostos_na_zona_de_cabeca(rostos)
        self.assertEqual(len(xs), 2)

    def test_multiplas_pessoas_iniciam_na_primeira_pessoa_nao_no_centro(self):
        pessoas = [{"posicao_x": 0.25}, {"posicao_x": 0.75}]
        self.assertEqual(_escolher_fallback_humano(pessoas, ultimo=None), 0.25)

    def test_sem_pessoa_validada_falha_em_vez_de_centralizar(self):
        with self.assertRaises(RuntimeError):
            _escolher_fallback_humano([], ultimo=None)
    def test_movimento_labial_ambiguo_retorna_none(self):
        # Dois rostos com boca ocluÃ­da (mic de mesa): frames quase idÃªnticos,
        # sem movimento real. Antes caÃ­a sempre em rostos[0]["x"] â€” viÃ©s
        # sistemÃ¡tico para o mesmo lado. Agora deve retornar None.
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
        # Boca do rosto da direita (x=0.8) muda bastante â€” Ã© quem fala.
        frame_atual[80:140, 140:180] = 220
        rostos = [
            {"x": 0.2, "y": 0.4, "w": 0.15, "h": 0.15},
            {"x": 0.8, "y": 0.4, "w": 0.15, "h": 0.15},
        ]
        resultado = _detectar_movimento_labial(frame_atual, frame_anterior, rostos, 200, 200)
        self.assertEqual(resultado, 0.8)

    def test_filtro_de_pessoas_remove_tv_e_deteccao_esporadica(self):
        deteccoes = [
            # Pessoa real: aparece em trÃªs amostras na zona humana.
            *[
                {"posicao_x": 0.16, "posicao_y": 0.46, "frame_idx": f, "fonte": "mediapipe"}
                for f in (1, 2, 3)
            ],
            # Rosto no telÃ£o: persistente, mas alto demais no quadro.
            *[
                {"posicao_x": 0.52, "posicao_y": 0.12, "frame_idx": f, "fonte": "mediapipe"}
                for f in (1, 2, 3, 4, 5)
            ],
            # Falso positivo isolado dentro da zona.
            {"posicao_x": 0.84, "posicao_y": 0.48, "frame_idx": 2, "fonte": "haar"},
        ]
        filtradas = _filtrar_candidatos_pessoas(deteccoes, total_amostras=30)
        self.assertEqual({round(d["posicao_x"], 2) for d in filtradas}, {0.16})

    def test_filtro_nao_promove_haar_fora_da_zona_humana(self):
        deteccoes = [
            {"posicao_x": 0.5, "posicao_y": 0.14, "frame_idx": f, "fonte": "haar"}
            for f in range(10)
        ]
        self.assertEqual(_filtrar_candidatos_pessoas(deteccoes, 30), [])

    def test_identidade_une_mesma_pessoa_em_lados_diferentes(self):
        class ReconhecedorFake:
            def feature(self, imagem):
                return np.array([[1.0, 0.0]]) if float(imagem.mean()) < 100 else np.array([[0.0, 1.0]])

            def match(self, a, b, _metrica):
                return float(np.dot(a.ravel(), b.ravel()))

        deteccoes = []
        for frame, x in ((1, 0.20), (2, 0.50), (3, 0.78)):
            deteccoes.append({
                "posicao_x": x, "posicao_y": 0.45, "frame_idx": frame,
                "recorte": np.full((40, 40, 3), 20, dtype=np.uint8),
            })
        for frame, x in ((1, 0.75), (2, 0.70), (3, 0.65)):
            deteccoes.append({
                "posicao_x": x, "posicao_y": 0.45, "frame_idx": frame,
                "recorte": np.full((40, 40, 3), 200, dtype=np.uint8),
            })

        pessoas = _agrupar_por_identidade(deteccoes, ReconhecedorFake(), total_amostras=6)
        self.assertEqual(len(pessoas), 2)
        self.assertEqual(sorted(p["n_aparicoes"] for p in pessoas), [3, 3])
    def test_identidade_passageira_nao_vira_participante(self):
        class ReconhecedorFake:
            def feature(self, imagem):
                return np.array([[1.0, 0.0]]) if float(imagem.mean()) < 100 else np.array([[0.0, 1.0]])
            def match(self, a, b, _metrica):
                return float(np.dot(a.ravel(), b.ravel()))
        deteccoes = []
        for frame in range(15):
            deteccoes.append({"posicao_x": 0.25, "posicao_y": 0.45, "frame_idx": frame,
                              "recorte": np.full((40, 40, 3), 20, dtype=np.uint8)})
        for frame in range(4):
            deteccoes.append({"posicao_x": 0.75, "posicao_y": 0.45, "frame_idx": frame,
                              "recorte": np.full((40, 40, 3), 200, dtype=np.uint8)})
        pessoas = _agrupar_por_identidade(deteccoes, ReconhecedorFake(), total_amostras=100)
        self.assertEqual(len(pessoas), 1)
        self.assertEqual(pessoas[0]["n_aparicoes"], 15)
    def test_identidade_cai_para_posicao_quando_sface_nao_extrai_embeddings(self):
        class ReconhecedorSemEmbedding:
            def feature(self, _imagem):
                return None

        deteccoes = []
        for frame in (1, 2, 3):
            for x in (0.2, 0.8):
                deteccoes.append({
                    "posicao_x": x,
                    "posicao_y": 0.45,
                    "frame_idx": frame,
                    "recorte": np.full((40, 40, 3), 80, dtype=np.uint8),
                })

        pessoas = _agrupar_por_identidade(
            deteccoes, ReconhecedorSemEmbedding(), total_amostras=6
        )

        self.assertEqual(len(pessoas), 2)
        self.assertEqual(sorted(p["n_aparicoes"] for p in pessoas), [3, 3])

    def test_silencios_viram_intervalos_de_fala_com_respiro(self):
        intervalos = calcular_intervalos_fala(
            10000, [(2000, 4000), (7000, 8000)], margem_ms=100
        )
        self.assertEqual(intervalos, [(0, 2100), (3900, 7100), (7900, 10000)])

    def test_refinamento_ajusta_para_limites_de_palavras(self):
        # Segmento com tempos "de frase" arredondados (10.0-20.0), mas as
        # palavras reais vÃ£o de 10.34 a 19.62 â€” o corte deve seguir as palavras.
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
        # Dois silÃªncios na margem: meio em 9000ms (longe) e 10100ms (perto).
        # O corte em 10000ms deve ir para o mais prÃ³ximo (10100), nÃ£o o
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
        # Frase forte jÃ¡ abre o clipe â€” cold open seria repetiÃ§Ã£o imediata
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

    def test_conversa_alternada_mantem_split(self):
        modos = _classificar_modos_fala([0.25, 0.75] * 60, 0.25, 0.75, fps=30)
        self.assertEqual(set(modos), {"SPLIT"})

    def test_tres_segundos_da_mesma_pessoa_destacam_solo(self):
        modos = _classificar_modos_fala([0.25] * 91, 0.25, 0.75, fps=30)
        self.assertEqual(modos[89], "SOLO_A")

    def test_retomada_da_outra_pessoa_volta_ao_split(self):
        modos = _classificar_modos_fala([0.25] * 91 + [0.75], 0.25, 0.75, fps=30)
        self.assertEqual(modos[-1], "SPLIT")

    def test_crop_solo_preserva_margem_do_rosto_na_borda(self):
        x, _y, w, _h = _calcular_crop_seguro(
            [(0.08, 0.38, 0.08)], 1920, 1080, 9 / 16
        )
        self.assertEqual(x, 0)
        self.assertGreaterEqual(w, 608)

    def test_crop_grupo_contem_as_duas_pessoas(self):
        x, _y, w, _h = _calcular_crop_seguro(
            [(0.30, 0.40, 0.08), (0.58, 0.42, 0.08)],
            1920, 1080, 9 / 16,
        )
        self.assertLessEqual(x, int(0.30 * 1920))
        self.assertGreaterEqual(x + w, int(0.58 * 1920))
    def test_split_compoe_dois_paineis_com_crops_independentes(self):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        frame[:, :320] = (0, 0, 220)
        frame[:, 320:] = (220, 0, 0)
        plano = {
            "modo": "SPLIT", "xa": 0.25, "xb": 0.75,
            "ya": 0.40, "yb": 0.40, "ta": 0.08, "tb": 0.08,
        }
        saida = _compor_frame_seguro(frame, plano, 360, 640)
        self.assertEqual(saida.shape, (640, 360, 3))
        self.assertGreater(saida[:320, :, 2].mean(), saida[:320, :, 0].mean())
        self.assertGreater(saida[320:, :, 0].mean(), saida[320:, :, 2].mean())
    def test_crop_fica_dentro_do_frame(self):
        self.assertEqual(_calcular_x_crop(0.0, 1920, 608), 0)
        self.assertEqual(_calcular_x_crop(1.0, 1920, 608), 1312)

    def test_duas_pessoas_sao_separadas(self):
        grupo = _agrupar_posicoes_cena([0.2, 0.22, 0.78, 0.8])
        self.assertEqual(grupo["n_pessoas"], 2)

    def test_rosto_esporadico_na_tv_nao_vira_lado(self):
        # Duas pessoas nas bordas aparecem em quase todas as amostras;
        # um rosto na TV central aparece uma vez sÃ³ â€” nÃ£o pode virar lado B.
        xs = [0.10, 0.11, 0.10, 0.12, 0.53, 0.88, 0.87, 0.89, 0.88]
        grupo = _agrupar_posicoes_cena(xs)
        self.assertEqual(grupo["n_pessoas"], 2)
        self.assertAlmostEqual(grupo["lado_a"], 0.11, delta=0.03)
        self.assertAlmostEqual(grupo["lado_b"], 0.88, delta=0.03)

    def test_plano_de_conversa_alternada_usa_split(self):
        total = 120
        cenas = [{
            "frame_ini": 0, "frame_fim": total, "n_pessoas": 2,
            "lado_a": 0.20, "lado_b": 0.80,
            "lado_a_y": 0.40, "lado_b_y": 0.42,
            "lado_a_tam": 0.08, "lado_b_tam": 0.08,
        }]
        plano = _gerar_plano(cenas, [0.20, 0.80] * 60, 30.0, total)
        self.assertEqual({p["modo"] for p in plano}, {"SPLIT"})
        self.assertTrue(all(p["xa"] == 0.20 and p["xb"] == 0.80 for p in plano))

    def test_plano_destaca_solo_depois_de_tres_segundos(self):
        total = 91
        cenas = [{
            "frame_ini": 0, "frame_fim": total, "n_pessoas": 2,
            "lado_a": 0.20, "lado_b": 0.80,
            "lado_a_y": 0.40, "lado_b_y": 0.42,
            "lado_a_tam": 0.08, "lado_b_tam": 0.08,
        }]
        plano = _gerar_plano(cenas, [0.20] * total, 30.0, total)
        self.assertEqual(plano[88]["modo"], "SPLIT")
        self.assertEqual(plano[89]["modo"], "SOLO_A")

    def test_crop_de_rosto_pequeno_mantem_plano_aberto(self):
        _x, _y, w, h = _calcular_crop_seguro(
            [(0.50, 0.38, 0.03)], 1920, 1080, 9 / 16
        )
        self.assertGreaterEqual(w, 516)
        self.assertGreaterEqual(h, 918)
    def test_duas_pessoas_segue_quem_fala_nao_posicao_de_rosto(self):
        # Cena de 2+ pessoas ignora lado_a/lado_b (posiÃ§Ã£o de rosto por
        # cena podia mirar num objeto decorativo â€” ver seÃ§Ã£o 10/11 do
        # RELATORIO_COMPLETO_2026-07-03.md). O alvo do crop Ã© a posiÃ§Ã£o de
        # QUEM FALA, mesmo que ela nÃ£o bata com lado_a nem lado_b.
        fps = 30.0
        total = 900  # 30s
        cenas = [{
            "frame_ini": 0, "frame_fim": total, "n_pessoas": 2,
            "lado_a": 0.10, "lado_b": 0.60,
            "lado_a_y": 0.40, "lado_b_y": 0.40,
        }]
        posicoes = [0.72] * total  # fala detectada numa posiÃ§Ã£o real, fora de lado_a/lado_b
        plano = _gerar_plano(cenas, posicoes, fps, total)
        self.assertEqual(plano[0]["modo"], "SPLIT")
        self.assertEqual(plano[89]["modo"], "SOLO_B")
        self.assertTrue(all(p["xa"] in (0.10, 0.60) for p in plano))

    def test_duas_pessoas_mantem_ultimo_alvo_no_silencio(self):
        # Sem fala detectada num trecho, o crop nÃ£o pula pro centro â€”
        # mantÃ©m o Ãºltimo alvo vÃ¡lido (evita corte nervoso em pausas).
        fps = 30.0
        total = 300  # 10s
        cenas = [{
            "frame_ini": 0, "frame_fim": total, "n_pessoas": 2,
            "lado_a": 0.10, "lado_b": 0.60,
            "lado_a_y": 0.40, "lado_b_y": 0.40,
        }]
        posicoes = [0.72] * 150 + [None] * 150  # fala, depois silÃªncio
        plano = _gerar_plano(cenas, posicoes, fps, total)
        self.assertEqual(plano[149]["modo"], "SOLO_B")
        self.assertEqual(plano[-1]["modo"], "SOLO_B")
        self.assertEqual(plano[-1]["xa"], 0.60)

    def test_encoder_tem_codec_definido(self):
        argumentos = argumentos_encoder()
        self.assertIn("-c:v", argumentos)

    def test_deteccoes_duplicadas_sao_removidas(self):
        rostos = _limpar_deteccoes([
            {"x": 0.3, "y": 0.3, "w": 0.1, "h": 0.1},
            {"x": 0.31, "y": 0.31, "w": 0.1, "h": 0.1},
        ])
        self.assertEqual(len(rostos), 1)

    def test_deteccoes_multiescala_da_mesma_face_sao_unificadas(self):
        rostos = _limpar_deteccoes([
            {"x": 0.51, "y": 0.47, "w": 0.61, "h": 0.61, "confianca": 0.8},
            {"x": 0.74, "y": 0.46, "w": 0.47, "h": 0.47, "confianca": 0.6},
        ])
        self.assertEqual(len(rostos), 1)

    def test_dois_rostos_realmente_separados_nao_sao_unificados(self):
        rostos = _limpar_deteccoes([
            {"x": 0.25, "y": 0.45, "w": 0.18, "h": 0.18},
            {"x": 0.75, "y": 0.45, "w": 0.18, "h": 0.18},
        ])
        self.assertEqual(len(rostos), 2)

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

    # Resposta simulada da validaÃ§Ã£o FFprobe (v2.3) para testes que usam
    # arquivos falsos â€” o ffprobe real reprovaria os bytes de mentira e o
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
        # original, e o Haar embutido no detector "combinado" disparava jÃ¡
        # na tentativa 1 antes de tentar o zoom 2x/3x â€” o Haar entÃ£o
        # "achava" rosto numa estatueta do cenÃ¡rio. As 3 tentativas de
        # MediaPipe devem esgotar ANTES de qualquer chamada ao Haar.
        detector = {"tipo": "combinado", "mediapipe": {"tipo": "novo"}, "haar": object()}
        frame = np.zeros((20, 20, 3), dtype=np.uint8)

        # tentativa 1 (original) e 2 (2x) vazias; tentativa 3 varre as duas
        # metades e sÃ³ acha rosto na esquerda â€” mesmo assim nÃ£o deve cair
        # no Haar, jÃ¡ que a tentativa 3 inteira roda antes dessa decisÃ£o.
        respostas = [[], [], [{"x": 0.2, "y": 0.4, "w": 0.1, "h": 0.1}], []]
        with patch("rostos._detectar_rostos_frame", side_effect=respostas) as mock_mp, \
                patch("rostos._detectar_rostos_haar") as mock_haar:
            rostos = detectar_rostos_robusto(frame, detector)

        self.assertEqual(mock_mp.call_count, 4)  # original, 2x, metade-esq, metade-dir
        mock_haar.assert_not_called()
        self.assertEqual(len(rostos), 1)
        self.assertAlmostEqual(rostos[0]["x"], 0.1, delta=0.001)

    def test_robusto_combina_rosto_proximo_com_rosto_que_so_aparece_no_zoom(self):
        detector = {"tipo": "combinado", "mediapipe": {"tipo": "novo"}, "haar": object()}
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        esquerda = {"x": 0.2, "y": 0.45, "w": 0.10, "h": 0.10, "fonte": "mediapipe"}
        direita = {"x": 0.8, "y": 0.45, "w": 0.08, "h": 0.08, "fonte": "mediapipe"}
        respostas = [
            [esquerda],
            [esquerda, direita],
            [{"x": 0.4, "y": 0.45, "w": 0.20, "h": 0.10, "fonte": "mediapipe"}],
            [{"x": 0.6, "y": 0.45, "w": 0.16, "h": 0.08, "fonte": "mediapipe"}],
        ]
        with patch("rostos._detectar_rostos_frame", side_effect=respostas) as mock_mp, \
                patch("rostos._detectar_rostos_haar") as mock_haar:
            rostos = detectar_rostos_robusto(frame, detector)

        self.assertEqual(mock_mp.call_count, 4)
        mock_haar.assert_not_called()
        self.assertEqual(sorted(round(r["x"], 1) for r in rostos), [0.2, 0.8])

    def test_robusto_nao_inventa_rosto_com_haar_quando_mediapipe_esta_ativo(self):
        detector = {"tipo": "combinado", "mediapipe": {"tipo": "novo"}, "haar": object()}
        frame = np.zeros((20, 20, 3), dtype=np.uint8)

        with patch("rostos._detectar_rostos_frame", return_value=[]) as mock_mp, \
                patch("rostos._detectar_rostos_haar", return_value=[{"x": 0.5, "y": 0.5, "w": 0.1, "h": 0.1}]) as mock_haar:
            rostos = detectar_rostos_robusto(frame, detector)

        self.assertEqual(mock_mp.call_count, 4)  # original, 2x, metade-esq, metade-dir
        mock_haar.assert_not_called()
        self.assertEqual(rostos, [])

    def test_robusto_usa_haar_se_mediapipe_nao_carregou(self):
        detector = {"tipo": "combinado", "mediapipe": None, "haar": object()}
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        esperado = [{"x": 0.5, "y": 0.5, "w": 0.1, "h": 0.1}]
        with patch("rostos._detectar_rostos_haar", return_value=esperado) as mock_haar:
            rostos = detectar_rostos_robusto(frame, detector)

        mock_haar.assert_called_once()
        self.assertEqual(len(rostos), 1)

if __name__ == "__main__":
    unittest.main()






