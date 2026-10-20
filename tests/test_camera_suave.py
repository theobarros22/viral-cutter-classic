"""A camera virtual se move como um operador, nao como um servo perseguindo ruido."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import enquadramento as enq


FPS = 30.0


def _amostras(valores, fps=FPS, intervalo=0.8):
    """Serie de (quadro, x, y, w) espacada no tempo como a analise real."""
    passo = int(fps * intervalo)
    return [(i * passo, x, 0.40, 0.12) for i, x in enumerate(valores)]


def test_small_head_movement_keeps_the_frame_still():
    """Zona morta: balanco de cabeca nao pode mexer o quadro."""
    tremor = [0.500, 0.504, 0.497, 0.503, 0.499, 0.502, 0.498]
    traj = enq._suavizar_trajetoria(_amostras(tremor), FPS, largura_crop=0.317)

    xs = [x for _q, x in traj]
    assert max(xs) - min(xs) < 0.005, f"quadro tremeu: amplitude {max(xs)-min(xs):.4f}"


def test_real_displacement_is_followed():
    """A pessoa anda de verdade: a camera tem de ir junto."""
    desloca = [0.30, 0.34, 0.40, 0.46, 0.52, 0.58, 0.62, 0.66, 0.70]
    traj = enq._suavizar_trajetoria(_amostras(desloca), FPS, largura_crop=0.317)

    xs = [x for _q, x in traj]
    assert xs[-1] > xs[0] + 0.20, "a camera ficou para tras do deslocamento"
    assert xs[-1] <= max(desloca), "a camera ultrapassou o alvo"


def test_isolated_detection_spike_is_ignored():
    """Um pico de deteccao errada nao pode arrastar o quadro."""
    com_pico = [0.50, 0.50, 0.50, 0.95, 0.50, 0.50, 0.50]
    traj = enq._suavizar_trajetoria(_amostras(com_pico), FPS, largura_crop=0.317)

    xs = [x for _q, x in traj]
    assert max(xs) < 0.60, f"o pico arrastou a camera ate {max(xs):.3f}"


def test_missing_detections_do_not_jerk_the_camera():
    """Frame sem rosto e preenchido, nao vira tranco."""
    com_buracos = [0.50, None, 0.52, None, None, 0.54, 0.55]
    traj = enq._suavizar_trajetoria(_amostras(com_buracos), FPS, largura_crop=0.317)

    assert traj, "deveria produzir trajetoria mesmo com lacunas"
    xs = [x for _q, x in traj]
    saltos = [abs(b - a) for a, b in zip(xs, xs[1:])]
    assert max(saltos) < 0.05, f"deu tranco de {max(saltos):.3f}"


def test_too_few_detections_gives_up_instead_of_guessing():
    """Sem sinal suficiente, quadro parado e melhor que perseguir ruido."""
    quase_vazio = [0.5] + [None] * 12
    assert enq._suavizar_trajetoria(_amostras(quase_vazio), FPS) == []


def test_spring_never_overshoots_the_target():
    """Mola criticamente amortecida: chega ao alvo sem passar dele."""
    tempos = [i * 0.1 for i in range(40)]
    alvos = [0.0] + [1.0] * 39
    saida = enq._mola_amortecida(alvos, tempos, tempo_suave=0.5,
                                 velocidade_maxima=10.0)

    assert max(saida) <= 1.0 + 1e-9, f"ultrapassou o alvo: {max(saida)}"
    assert saida[-1] == pytest.approx(1.0, abs=0.02), "nao alcancou o alvo"


def test_spring_accelerates_then_decelerates():
    """O movimento tem ease: comeca devagar, ganha velocidade, freia."""
    tempos = [i * 0.1 for i in range(30)]
    alvos = [0.0] + [1.0] * 29
    saida = enq._mola_amortecida(alvos, tempos, tempo_suave=0.9,
                                 velocidade_maxima=10.0)

    passos = [b - a for a, b in zip(saida, saida[1:])]
    pico = passos.index(max(passos))
    assert pico > 0, "comecou na velocidade maxima, sem aceleracao"
    assert passos[-1] < max(passos) / 2, "terminou sem desacelerar"


def test_median_filter_preserves_real_motion():
    """A mediana mata pico, mas nao pode achatar deslocamento verdadeiro."""
    rampa = [0.1, 0.2, 0.3, 0.4, 0.5]
    assert enq._mediana_movel(rampa, 3) == pytest.approx(rampa, abs=1e-9)


def test_deadzone_anchor_moves_only_past_the_zone():
    alvos = enq._alvos_com_zona_morta([0.50, 0.52, 0.54, 0.70], zona_morta=0.05)
    assert alvos[0] == alvos[1] == alvos[2], "ancora andou dentro da zona morta"
    assert alvos[3] > alvos[2], "ancora nao acompanhou fora da zona morta"


def test_gap_fill_handles_leading_and_trailing_holes():
    assert enq._preencher_lacunas([None, None, 0.4, None]) == [0.4, 0.4, 0.4, 0.4]
    assert enq._preencher_lacunas([None, None]) == [None, None]
