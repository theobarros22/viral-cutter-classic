# -*- coding: utf-8 -*-
"""Dois participantes no mesmo frame nao podem virar uma pessoa so.

Regressao real: num podcast de 144 min, os dois participantes -- um em
x=0.31 e outro em x=0.89, no mesmo frame, com rostos de tamanho parecido --
foram fundidos numa identidade unica posicionada em x=0.52, o ponto medio
entre eles. A regra geometrica que impedia isso existia em
PARA-DESENVOLVEDORES.md e se perdeu na troca para identidade facial.
"""
import numpy as np
import pytest

import rostos


def _grupo(x, frames, tamanho=0.07, n=4):
    return {
        "deteccoes": [
            {"posicao_x": x, "posicao_y": 0.37, "tamanho": tamanho} for _ in range(n)
        ],
        "embeddings": [np.zeros((1, 128), dtype=np.float32)],
        "frames": set(frames),
    }


def test_lados_opostos_no_mesmo_frame_sao_pessoas_distintas():
    esquerda = _grupo(0.314, [0, 1499, 8999])
    direita = _grupo(0.890, [0, 1499, 8999])

    assert rostos._sao_participantes_distintos(esquerda, direita)


def test_mesma_pessoa_em_cameras_diferentes_nao_e_vetada():
    """Sem co-ocorrencia o veto nao vale -- e o caso que exigiu o SFace."""
    camera_a = _grupo(0.30, [100, 200])
    camera_b = _grupo(0.85, [300, 400])

    assert not rostos._sao_participantes_distintos(camera_a, camera_b)


def test_rostos_proximos_nao_sao_vetados():
    """Duas deteccoes do mesmo rosto oscilando de posicao continuam fundiveis."""
    a = _grupo(0.50, [10, 20])
    b = _grupo(0.58, [10, 20])

    assert not rostos._sao_participantes_distintos(a, b)


def test_tamanhos_incompativeis_nao_sao_vetados():
    """Rosto ao fundo x rosto em primeiro plano: nao e o caso de dois lados."""
    perto = _grupo(0.25, [5], tamanho=0.20)
    longe = _grupo(0.85, [5], tamanho=0.03)

    assert not rostos._sao_participantes_distintos(perto, longe)


def test_veto_impede_a_fusao_de_fato():
    """O veto tem de agir dentro de _fundir_grupos_da_mesma_pessoa."""

    class ReconhecedorQueSempreConcorda:
        def match(self, a, b, tipo):
            return 0.99  # similaridade maxima: so o veto pode separar

    grupos = [_grupo(0.314, [0, 1499]), _grupo(0.890, [0, 1499])]
    resultado = rostos._fundir_grupos_da_mesma_pessoa(
        grupos, ReconhecedorQueSempreConcorda(), rostos.LIMIAR_IDENTIDADE_SFACE
    )

    assert len(resultado) == 2, "os dois lados foram fundidos apesar do veto"


def test_score_entre_grupos_usa_mediana_e_nao_maximo():
    """Com muitas poses, o maximo sobe so por haver mais amostra."""

    class ReconhecedorComUmParAlto:
        def __init__(self):
            self.chamadas = 0

        def match(self, a, b, tipo):
            self.chamadas += 1
            return 0.95 if self.chamadas == 1 else 0.10

    a = _grupo(0.30, [10])
    b = _grupo(0.32, [20])
    a["embeddings"] = [np.zeros((1, 128), dtype=np.float32) for _ in range(4)]
    b["embeddings"] = [np.zeros((1, 128), dtype=np.float32) for _ in range(4)]

    resultado = rostos._fundir_grupos_da_mesma_pessoa(
        [a, b], ReconhecedorComUmParAlto(), rostos.LIMIAR_IDENTIDADE_SFACE
    )

    assert len(resultado) == 2, "um unico par alto nao pode fundir dois grupos"
