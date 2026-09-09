# -*- coding: utf-8 -*-
"""Mede a identidade facial no material real, em vez de julgar por preview.

Roda a deteccao de verdade e imprime:
  - quantas vezes o alinhamento YuNet realmente disparou;
  - a similaridade SFace entre TODOS os pares de grupos;
  - o limite aplicado a cada par e a decisao tomada.

Sem isso, calibrar limiar e chute.
"""
import io, os, sys, json, time
sys.path.insert(0, r"H:\CORTE VIRAL\ViralCutter-Classic-Atualizado")
os.chdir(r"H:\CORTE VIRAL\ViralCutter-Classic-Atualizado")

import cv2, numpy as np
import rostos

VIDEO = r"F:\Meu_Vídeo\RFNSL_BENY.mov"
SAIDA = r"H:\CORTE VIRAL\ViralCutter-Classic-Atualizado\diagnostico-identidade"
os.makedirs(SAIDA, exist_ok=True)

alinhamento = {"tentou": 0, "ok": 0, "sem_pontos": 0, "nao_yunet": 0}
_alinhar_original = rostos._alinhar_rosto_yunet

def alinhar_instrumentado(frame, rosto, reconhecedor):
    alinhamento["tentou"] += 1
    if rosto.get("fonte") != "yunet":
        alinhamento["nao_yunet"] += 1
    elif len(rosto.get("pontos", ())) != 5:
        alinhamento["sem_pontos"] += 1
    r = _alinhar_original(frame, rosto, reconhecedor)
    if r is not None:
        alinhamento["ok"] += 1
    return r

rostos._alinhar_rosto_yunet = alinhar_instrumentado

pares = []
_fundir_original = rostos._fundir_grupos_da_mesma_pessoa

def fundir_instrumentado(grupos, reconhecedor, limiar):
    print("\n== MATRIZ DE SIMILARIDADE (antes da fusao) ==", flush=True)
    print("grupos brutos: %d" % len(grupos), flush=True)
    for i in range(len(grupos)):
        for j in range(i + 1, len(grupos)):
            a, b = grupos[i], grupos[j]
            score = max(
                float(reconhecedor.match(ea, eb, cv2.FaceRecognizerSF_FR_COSINE))
                for ea in a["embeddings"] for eb in b["embeddings"]
            )
            simultaneo = bool(a["frames"] & b["frames"])
            limite = max(limiar, rostos.LIMIAR_IDENTIDADE_SIMULTANEA) if simultaneo else limiar
            pares.append({
                "a": i, "b": j, "score": round(score, 4),
                "simultaneo": simultaneo, "limite": round(limite, 4),
                "funde": score >= limite,
                "frames_a": len(a["frames"]), "frames_b": len(b["frames"]),
            })
            print("  g%-2d x g%-2d  score=%.4f  %s  limite=%.2f  -> %s"
                  % (i, j, score, "MESMO FRAME" if simultaneo else "frames dif.",
                     limite, "FUNDE" if score >= limite else "separa"), flush=True)
    # salva um preview de cada grupo bruto para conferencia visual
    for i, g in enumerate(grupos):
        try:
            melhor = rostos._escolher_melhor_preview(g["deteccoes"])
            img = melhor.get("recorte_identidade", melhor["recorte"])
            cv2.imwrite(os.path.join(SAIDA, "grupo_bruto_%02d.png" % i), img)
        except Exception as e:
            print("  (sem preview do grupo %d: %s)" % (i, e), flush=True)
    return _fundir_original(grupos, reconhecedor, limiar)

rostos._fundir_grupos_da_mesma_pessoa = fundir_instrumentado

print("Video:", VIDEO, flush=True)
print("LIMIAR_IDENTIDADE_SFACE      =", rostos.LIMIAR_IDENTIDADE_SFACE, flush=True)
print("LIMIAR_IDENTIDADE_SIMULTANEA =", rostos.LIMIAR_IDENTIDADE_SIMULTANEA, flush=True)
inicio = time.time()

pessoas = rostos.detectar_pessoas_no_video(VIDEO, max_amostras=30)

print("\n== ALINHAMENTO YUNET ==", flush=True)
print(json.dumps(alinhamento, indent=2), flush=True)

print("\n== PESSOAS FINAIS: %d ==" % len(pessoas), flush=True)
for p in pessoas:
    print("  %s  x=%.3f y=%.3f aparicoes=%d"
          % (p["nome"], p["posicao_x"], p["posicao_y"], p["n_aparicoes"]), flush=True)
    cv2.imwrite(os.path.join(SAIDA, "final_%d_%s.png" % (p["id"], p["lado"])), p["recorte_cv2"])

with io.open(os.path.join(SAIDA, "pares.json"), "w", encoding="utf-8") as f:
    json.dump(pares, f, indent=2, ensure_ascii=False)

print("\nTempo: %.1fs" % (time.time() - inicio), flush=True)
print("Saida em:", SAIDA, flush=True)
