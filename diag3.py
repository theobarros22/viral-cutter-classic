# -*- coding: utf-8 -*-
"""Onde, exatamente, o participante do lado direito desaparece."""
import os, sys
R = r"H:\CORTE VIRAL\ViralCutter-Classic-Atualizado"
sys.path.insert(0, R); os.chdir(R)
import numpy as np, rostos

def resumo(nome, dets):
    if not dets:
        print("    %-34s 0 deteccoes" % nome, flush=True); return
    esq = [d for d in dets if float(d["posicao_x"]) < 0.45]
    dir_ = [d for d in dets if float(d["posicao_x"]) > 0.55]
    cen = [d for d in dets if 0.45 <= float(d["posicao_x"]) <= 0.55]
    print("    %-34s total=%-3d  esquerda=%-3d  centro=%-2d  DIREITA=%-3d"
          % (nome, len(dets), len(esq), len(cen), len(dir_)), flush=True)

_filtrar_orig = rostos._filtrar_candidatos_pessoas
_remover_orig = rostos._remover_identidades_sem_rosto_valido
_agrupar_orig = rostos._agrupar_por_identidade
rodada = {"n": 0}

def filtrar(deteccoes, total_amostras, exigir_persistencia_por_lado=False):
    rodada["n"] += 1
    minimo_010 = max(2, min(4, int(np.ceil(max(1, total_amostras) * 0.10))))
    minimo_006 = max(2, int(np.ceil(max(1, total_amostras) * 0.06)))
    print("\n--- RODADA %d | amostras acumuladas=%d | minimo_frames filtro=%d agrupamento=%d ---"
          % (rodada["n"], total_amostras, minimo_010, minimo_006), flush=True)
    resumo("1. deteccoes acumuladas", deteccoes)
    r = _filtrar_orig(deteccoes, total_amostras, exigir_persistencia_por_lado)
    resumo("2. apos _filtrar_candidatos", r)
    return r

def remover(deteccoes):
    r = _remover_orig(deteccoes)
    resumo("3. apos _remover_sem_rosto_valido", r)
    return r

def agrupar(deteccoes, reconhecedor, total_amostras, **kw):
    pessoas = _agrupar_orig(deteccoes, reconhecedor, total_amostras, **kw)
    print("    4. pessoas finais da rodada: %d" % len(pessoas), flush=True)
    for p in pessoas:
        print("       - %s x=%.3f aparicoes=%d" % (p["nome"], p["posicao_x"], p["n_aparicoes"]), flush=True)
    return pessoas

rostos._filtrar_candidatos_pessoas = filtrar
rostos._remover_identidades_sem_rosto_valido = remover
rostos._agrupar_por_identidade = agrupar

pessoas = rostos.detectar_pessoas_no_video(r"F:\Meu_Vídeo\RFNSL_BENY.mov", max_amostras=30)
print("\n=== RESULTADO: %d pessoa(s) ===" % len(pessoas), flush=True)
