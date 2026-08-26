"""Testes da regra definitiva de enquadramento seguro (nenhuma pessoa cortada)."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import enquadramento as enq


LARGURA, ALTURA = 1920, 1080
SAIDA_W, SAIDA_H = 1080, 1920


def _validar_layout(layout, alvos):
    """Confere que todo alvo cabe com margem em pelo menos um painel do layout."""
    caixas = enq._caixas_humanas(alvos, LARGURA, ALTURA)
    if layout["tipo"] == "solo":
        crops = [layout["crop"]]
    else:
        crops = [layout["top_crop"], layout["bot_crop"]]
    for caixa in caixas:
        assert any(
            enq._validar_crop_alvos(c, [caixa], LARGURA, ALTURA)[0] for c in crops
        ), f"caixa {caixa} cortada em {layout}"


def test_caixa_humana_ignores_unreliable_face():
    assert enq._caixa_humana((0.5, 0.5, 0.0), LARGURA, ALTURA) is None
    assert enq._caixa_humana((0.5, 0.5, 0.001), LARGURA, ALTURA) is None


def test_caixa_humana_stays_inside_source_frame():
    x0, y0, x1, y1 = enq._caixa_humana((0.02, 0.35, 0.08), LARGURA, ALTURA)
    assert 0.0 <= x0 < x1 <= LARGURA
    assert 0.0 <= y0 < y1 <= ALTURA


def test_crop_rejects_person_touching_the_edge():
    crop = (0, 0, 600, 1080)  # borda direita do crop cai no meio da pessoa
    caixa = (500.0, 200.0, 800.0, 900.0)
    ok, motivo = enq._validar_crop_alvos(crop, [caixa], LARGURA, ALTURA)
    assert not ok
    assert motivo == "pessoa_cortada_na_direita"


def test_crop_accepts_person_with_margin():
    crop = (0, 0, 900, 1080)
    caixa = (200.0, 200.0, 600.0, 1000.0)
    ok, _ = enq._validar_crop_alvos(crop, [caixa], LARGURA, ALTURA)
    assert ok


def test_crop_at_source_border_is_allowed():
    """Pessoa ja cortada na fonte nao invalida um crop colado na mesma borda."""
    crop = (0, 0, 900, 1080)
    caixa = (0.0, 200.0, 400.0, 1000.0)
    ok, _ = enq._validar_crop_alvos(crop, [caixa], LARGURA, ALTURA)
    assert ok


def test_solo_shot_keeps_person_whole():
    plano = {"modo": "SOLO_A", "xa": 0.30, "ya": 0.42, "ta": 0.07}
    relatorio = {}
    layout = enq._calcular_filtros_shot(
        plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H, relatorio=relatorio
    )
    _validar_layout(layout, [(0.30, 0.42, 0.07)])
    assert not relatorio.get("revisar")


def test_solo_near_border_is_recentered_not_cut():
    plano = {"modo": "SOLO_A", "xa": 0.06, "ya": 0.42, "ta": 0.06}
    layout = enq._calcular_filtros_shot(plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H)
    x, _, w, _ = layout["crop"]
    assert x == 0  # encosta na borda da fonte, sem cortar o que existe
    _validar_layout(layout, [(0.06, 0.42, 0.06)])


def test_two_distant_people_degrade_to_split():
    plano = {
        "modo": "GRUPO",
        "xa": 0.15, "ya": 0.45, "ta": 0.06,
        "xb": 0.85, "yb": 0.45, "tb": 0.06,
    }
    relatorio = {}
    layout = enq._calcular_filtros_shot(
        plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H, relatorio=relatorio
    )
    assert layout["tipo"] == "split"
    assert not relatorio.get("revisar")
    _validar_layout(layout, [(0.15, 0.45, 0.06), (0.85, 0.45, 0.06)])


def test_split_panels_fill_the_whole_output():
    plano = {
        "modo": "SPLIT",
        "xa": 0.25, "ya": 0.45, "ta": 0.06,
        "xb": 0.75, "yb": 0.45, "tb": 0.06,
    }
    layout = enq._calcular_filtros_shot(plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H)
    assert layout["top_scale"][1] + layout["bot_scale"][1] == SAIDA_H
    assert layout["top_scale"][0] == layout["bot_scale"][0] == SAIDA_W


def test_scene_without_faces_is_not_flagged_for_review():
    plano = {"modo": "SOLO_A", "xa": 0.5, "ya": 0.40, "ta": 0.0}
    relatorio = {}
    enq._calcular_filtros_shot(
        plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H, relatorio=relatorio
    )
    assert not relatorio.get("revisar")
    assert "cena_sem_rosto_confiavel" in relatorio["motivos"]


def test_no_safe_crop_falls_back_to_the_open_frame():
    """Regra do usuario: na duvida, quadro aberto — nunca um crop arriscado."""
    plano = {"modo": "SOLO_A", "xa": 0.5, "ya": 0.5, "ta": 0.25}
    relatorio = {}
    layout = enq._calcular_filtros_shot(
        plano, 960, 540, SAIDA_W, SAIDA_H, relatorio=relatorio
    )
    assert layout["modo_final"] == "ABERTO"
    assert "quadro_aberto_por_seguranca" in relatorio["motivos"]
    assert not relatorio.get("revisar")


def test_both_engines_share_the_same_layout():
    """O compositor por pipe usa exatamente o layout validado do motor FFmpeg."""
    plano = {
        "modo": "GRUPO",
        "xa": 0.15, "ya": 0.45, "ta": 0.06,
        "xb": 0.85, "yb": 0.45, "tb": 0.06,
    }
    frame = np.zeros((ALTURA, LARGURA, 3), dtype=np.uint8)
    layout = enq._calcular_filtros_shot(plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H)
    composto = enq._compor_frame_seguro(frame, plano, SAIDA_W, SAIDA_H)
    assert composto.shape == (SAIDA_H, SAIDA_W, 3)
    assert layout["tipo"] == "split"


def test_composed_frame_has_exact_output_size_in_every_mode():
    frame = np.zeros((ALTURA, LARGURA, 3), dtype=np.uint8)
    for modo in ("SOLO_A", "SOLO_B", "GRUPO", "SPLIT", "FALLBACK_SPLIT"):
        plano = {
            "modo": modo,
            "xa": 0.30, "ya": 0.45, "ta": 0.06,
            "xb": 0.70, "yb": 0.45, "tb": 0.06,
        }
        composto = enq._compor_frame_seguro(frame, plano, SAIDA_W, SAIDA_H)
        assert composto.shape == (SAIDA_H, SAIDA_W, 3), modo


def test_crop_dimensions_are_even_for_h264():
    plano = {"modo": "SOLO_A", "xa": 0.4, "ya": 0.45, "ta": 0.06}
    layout = enq._calcular_filtros_shot(plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H)
    _, _, w, h = layout["crop"]
    assert w % 2 == 0 and h % 2 == 0


def test_resume_keeps_review_clips_out_of_ready_count(tmp_path, monkeypatch):
    """Retomada nao promove clipe em revisao a 'pronto' so porque o arquivo existe."""
    import checkpoint as ckp
    from checkpoint import inspecionar_retomada

    monkeypatch.setattr(ckp, "resultado_valido", lambda r: bool(r and r.get("arquivo")))

    arquivo = tmp_path / "01_clipe.mp4"
    arquivo.write_bytes(b"\0" * 70000)
    checkpoint = {
        "clipes": {
            "1": {
                "status": "revisar",
                "resultado": {"arquivo": str(arquivo), "revisar": True},
            }
        }
    }
    segmentos = [{"inicio": 0, "fim": 10, "titulo": "clipe"}]

    inventario = inspecionar_retomada(checkpoint, str(tmp_path), segmentos)

    assert inventario["em_revisao"] == [1]
    assert inventario["prontos"] == []


def test_spurious_second_face_does_not_become_side_b():
    """Rosto espurio ao lado do falante nao vira 'lado B' (caso real Papo Reto)."""
    # Medido no clipe 08: A em 0.495 (rosto 0.168) e B em 0.714 (rosto 0.0905).
    xs = [0.49, 0.495, 0.50, 0.71, 0.714, 0.72]
    ys = [0.31, 0.31, 0.31, 0.33, 0.33, 0.33]
    ws = [0.168, 0.168, 0.168, 0.0905, 0.0905, 0.0905]

    grupo = enq._agrupar_posicoes_cena(xs, ys, ws)

    assert grupo["n_pessoas"] == 1
    assert grupo["lado_a"] == grupo["lado_b"]


def test_two_real_people_are_still_detected_as_two():
    xs = [0.22, 0.23, 0.24, 0.74, 0.75, 0.76]
    ys = [0.45] * 6
    ws = [0.07] * 6

    grupo = enq._agrupar_posicoes_cena(xs, ys, ws)

    assert grupo["n_pessoas"] == 2
    assert grupo["lado_a"] < grupo["lado_b"]


def test_incompatible_face_sizes_are_not_two_people():
    """Rosto do fundo (bem menor) nao vira o segundo painel do split."""
    xs = [0.30, 0.31, 0.32, 0.80, 0.81, 0.82]
    ys = [0.45] * 6
    ws = [0.10, 0.10, 0.10, 0.025, 0.025, 0.025]

    assert enq._agrupar_posicoes_cena(xs, ys, ws)["n_pessoas"] == 1


def test_implausibly_large_face_is_discarded():
    """Falso positivo gigante (clipe 13 do Papo Reto) nao vira alvo de crop."""
    assert enq._caixa_cabeca((0.814, 0.55, 0.358), LARGURA, ALTURA) is None
    assert enq._caixa_humana((0.814, 0.55, 0.358), LARGURA, ALTURA) is None


def test_open_shot_with_bogus_face_falls_back_to_center_not_review():
    plano = {"modo": "SOLO_A", "xa": 0.814, "ya": 0.55, "ta": 0.358}
    relatorio = {}
    layout = enq._calcular_filtros_shot(
        plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H, relatorio=relatorio
    )
    assert not relatorio.get("revisar")
    assert layout["tipo"] == "solo"
    assert "cena_sem_rosto_confiavel" in relatorio["motivos"]


def test_a_real_close_up_is_still_a_valid_target():
    """O teto nao pode descartar close legitimo: 0.25 continua valendo."""
    assert enq._caixa_cabeca((0.5, 0.45, 0.25), LARGURA, ALTURA) is not None


def test_open_frame_uses_the_full_height_and_centers_on_the_person():
    """O quadro aberto nao fecha mais que a altura da fonte."""
    layout = enq._quadro_aberto(
        [(0.30, 0.45, 0.08), (0.30, 0.45, 0.08)], LARGURA, ALTURA,
        SAIDA_W, SAIDA_H,
    )
    x, y, w, h = layout["crop"]
    assert h == ALTURA          # altura inteira: sem zoom
    assert y == 0
    assert 0 <= x <= LARGURA - w
    # centralizado na pessoa, nao no meio do quadro
    assert abs((x + w / 2) - 0.30 * LARGURA) < w / 2


def test_open_frame_without_faces_stays_centered():
    layout = enq._quadro_aberto([(0.5, 0.4, 0.0)], LARGURA, ALTURA, SAIDA_W, SAIDA_H)
    x, _y, w, _h = layout["crop"]
    assert abs((x + w / 2) - LARGURA / 2) <= 1


def test_ffmpeg_error_is_never_reported_empty():
    """Clipe 14 do Papo Reto falhou com stderr vazio nos dois motores."""
    assert enq._detalhar_erro_ffmpeg("", 1).strip()
    assert "codigo 1" in enq._detalhar_erro_ffmpeg("", 1)
    assert enq._detalhar_erro_ffmpeg("   ", 8) != ""
    assert enq._detalhar_erro_ffmpeg("Invalid argument", 1) == "Invalid argument"


def _amostra(frame, x, w=0.15):
    return (frame, [{"x": x, "y": 0.35, "w": w}])


def test_scene_is_split_when_the_camera_changes():
    """Caso real do clipe 49: uma 'cena' de 66s continha dois enquadramentos."""
    cena = {"frame_ini": 0, "frame_fim": 2000}
    amostras = [_amostra(f, 0.36) for f in range(0, 1000, 200)]
    amostras += [_amostra(f, 0.50) for f in range(1000, 2000, 200)]

    pedacos = enq._subdividir_cena_por_plano(cena, amostras)

    assert len(pedacos) == 2
    assert pedacos[0]["frame_ini"] == 0
    assert pedacos[1]["frame_fim"] == 2000
    assert pedacos[0]["frame_fim"] == pedacos[1]["frame_ini"]


def test_a_still_scene_is_not_split():
    cena = {"frame_ini": 0, "frame_fim": 900}
    amostras = [_amostra(f, 0.50 + (f % 3) * 0.005) for f in range(0, 900, 100)]
    assert len(enq._subdividir_cena_por_plano(cena, amostras)) == 1


def test_zoom_change_also_splits_the_scene():
    """Mesma posicao, rosto muito maior = outra camera."""
    cena = {"frame_ini": 0, "frame_fim": 800}
    amostras = [_amostra(f, 0.50, 0.08) for f in range(0, 400, 100)]
    amostras += [_amostra(f, 0.50, 0.16) for f in range(400, 800, 100)]
    assert len(enq._subdividir_cena_por_plano(cena, amostras)) == 2


def test_scene_without_faces_is_kept_whole():
    cena = {"frame_ini": 0, "frame_fim": 600}
    amostras = [(f, []) for f in range(0, 600, 100)]
    pedacos = enq._subdividir_cena_por_plano(cena, amostras)
    assert len(pedacos) == 1
    assert pedacos[0]["frame_fim"] == 600


def test_subdivision_covers_the_whole_scene_without_gaps():
    cena = {"frame_ini": 100, "frame_fim": 1600}
    amostras = [_amostra(f, 0.30) for f in range(100, 700, 150)]
    amostras += [_amostra(f, 0.55) for f in range(700, 1200, 150)]
    amostras += [_amostra(f, 0.80) for f in range(1200, 1600, 150)]

    pedacos = enq._subdividir_cena_por_plano(cena, amostras)

    assert pedacos[0]["frame_ini"] == 100
    assert pedacos[-1]["frame_fim"] == 1600
    for anterior, seguinte in zip(pedacos, pedacos[1:]):
        assert anterior["frame_fim"] == seguinte["frame_ini"]


def test_block_never_holds_positions_that_do_not_fit_one_crop():
    """O criterio de divisao e a folga real do quadro, nao um limiar arbitrario."""
    largura_crop = enq._largura_crop_normalizada(1920, 1080)
    assert 0.30 < largura_crop < 0.33  # 9:16 sobre fonte 16:9

    # Cabeca de 0.225 + margens deixa pouco espaco para a pessoa se deslocar.
    assert enq._cabe_no_mesmo_crop([0.50, 0.52], 0.15, largura_crop)
    assert not enq._cabe_no_mesmo_crop([0.36, 0.50], 0.15, largura_crop)


def test_drifting_person_is_split_even_without_a_camera_cut():
    """Caso do clipe 48: a pessoa se desloca e o crop fixo corta a cabeca."""
    cena = {"frame_ini": 0, "frame_fim": 1200}
    amostras = [_amostra(f, 0.42 + f * 0.00008) for f in range(0, 1200, 100)]

    pedacos = enq._subdividir_cena_por_plano(cena, amostras, 1920, 1080)

    assert len(pedacos) >= 2
    for pedaco in pedacos:
        xs = [enq._plano_da_amostra(r)[0] for _f, r in pedaco["amostras"]]
        maior = max(enq._plano_da_amostra(r)[1] for _f, r in pedaco["amostras"])
        assert enq._cabe_no_mesmo_crop(xs, maior, enq._largura_crop_normalizada(1920, 1080))


def test_vertical_source_gets_a_wider_relative_crop():
    """Fonte ja vertical quase nao precisa cortar na largura."""
    assert enq._largura_crop_normalizada(1080, 1920) == 1.0
