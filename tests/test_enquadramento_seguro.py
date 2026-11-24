"""Testes da regra definitiva de enquadramento seguro (nenhuma pessoa cortada)."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import enquadramento as enq


LARGURA, ALTURA = 1920, 1080
SAIDA_W, SAIDA_H = 1080, 1920


def _validar_layout(layout, alvos, largura=LARGURA, altura=ALTURA):
    """Confere que todo alvo cabe com margem em pelo menos um painel do layout.

    Conforme a regra definitiva: a cabeca inteira e obrigatoria; ombros e tronco
    sao preferencia, pois em close-up os ombros nao cabem num 9:16/9:8.
    """
    caixas = enq._caixas_cabecas(alvos, largura, altura)
    if layout["tipo"] == "solo":
        crops = [layout["crop"]]
    else:
        crops = [layout["top_crop"], layout["bot_crop"]]
    for caixa in caixas:
        assert any(
            enq._validar_crop_alvos(c, [caixa], largura, altura)[0] for c in crops
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


def test_camera_cut_reanchors_when_previous_speaker_target_is_empty():
    """Uma troca de camera nao pode continuar mirando o ponto da tomada anterior."""
    segmento = {
        "frame_ini": 0,
        "frame_fim": 90,
        "start_s": 0.0,
        "end_s": 3.0,
        "plano": {"modo": "SOLO_A", "xa": 0.18, "xb": 0.18,
                  "ya": 0.40, "yb": 0.40, "ta": 0.06, "tb": 0.06},
    }
    amostras = {
        15: [{"x": 0.76, "y": 0.40, "w": 0.08}],
        45: [{"x": 0.77, "y": 0.40, "w": 0.08}],
        75: [{"x": 0.75, "y": 0.40, "w": 0.08}],
    }

    ajustado = enq._ajustar_segmentos_pelos_frames(
        "", [segmento], LARGURA, ALTURA, 30.0, amostras
    )

    assert ajustado
    assert ajustado[0]["plano"]["xa"] == pytest.approx(0.76, abs=0.02)


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


def test_panels_come_before_the_open_frame():
    """Paineis empilhados sao aceitaveis; so caem para o quadro aberto se nao servirem."""
    plano = {
        "modo": "GRUPO",
        "xa": 0.12, "ya": 0.45, "ta": 0.07,
        "xb": 0.88, "yb": 0.45, "tb": 0.07,
    }
    relatorio = {}
    layout = enq._calcular_filtros_shot(
        plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H, relatorio=relatorio
    )
    assert layout["tipo"] == "split"
    assert layout["top_scale"][1] + layout["bot_scale"][1] == SAIDA_H
    assert not relatorio.get("revisar")


def test_alvo_migra_para_o_falante_mesmo_com_sinal_esparso():
    """A deteccao de fala so preenche 1 frame a cada ~15; o resto vem None.

    Se o None interrompesse a contagem da histerese, a espera de 1,5s viraria
    ~22s e o alvo nunca migraria dentro de um clipe — foi o que deixou os
    primeiros segundos de um clipe enquadrados no logo da parede em vez da
    pessoa que falava.
    """
    from enquadramento import _alvos_seguindo_falante

    fps = 24.0
    x_cena = 0.68          # onde a cena "viu" alguem (na verdade, o logo)
    x_falante = 0.26       # onde a pessoa realmente esta

    # 6 segundos de sinal, com valor a cada 15 frames e None no resto
    posicoes = []
    for i in range(int(fps * 6)):
        posicoes.append(x_falante if i % 15 == 0 else None)

    alvos = _alvos_seguindo_falante(posicoes, x_cena, fps, limiar_s=1.5)

    # Comeca ja no falante: no primeiro instante do clipe nao ha nada anterior
    # a preservar, e esperar 1,5s significaria abrir apontando para o lugar
    # errado — que foi o defeito real (o quadro abria no logo da parede).
    assert abs(alvos[0] - x_falante) < 1e-6, "deve abrir ja no falante"
    assert abs(alvos[int(fps * 2)] - x_falante) < 1e-6
    assert abs(alvos[-1] - x_falante) < 1e-6


def test_histerese_segura_troca_no_meio_da_cena():
    """No meio da cena, a histerese continua valendo: nao troca por um pico.

    Aqui a cena comeca concordando com o falante; a troca so acontece depois
    de 1,5s insistindo, e um unico valor divergente nao move o quadro.
    """
    from enquadramento import _alvos_seguindo_falante

    fps = 24.0
    x_cena = 0.26
    posicoes = []
    for i in range(int(fps * 6)):
        if i % 15:
            posicoes.append(None)
        elif i == 45:          # um unico pico isolado para o outro lado
            posicoes.append(0.73)
        else:
            posicoes.append(0.26)

    alvos = _alvos_seguindo_falante(posicoes, x_cena, fps, limiar_s=1.5)
    assert all(abs(a - x_cena) < 1e-6 for a in alvos), (
        "um valor isolado nao pode mover o quadro"
    )


def test_alvo_nao_migra_com_falante_perto_do_alvo_da_cena():
    """Movimento na cadeira nao pode ser lido como troca de pessoa."""
    from enquadramento import _alvos_seguindo_falante

    fps = 24.0
    x_cena = 0.30
    posicoes = [0.33 if i % 15 == 0 else None for i in range(int(fps * 6))]

    alvos = _alvos_seguindo_falante(posicoes, x_cena, fps, limiar_s=1.5)
    assert all(abs(a - x_cena) < 1e-6 for a in alvos)


def test_rosto_em_close_up_maior_que_32_porcento_nao_e_descartado():
    """Rosto real em close-up (>32% da largura) e alvo valido e preserva a cabeca inteira."""
    alvo_close = (0.50, 0.40, 0.36)
    # 1. Nao pode retornar None como se fosse falso positivo
    caixa_cabeca = enq._caixa_cabeca(alvo_close, LARGURA, ALTURA)
    assert caixa_cabeca is not None, "caixa_cabeca descartou rosto legitimo em close-up (> 32%)"
    caixa_humana = enq._caixa_humana(alvo_close, LARGURA, ALTURA)
    assert caixa_humana is not None, "caixa_humana descartou rosto legitimo em close-up (> 32%)"

    # 2. No calcular filtros shot em 16:9, a cabeca (1.5 * 0.36 = 54% de 1920)
    # nao cabe num crop 9:16 solo (31.7%), logo deve degradar com seguranca para
    # paineis horizontais (FALLBACK_SPLIT), sem rotular como 'cena_sem_rosto_confiavel'.
    plano = {"modo": "SOLO_A", "xa": 0.50, "ya": 0.40, "ta": 0.36}
    relatorio = {}
    layout = enq._calcular_filtros_shot(
        plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H, relatorio=relatorio
    )
    assert "cena_sem_rosto_confiavel" not in relatorio.get("motivos", [])
    assert layout["tipo"] == "split", "close-up que excede 9:16 solo deve usar paineis horizontais"
    _validar_layout(layout, [alvo_close])
    assert not relatorio.get("revisar")


def test_close_up_em_fonte_vertical_mantem_modo_solo():
    """Em fonte vertical (1080x1920), close-up de 36% da largura cabe em SOLO."""
    alvo_close = (0.50, 0.40, 0.36)
    plano = {"modo": "SOLO_A", "xa": 0.50, "ya": 0.40, "ta": 0.36}
    relatorio = {}
    layout = enq._calcular_filtros_shot(
        plano, SAIDA_W, SAIDA_H, SAIDA_W, SAIDA_H, relatorio=relatorio
    )
    assert layout["tipo"] == "solo"
    _validar_layout(layout, [alvo_close], SAIDA_W, SAIDA_H)
    assert not relatorio.get("revisar")


def test_close_up_impossivel_sem_modo_seguro_marca_revisar():
    """Composicao sem enquadramento seguro possivel deve ser marcada para revisar."""
    # Rosto de 70% da largura em 16:9: cabeca de 1.5 * 0.70 * 1920 = 2016px > 1920px.
    # Nao cabe em solo nem em painel horizontal: DEVE marcar revisar.
    plano = {"modo": "SOLO_A", "xa": 0.50, "ya": 0.40, "ta": 0.70}
    relatorio = {}
    layout = enq._calcular_filtros_shot(
        plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H, relatorio=relatorio
    )
    assert relatorio.get("revisar") is True, "composicao que corta cabeca tem que marcar revisar"


def test_reporter_em_pe_nao_e_descartado_por_presenca_em_zona_sentada():
    """Reporter externo ou apresentador em pe (Y < 0.30) nao pode ser descartado."""
    amostras_rostos = [
        {"x": 0.35, "y": 0.18, "w": 0.08},  # Reporter em pe
        {"x": 0.75, "y": 0.45, "w": 0.05},  # Elemento na zona de sentados
    ]
    xs, ys, ws = enq._filtrar_rostos_na_zona_de_cabeca(amostras_rostos)
    assert any(abs(x - 0.35) < 1e-4 for x in xs), "reporter em pe (Y=0.18) foi descartado pelo filtro de zona sentada"


def test_reporter_em_pe_preserva_topo_da_cabeca_sem_corte():
    """Enquadramento de reporter em pe deve conter a cabeca inteira sem cortar o topo."""
    plano = {"modo": "SOLO_A", "xa": 0.35, "ya": 0.18, "ta": 0.08}
    relatorio = {}
    layout = enq._calcular_filtros_shot(
        plano, LARGURA, ALTURA, SAIDA_W, SAIDA_H, relatorio=relatorio
    )
    _validar_layout(layout, [(0.35, 0.18, 0.08)])
    assert "cabeca_cortada_no_topo" not in relatorio.get("motivos", [])
    assert not relatorio.get("revisar")


def test_transicao_de_camera_invalida_alvo_antigo_e_reancora_no_novo():
    """Troca de camera para outro alvo nao pode ficar presa no alvo antigo vazio."""
    seg = {
        "plano": {"modo": "SOLO_A", "xa": 0.25, "ya": 0.40, "ta": 0.08},
        "frame_ini": 100,
        "frame_fim": 200,
        "start_s": 100 / 30.0,
        "end_s": 200 / 30.0,
    }
    # Na nova camera (frames 100-200), o alvo consistente esta em x=0.75
    amostras_por_frame = {
        f: [{"x": 0.75, "y": 0.40, "w": 0.08}]
        for f in range(100, 200, 15)
    }
    ajustados = enq._ajustar_segmentos_pelos_frames(
        None, [seg], LARGURA, ALTURA, 30.0, amostras_por_frame=amostras_por_frame
    )
    assert len(ajustados) >= 1
    # O shot reancorado deve apontar para o alvo real (0.75), nao continuar em 0.25
    novo_xa = ajustados[0]["plano"]["xa"]
    assert abs(novo_xa - 0.75) < 0.05, f"shot ficou preso no alvo antigo {novo_xa}, nao reancorou em 0.75"
